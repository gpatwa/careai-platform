import argparse
from dataclasses import dataclass
from pathlib import Path

from ingest_rag.azure_search import AzureAISearchClient
from ingest_rag.documents import chunk_documents, load_documents
from ingest_rag.embeddings import EmbeddingProvider, embedding_provider_from_env
from ingest_rag.local_index import write_local_index
from ingest_rag.models import ChunkRecord

DEFAULT_OUTPUT_PATH = Path("data/local/rag-index.json")


@dataclass(frozen=True)
class IngestResult:
    chunk_count: int
    embedding_dimension: int
    target: str
    local_index_path: Path | None = None
    azure_index_name: str | None = None


def attach_embeddings(
    chunks: list[ChunkRecord],
    provider: EmbeddingProvider,
    *,
    batch_size: int = 16,
) -> list[ChunkRecord]:
    embedded: list[ChunkRecord] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = provider.embed_texts([chunk.content for chunk in batch])
        for chunk, vector in zip(batch, vectors, strict=True):
            embedded.append(
                ChunkRecord(
                    id=chunk.id,
                    doc_id=chunk.doc_id,
                    chunk_id=chunk.chunk_id,
                    title=chunk.title,
                    version=chunk.version,
                    sensitivity_class=chunk.sensitivity_class,
                    source_uri=chunk.source_uri,
                    allowed_roles=chunk.allowed_roles,
                    content=chunk.content,
                    content_vector=vector,
                )
            )
    return embedded


def ingest_documents(
    *,
    input_dir: str | Path,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    embedding_provider: EmbeddingProvider | None = None,
    search_client: AzureAISearchClient | None = None,
    max_chars: int = 900,
    overlap_chars: int = 150,
) -> IngestResult:
    documents = load_documents(input_dir)
    chunks = chunk_documents(documents, max_chars=max_chars, overlap_chars=overlap_chars)
    provider = embedding_provider or embedding_provider_from_env()
    embedded_chunks = attach_embeddings(chunks, provider)

    if search_client is not None:
        search_client.create_or_update_index(provider.dimension)
        search_client.upload_chunks(embedded_chunks)
        return IngestResult(
            chunk_count=len(embedded_chunks),
            embedding_dimension=provider.dimension,
            target="azure_ai_search",
            azure_index_name=search_client.index_name,
        )

    local_path = write_local_index(
        embedded_chunks,
        output_path,
        embedding_dimension=provider.dimension,
    )
    return IngestResult(
        chunk_count=len(embedded_chunks),
        embedding_dimension=provider.dimension,
        target="local_json",
        local_index_path=local_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest synthetic RAG documents into Azure AI Search or local JSON."
    )
    parser.add_argument("--input-dir", default="data/synthetic_docs")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--max-chars", type=int, default=900)
    parser.add_argument("--overlap-chars", type=int, default=150)
    parser.add_argument(
        "--force-local",
        action="store_true",
        help="Write local JSON even when Azure AI Search environment variables are present.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    search_client = None if args.force_local else AzureAISearchClient.from_env()
    result = ingest_documents(
        input_dir=args.input_dir,
        output_path=args.output,
        search_client=search_client,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
    )
    if result.target == "azure_ai_search":
        print(
            f"Uploaded {result.chunk_count} chunks to Azure AI Search index "
            f"{result.azure_index_name}."
        )
        return
    print(f"Wrote {result.chunk_count} chunks to {result.local_index_path}.")


if __name__ == "__main__":
    main()
