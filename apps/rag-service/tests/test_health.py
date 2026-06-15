from careai_rag_service.main import app
from fastapi.testclient import TestClient


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "rag-service"


def test_readyz() -> None:
    response = TestClient(app).get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["azure_ai_search"] == "local-placeholder"

