from ingest_rag.embeddings import (
    AzureOpenAIEmbeddingProvider,
    LocalDeterministicEmbeddingProvider,
)


def test_local_deterministic_embeddings_are_stable_and_normalized() -> None:
    provider = LocalDeterministicEmbeddingProvider(dimension=16)

    first = provider.embed_texts(["prior authorization review"])[0]
    second = provider.embed_texts(["prior authorization review"])[0]
    different = provider.embed_texts(["pharmacy exception"])[0]

    assert first == second
    assert first != different
    assert len(first) == 16
    assert round(sum(value * value for value in first), 6) == 1.0


def test_azure_openai_embedding_provider_posts_expected_payload(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, headers: dict, json: dict):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("ingest_rag.embeddings.httpx.Client", FakeClient)

    provider = AzureOpenAIEmbeddingProvider(
        endpoint="https://example.openai.azure.com",
        api_key="test-key",
        deployment="embed",
        api_version="2024-02-01",
        requested_dimensions=3,
    )
    vectors = provider.embed_texts(["synthetic policy"])

    assert vectors == [[0.1, 0.2, 0.3]]
    assert provider.dimension == 3
    assert captured["url"].endswith("/openai/deployments/embed/embeddings?api-version=2024-02-01")
    assert captured["headers"]["api-key"] == "test-key"
    assert captured["json"] == {"input": ["synthetic policy"], "dimensions": 3}
