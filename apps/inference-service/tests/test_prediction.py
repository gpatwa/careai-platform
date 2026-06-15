import json
from datetime import UTC, datetime

import joblib
from careai_common.events import LocalLoggingEventPublisher
from careai_inference_service.audit import AuditClient
from careai_inference_service.main import create_app
from careai_inference_service.model_manager import InferenceSettings
from fastapi.testclient import TestClient


class FixedProbabilityModel:
    def predict_proba(self, frame):
        return [[0.2, 0.8] for _ in range(len(frame))]


class FailingProbabilityModel:
    def predict_proba(self, frame):
        raise RuntimeError("synthetic model failure")


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


def test_prediction_traffic_split_selects_champion_and_challenger(tmp_path) -> None:
    model_path = tmp_path / "claims-risk.joblib"
    metadata_path = tmp_path / "model-metadata.json"
    joblib.dump(FixedProbabilityModel(), model_path)
    metadata_path.write_text(json.dumps({"name": "claims-risk", "version": "champion-v1"}))

    app = create_app(
        InferenceSettings(
            model_uri=str(model_path),
            model_metadata_path=str(metadata_path),
            feature_version="features-test",
            max_feature_age_minutes=60,
            control_plane_url=None,
            audit_enabled=False,
            traffic_split_json={"champion": 50, "challenger": 50},
            champion_model_version="champion-v1",
            challenger_model_version="challenger-v2",
        )
    )

    champion_payload = valid_payload()
    champion_payload["request_id"] = "synthetic-request-001"
    challenger_payload = valid_payload()
    challenger_payload["request_id"] = "synthetic-request-000"

    with TestClient(app) as client:
        champion_response = client.post("/predict/claims-risk", json=champion_payload)
        challenger_response = client.post("/predict/claims-risk", json=challenger_payload)

    assert champion_response.status_code == 200
    assert challenger_response.status_code == 200
    champion = champion_response.json()
    challenger = challenger_response.json()
    assert champion["selected_model_role"] == "champion"
    assert champion["model_version"] == "champion-v1"
    assert challenger["selected_model_role"] == "challenger"
    assert challenger["model_version"] == "challenger-v2"
    assert challenger["traffic_split_json"] == {"champion": 50, "challenger": 50}


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


def test_audit_client_sends_monitoring_prediction_event(monkeypatch) -> None:
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

    delivered = AuditClient("http://control-plane:8000").send_monitoring_prediction_event(
        model_name="claims-risk",
        model_version="test",
        request_features=valid_payload()["features"],
        prediction_score=0.8,
        risk_band="high",
        latency_ms=12,
        correlation_id="corr-monitoring",
    )

    assert delivered is True
    assert captured["url"] == "http://control-plane:8000/monitoring/prediction-events"
    assert captured["json"]["model_name"] == "claims-risk"
    assert captured["json"]["latency_ms"] == 12
    assert captured["json"]["correlation_id"] == "corr-monitoring"


def test_audit_client_sends_monitoring_error_event(monkeypatch) -> None:
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

    delivered = AuditClient("http://control-plane:8000").send_monitoring_error_event(
        model_name="claims-risk",
        model_version="test",
        error_type="model_prediction_failed",
        error_message="Model prediction failed; deterministic fallback score returned.",
        status_code=200,
        latency_ms=15,
        correlation_id="corr-error",
    )

    assert delivered is True
    assert captured["url"] == "http://control-plane:8000/monitoring/error-events"
    assert captured["json"]["error_type"] == "model_prediction_failed"
    assert captured["json"]["status_code"] == 200
    assert captured["json"]["correlation_id"] == "corr-error"


def test_prediction_route_emits_monitoring_event(monkeypatch) -> None:
    posts: list[dict] = []

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
            posts.append({"url": url, "json": json})
            return FakeResponse()

    monkeypatch.setattr("careai_inference_service.audit.httpx.Client", FakeClient)
    app = create_app(
        InferenceSettings(
            model_uri=None,
            model_metadata_path=None,
            feature_version="features-test",
            max_feature_age_minutes=60,
            control_plane_url="http://control-plane:8000",
            audit_enabled=True,
            monitoring_enabled=True,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/predict/claims-risk",
            headers={"x-correlation-id": "corr-route-monitoring"},
            json=valid_payload(),
        )

    assert response.status_code == 200
    monitoring_post = next(
        post for post in posts if post["url"].endswith("/monitoring/prediction-events")
    )
    assert monitoring_post["json"]["model_name"] == "claims-risk-rules-fallback"
    assert monitoring_post["json"]["risk_band"] == response.json()["risk_band"]
    assert monitoring_post["json"]["correlation_id"] == "corr-route-monitoring"
    assert "feature_timestamp" not in monitoring_post["json"]["request_features_json"]


def test_prediction_route_publishes_prediction_created_event() -> None:
    publisher = LocalLoggingEventPublisher()
    app = create_app(
        InferenceSettings(
            model_uri=None,
            model_metadata_path=None,
            feature_version="features-test",
            max_feature_age_minutes=60,
            control_plane_url=None,
            audit_enabled=False,
            monitoring_enabled=False,
        ),
        event_publisher=publisher,
    )

    with TestClient(app) as client:
        response = client.post(
            "/predict/claims-risk",
            headers={"x-correlation-id": "corr-event-prediction"},
            json=valid_payload(),
        )

    assert response.status_code == 200
    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event.event_type == "prediction.created"
    assert event.schema_version == "1.0"
    assert event.correlation_id == "corr-event-prediction"
    assert event.payload["model_name"] == "claims-risk-rules-fallback"
    assert event.payload["feature_version"] == "features-test"
    assert event.payload["risk_band"] == response.json()["risk_band"]
    assert "feature_timestamp" not in event.payload["request_features_json"]


def test_prediction_route_emits_error_event_when_model_prediction_fails(
    monkeypatch,
    tmp_path,
) -> None:
    posts: list[dict] = []

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
            posts.append({"url": url, "json": json})
            return FakeResponse()

    monkeypatch.setattr("careai_inference_service.audit.httpx.Client", FakeClient)

    model_path = tmp_path / "claims-risk-failing.joblib"
    metadata_path = tmp_path / "model-metadata.json"
    joblib.dump(FailingProbabilityModel(), model_path)
    metadata_path.write_text(json.dumps({"name": "claims-risk", "version": "test"}))

    app = create_app(
        InferenceSettings(
            model_uri=str(model_path),
            model_metadata_path=str(metadata_path),
            feature_version="features-test",
            max_feature_age_minutes=60,
            control_plane_url="http://control-plane:8000",
            audit_enabled=True,
            monitoring_enabled=True,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/predict/claims-risk",
            headers={"x-correlation-id": "corr-route-error"},
            json=valid_payload(),
        )

    assert response.status_code == 200
    assert response.json()["fallback_mode"] is True
    error_post = next(post for post in posts if post["url"].endswith("/monitoring/error-events"))
    assert error_post["json"]["model_name"] == "claims-risk"
    assert error_post["json"]["model_version"] == "test"
    assert error_post["json"]["error_type"] == "model_prediction_failed"
    assert error_post["json"]["status_code"] == 200
    assert error_post["json"]["correlation_id"] == "corr-route-error"
