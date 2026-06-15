from ingest_rag.azure_search import AzureAISearchClient
from ingest_rag.models import ChunkRecord


def sample_chunk() -> ChunkRecord:
    return ChunkRecord(
        id="chunk-001",
        doc_id="responsible_ai_guidelines",
        chunk_id="responsible_ai_guidelines-0000",
        title="Responsible AI Guidelines",
        version="2026.06",
        sensitivity_class="synthetic-internal",
        source_uri="file:///synthetic/responsible_ai_guidelines.md",
        allowed_roles=["platform_admin", "model_risk_reviewer"],
        content="Retrieval must preserve document metadata.",
        content_vector=[0.1, 0.2, 0.3],
    )


def test_index_schema_contains_vector_and_role_fields() -> None:
    client = AzureAISearchClient(
        endpoint="https://search.example.net",
        api_key="key",
        index_name="careai-test",
    )

    schema = client.index_schema(embedding_dimension=3)
    fields = {field["name"]: field for field in schema["fields"]}

    assert fields["id"]["key"] is True
    assert fields["allowed_roles"]["type"] == "Collection(Edm.String)"
    assert fields["allowed_roles"]["filterable"] is True
    assert fields["content_vector"]["type"] == "Collection(Edm.Single)"
    assert fields["content_vector"]["dimensions"] == 3
    assert schema["vectorSearch"]["algorithms"][0]["kind"] == "hnsw"


def test_azure_search_client_sends_create_upload_and_search_requests(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, body: dict) -> None:
            self.body = body

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.body

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def put(self, url: str, headers: dict, json: dict):
            calls.append({"method": "PUT", "url": url, "headers": headers, "json": json})
            return FakeResponse({"name": json["name"]})

        def post(self, url: str, headers: dict, json: dict):
            calls.append({"method": "POST", "url": url, "headers": headers, "json": json})
            return FakeResponse({"value": []})

    monkeypatch.setattr("ingest_rag.azure_search.httpx.Client", FakeClient)

    client = AzureAISearchClient(
        endpoint="https://search.example.net",
        api_key="search-key",
        index_name="careai-test",
        api_version="2026-04-01",
    )

    client.create_or_update_index(embedding_dimension=3)
    client.upload_chunks([sample_chunk()])
    client.search(
        query="responsible ai retrieval",
        query_vector=[0.1, 0.2, 0.3],
        allowed_role="model_risk_reviewer",
        top_k=2,
    )

    assert calls[0]["method"] == "PUT"
    assert "/indexes/careai-test?allowIndexDowntime=true&api-version=2026-04-01" in calls[0][
        "url"
    ]
    assert calls[1]["json"]["value"][0]["@search.action"] == "upload"
    assert calls[2]["json"]["vectorQueries"][0]["fields"] == "content_vector"
    assert calls[2]["json"]["filter"] == (
        "allowed_roles/any(role: role eq 'model_risk_reviewer')"
    )
