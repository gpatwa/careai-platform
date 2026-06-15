import json
import logging

from careai_common.audit import AuditActor, AuditEvent
from careai_common.config import AppSettings, load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.events import LocalLoggingEventPublisher, build_event, read_local_event_stream
from careai_common.logging import setup_json_logging
from careai_common.observability import configure_application_insights


def test_load_settings_defaults() -> None:
    settings = load_settings("demo-service", 8080)

    assert settings.service_name == "demo-service"
    assert settings.service_port == 8080
    assert settings.environment == "local"


def test_correlation_id_can_be_set_and_used_by_audit_event() -> None:
    token = set_correlation_id("test-correlation-id")
    try:
        event = AuditEvent(
            event_type="model.promoted",
            action="promote",
            actor=AuditActor(actor_id="demo-user", roles=["ml-operator"]),
            resource_type="model",
            resource_id="claims-risk:champion",
        )

        assert event.correlation_id == "test-correlation-id"
    finally:
        clear_correlation_id(token)


def test_json_logging_redacts_sensitive_keys_and_promotes_enterprise_fields() -> None:
    setup_json_logging("test-service", environment="unit-test")

    ensure_correlation_id()
    record = logging.LogRecord(
        name="careai.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="configured",
        args=(),
        exc_info=None,
    )
    record.password = "do-not-log"
    record.actor = "synthetic-operator"
    record.model_version = "1.2.3"

    rendered = logging.getLogger().handlers[0].formatter.format(record)
    payload = json.loads(rendered)
    assert payload["service_name"] == "test-service"
    assert payload["service"] == "test-service"
    assert payload["environment"] == "unit-test"
    assert payload["message"] == "configured"
    assert payload["actor"] == "synthetic-operator"
    assert payload["model_version"] == "1.2.3"
    assert payload["extra"]["password"] == "[REDACTED]"


def test_application_insights_is_optional_without_connection_string(monkeypatch) -> None:
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    settings = load_settings("demo-service", 8080)

    assert configure_application_insights(settings) is False


def test_application_insights_configures_exporter_when_connection_string(monkeypatch) -> None:
    calls: list[str] = []

    def fake_configure_azure_monitor(*, connection_string: str) -> None:
        calls.append(connection_string)

    monkeypatch.setattr(
        "careai_common.observability.configure_azure_monitor",
        fake_configure_azure_monitor,
    )
    settings = AppSettings(
        service_name="demo-service",
        service_port=8080,
        applicationinsights_connection_string=(
            "InstrumentationKey=00000000-0000-0000-0000-000000000000;"
            "IngestionEndpoint=https://example.invalid/"
        ),
    )

    assert configure_application_insights(settings) is True
    assert calls == [settings.applicationinsights_connection_string]


def test_local_event_publisher_captures_and_writes_envelopes(tmp_path) -> None:
    stream_path = tmp_path / "event-stream.jsonl"
    publisher = LocalLoggingEventPublisher(str(stream_path))
    event = build_event(
        event_type="prediction.created",
        source="inference-service",
        subject="model/claims-risk",
        correlation_id="corr-event",
        payload={
            "model_name": "claims-risk",
            "model_version": "test",
            "feature_version": "features-v1",
            "request_features_json": {"age_bucket": "65+"},
            "prediction_score": 0.8,
            "risk_band": "high",
            "latency_ms": 12,
            "fallback_mode": False,
        },
    )

    assert publisher.publish(event) is True
    assert publisher.events == [event]
    streamed = read_local_event_stream(stream_path)
    assert streamed == [event]
    assert streamed[0].schema_version == "1.0"
    assert streamed[0].payload["schema_version"] == "1.0"


def test_event_schema_contracts_cover_supported_event_types() -> None:
    examples = [
        (
            "prediction.created",
            {
                "model_name": "claims-risk",
                "model_version": "test",
                "feature_version": "features-v1",
                "request_features_json": {"plan_type": "gold"},
                "prediction_score": 0.7,
                "risk_band": "medium",
                "latency_ms": 10,
                "fallback_mode": False,
            },
        ),
        (
            "audit.created",
            {
                "actor": "synthetic-operator",
                "action": "model.promoted",
                "target_type": "model",
                "target_id": "model-001",
                "metadata_json": {"stage": "candidate"},
            },
        ),
        (
            "model.drift_detected",
            {
                "model_name": "claims-risk",
                "model_version": "test",
                "drift_status": "yellow",
                "snapshot_id": "snapshot-001",
                "rollback_recommended": False,
                "metrics_json": {},
            },
        ),
        (
            "model.promotion_requested",
            {
                "model_id": "model-001",
                "model_name": "claims-risk",
                "model_version": "test",
                "from_stage": "candidate",
                "to_stage": "staging",
                "requested_by": "model-risk-reviewer",
                "notes": "Synthetic gate passed.",
            },
        ),
        (
            "rag.query_answered",
            {
                "user_id": "synthetic-user-001",
                "role": "clinical_ops",
                "prompt_template_id": "prompt-001",
                "prompt_version": "v1",
                "retrieved_source_ids": ["source-001"],
                "model_name": "local-deterministic-rag",
                "provider": "local-mock",
                "safety_flags": [],
                "human_review_required": False,
                "groundedness_score": 0.8,
                "fallback_mode": True,
            },
        ),
        (
            "feedback.received",
            {
                "feedback_id": "feedback-001",
                "target_type": "rag_answer",
                "target_id": "corr-rag",
                "rating": "positive",
                "submitted_by": "synthetic-user-001",
                "notes_category": "helpful",
                "metadata_json": {},
            },
        ),
    ]

    events = [
        build_event(
            event_type=event_type,
            source="unit-test",
            subject=f"test/{index}",
            correlation_id=f"corr-{index}",
            payload=payload,
        )
        for index, (event_type, payload) in enumerate(examples)
    ]

    assert [event.event_type for event in events] == [
        "prediction.created",
        "audit.created",
        "model.drift_detected",
        "model.promotion_requested",
        "rag.query_answered",
        "feedback.received",
    ]
    assert all(event.schema_version == "1.0" for event in events)
    assert all(event.payload["schema_version"] == "1.0" for event in events)
