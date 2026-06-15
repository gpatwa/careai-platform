import json
import logging

from careai_common.audit import AuditActor, AuditEvent
from careai_common.config import AppSettings, load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.events import EventEnvelope, InMemoryEventPublisher
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


def test_in_memory_event_publisher_captures_envelopes() -> None:
    publisher = InMemoryEventPublisher()
    event = EventEnvelope(
        event_type="prediction.created",
        source="inference-service",
        payload={"model_name": "claims-risk"},
        correlation_id="corr-event",
    )

    assert publisher.publish(event) is True
    assert publisher.events == [event]
