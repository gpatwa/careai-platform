from dataclasses import replace

from ingest_rag.documents import chunk_documents, load_documents
from ingest_rag.embeddings import LocalDeterministicEmbeddingProvider
from ingest_rag.ingest import attach_embeddings
from ingest_rag.local_index import load_local_index, search_local_index, write_local_index


def test_write_and_search_local_index_with_role_filter(tmp_path) -> None:
    provider = LocalDeterministicEmbeddingProvider(dimension=32)
    documents = load_documents("data/synthetic_docs")
    chunks = chunk_documents(documents, max_chars=700, overlap_chars=80)
    embedded = attach_embeddings(chunks, provider)
    index_path = write_local_index(
        embedded,
        tmp_path / "rag-index.json",
        embedding_dimension=provider.dimension,
    )

    payload = load_local_index(index_path)
    assert payload["schema_version"] == "careai-local-rag-index-v1"
    assert payload["embedding_dimension"] == 32
    assert len(payload["chunks"]) == len(embedded)

    query_vector = provider.embed_texts(["pharmacy exception urgent access"])[0]
    pharmacy_results = search_local_index(
        index_path=index_path,
        query="pharmacy exception urgent access",
        query_vector=query_vector,
        allowed_role="pharmacy_ops",
        top_k=3,
    )
    support_results = search_local_index(
        index_path=index_path,
        query="pharmacy exception urgent access",
        query_vector=query_vector,
        allowed_role="member_support",
        top_k=3,
    )

    assert pharmacy_results
    assert all("pharmacy_ops" in result["allowed_roles"] for result in pharmacy_results)
    assert support_results
    assert all("member_support" in result["allowed_roles"] for result in support_results)


def test_local_search_rejects_dimension_mismatch(tmp_path) -> None:
    provider = LocalDeterministicEmbeddingProvider(dimension=8)
    chunks = chunk_documents(load_documents("data/synthetic_docs")[:1])
    embedded = attach_embeddings(chunks, provider)
    broken = [replace(embedded[0], content_vector=[1.0, 2.0])]
    index_path = write_local_index(broken, tmp_path / "broken.json", embedding_dimension=2)

    try:
        search_local_index(
            index_path=index_path,
            query="prior authorization",
            query_vector=provider.embed_texts(["prior authorization"])[0],
        )
    except ValueError as exc:
        assert "same dimension" in str(exc)
    else:
        raise AssertionError("expected dimension mismatch to raise")
