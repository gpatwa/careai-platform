import json
from datetime import UTC, datetime

import joblib
from careai_inference_service.audit import AuditClient
from careai_inference_service.main import create_app
from careai_inference_service.model_manager import InferenceSettings
from fastapi.testclient import TestClient


class FixedProbabilityModel:
    def predict_proba(self, frame):
        return [[0.2, 0.8] for _ in range(len(frame))]


def valid_payload() -> dict:
    return {
        "request_id": "synthetic-request-001",
        "features": {
            "age_bucket": "65+",
            "plan_type": "medicare_advantage",
            "prior_claim_count": 8,
            "recent_visit_count": 4,
            "medication_count": 6,
            "chronic_condition_count": 3,
            "region_code": "R03",
            "feature_timestamp": datetime.now(UTC).isoformat(),
        },
    }


def test_prediction_uses_loaded_model(tmp_path) -> None:
    model_path = tmp_path / "claims-risk.joblib"
    metadata_path = tmp_path / "model-metadata.json"
    joblib.dump(FixedProbabilityModel(), model_path)
    metadata_path.write_text(json.dumps({"name": "claims-risk", "version": "test"}))

    app = create_app(
        InferenceSettings(
            model_uri=str(model_path),
            model_metadata_path=str(metadata_path),
            feature_version="features-test",
            max_feature_age_minutes=60,
            control_plane_url=None,
            audit_enabled=False,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/predict/claims-risk",
            headers={"x-correlation-id": "corr-loaded-model"},
            json=valid_payload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_score"] == 0.8
    assert body["risk_band"] == "high"
    assert body["model_name"] == "claims-risk"
    assert body["model_version"] == "test"
    assert body["feature_version"] == "features-test"
    assert body["correlation_id"] == "corr-loaded-model"
    assert body["fallback_mode"] is False
    assert "HIGH_SCORE_THRESHOLD" in body["decision_reason_codes"]


def test_validation_failure_for_missing_required_feature() -> None:
    app = create_app(load_model=False)
    payload = valid_payload()
    del payload["features"]["prior_claim_count"]

    with TestClient(app) as client:
        response = client.post("/predict/claims-risk", json=payload)

    assert response.status_code == 422


def test_model_unavailable_uses_deterministic_fallback() -> None:
    app = create_app(
        InferenceSettings(
            model_uri=None,
            model_metadata_path=None,
            feature_version="features-test",
            max_feature_age_minutes=60,
            control_plane_url=None,
            audit_enabled=False,
        )
    )

    with TestClient(app) as client:
        first = client.post("/predict/claims-risk", json=valid_payload()).json()
        second = client.post("/predict/claims-risk", json=valid_payload()).json()

    assert first["fallback_mode"] is True
    assert second["fallback_mode"] is True
    assert first["prediction_score"] == second["prediction_score"]
    assert "model_unavailable_rules_fallback_used" in first["warnings"]


def test_active_model_reports_fallback_when_model_is_unconfigured() -> None:
    app = create_app(
        InferenceSettings(
            model_uri=None,
            model_metadata_path=None,
            feature_version="features-test",
            max_feature_age_minutes=60,
            control_plane_url=None,
            audit_enabled=False,
        )
    )

    with TestClient(app) as client:
        response = client.get("/models/active")

    assert response.status_code == 200
    assert response.json()["fallback_mode"] is True
    assert response.json()["model_loaded"] is False


def test_audit_client_sends_prediction_event(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, json: dict):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("careai_inference_service.audit.httpx.Client", FakeClient)

    delivered = AuditClient("http://control-plane:8000").send_prediction_event(
        actor="inference-service",
        action="claims_risk.predicted",
        target_id="synthetic-request-001",
        correlation_id="corr-audit",
        metadata={"risk_band": "high"},
    )

    assert delivered is True
    assert captured["url"] == "http://control-plane:8000/audit-events"
    assert captured["json"]["metadata_json"] == {"risk_band": "high"}
    assert captured["json"]["target_type"] == "prediction"
