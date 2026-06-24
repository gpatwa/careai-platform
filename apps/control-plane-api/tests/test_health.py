from careai_control_plane_api.main import app
from fastapi.testclient import TestClient


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "control-plane-api"


def test_correlation_id_header_is_propagated() -> None:
    response = TestClient(app).get("/healthz", headers={"x-correlation-id": "corr-health"})

    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == "corr-health"


def test_readyz() -> None:
    response = TestClient(app).get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["metadata_database"] == "ready"


def test_cors_preflight_allows_tenant_header() -> None:
    response = TestClient(app).options(
        "/models",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-tenant-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-tenant-id" in response.headers["access-control-allow-headers"]
