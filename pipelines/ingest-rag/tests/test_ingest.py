from ingest_rag.azure_search import AzureAISearchClient
from ingest_rag.embeddings import LocalDeterministicEmbeddingProvider
from ingest_rag.ingest import ingest_documents
from ingest_rag.local_index import load_local_index


class RecordingSearchClient(AzureAISearchClient):
    def __init__(self) -> None:
        super().__init__(
            endpoint="https://search.example.net",
            api_key="key",
            index_name="careai-test",
        )
        self.created_dimension: int | None = None
        self.uploaded_count = 0

    def create_or_update_index(self, embedding_dimension: int) -> dict:
        self.created_dimension = embedding_dimension
        return {"name": self.index_name}

    def upload_chunks(self, chunks: list) -> dict:
        self.uploaded_count = len(chunks)
        return {"value": [{"key": chunk.id, "status": True} for chunk in chunks]}


def test_ingest_documents_writes_local_index(tmp_path) -> None:
    provider = LocalDeterministicEmbeddingProvider(dimension=24)

    result = ingest_documents(
        input_dir="data/synthetic_docs",
        output_path=tmp_path / "rag-index.json",
        embedding_provider=provider,
        max_chars=600,
        overlap_chars=80,
    )

    assert result.target == "local_json"
    assert result.local_index_path is not None
    assert result.local_index_path.exists()
    assert result.chunk_count > 5
    payload = load_local_index(result.local_index_path)
    assert payload["embedding_dimension"] == 24


def test_ingest_documents_uploads_to_azure_search_when_configured() -> None:
    provider = LocalDeterministicEmbeddingProvider(dimension=12)
    search_client = RecordingSearchClient()

    result = ingest_documents(
        input_dir="data/synthetic_docs",
        embedding_provider=provider,
        search_client=search_client,
        max_chars=700,
        overlap_chars=80,
    )

    assert result.target == "azure_ai_search"
    assert result.azure_index_name == "careai-test"
    assert result.chunk_count == search_client.uploaded_count
    assert search_client.created_dimension == 12
