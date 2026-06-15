import logging
import os
from abc import ABC, abstractmethod
from dataclasses import replace
from pathlib import Path
from typing import Any

from ingest_rag.azure_search import AzureAISearchClient
from ingest_rag.documents import DEFAULT_DOCS_DIR, chunk_documents, load_documents
from ingest_rag.embeddings import (
    AzureOpenAIEmbeddingProvider,
    EmbeddingProvider,
    LocalDeterministicEmbeddingProvider,
    embedding_provider_from_env,
)
from ingest_rag.local_index import search_local_index, write_local_index

from careai_rag_service.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_INDEX_PATH = Path("data/local/rag-index.json")


class Retriever(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def search(self, *, query: str, role: str, top_k: int) -> list[RetrievedChunk]:
        raise NotImplementedError


class LocalVectorRetriever(Retriever):
    def __init__(
        self,
        *,
        index_path: str | Path = DEFAULT_LOCAL_INDEX_PATH,
        docs_dir: str | Path = DEFAULT_DOCS_DIR,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.index_path = Path(index_path)
        self.docs_dir = Path(docs_dir)
        self.embedding_provider = embedding_provider or LocalDeterministicEmbeddingProvider()

    @property
    def provider_name(self) -> str:
        return "local-json-vector-index"

    def search(self, *, query: str, role: str, top_k: int) -> list[RetrievedChunk]:
        self._ensure_index()
        query_vector = self.embedding_provider.embed_texts([query])[0]
        rows = search_local_index(
            index_path=self.index_path,
            query=query,
            query_vector=query_vector,
            allowed_role=role,
            top_k=top_k,
        )
        return [retrieved_chunk_from_row(row) for row in rows]

    def _ensure_index(self) -> None:
        if self.index_path.exists():
            return

        documents = load_documents(self.docs_dir)
        chunks = chunk_documents(documents)
        vectors = self.embedding_provider.embed_texts([chunk.content for chunk in chunks])
        embedded_chunks = [
            replace(chunk, content_vector=vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        write_local_index(
            embedded_chunks,
            self.index_path,
            embedding_dimension=self.embedding_provider.dimension,
        )
        logger.info(
            "built local RAG index",
            extra={"index_path": str(self.index_path), "chunk_count": len(embedded_chunks)},
        )


class AzureSearchRetriever(Retriever):
    def __init__(
        self,
        *,
        search_client: AzureAISearchClient,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.search_client = search_client
        self.embedding_provider = embedding_provider

    @property
    def provider_name(self) -> str:
        return "azure-ai-search"

    def search(self, *, query: str, role: str, top_k: int) -> list[RetrievedChunk]:
        query_vector = self.embedding_provider.embed_texts([query])[0]
        body = self.search_client.search(
            query=query,
            query_vector=query_vector,
            allowed_role=role,
            top_k=top_k,
        )
        rows = body.get("value", [])
        return [retrieved_chunk_from_row(row) for row in rows]


def retriever_from_env() -> Retriever:
    search_client = AzureAISearchClient.from_env()
    azure_embedding_provider = AzureOpenAIEmbeddingProvider.from_env()
    if search_client and azure_embedding_provider:
        return AzureSearchRetriever(
            search_client=search_client,
            embedding_provider=azure_embedding_provider,
        )

    if search_client and not azure_embedding_provider:
        logger.warning("Azure AI Search configured without Azure embeddings; using local fallback")

    return LocalVectorRetriever(
        index_path=os.getenv("RAG_LOCAL_INDEX_PATH", str(DEFAULT_LOCAL_INDEX_PATH)),
        docs_dir=os.getenv("RAG_DOCS_DIR", str(DEFAULT_DOCS_DIR)),
        embedding_provider=embedding_provider_from_env(),
    )


def retrieved_chunk_from_row(row: dict[str, Any]) -> RetrievedChunk:
    source_id = str(row.get("chunk_id") or row.get("id"))
    score = row.get("score", row.get("@search.score", 0.0))
    return RetrievedChunk(
        source_id=source_id,
        doc_id=str(row["doc_id"]),
        chunk_id=str(row["chunk_id"]),
        title=str(row["title"]),
        source_uri=str(row["source_uri"]),
        score=float(score),
        excerpt=trim_excerpt(str(row["content"])),
    )


def trim_excerpt(content: str, max_chars: int = 650) -> str:
    compact = " ".join(content.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."
