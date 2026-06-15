import json
import logging

from careai_common.audit import AuditActor, AuditEvent
from careai_common.config import load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.logging import setup_json_logging


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


def test_json_logging_redacts_sensitive_keys() -> None:
    setup_json_logging("test-service")

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

    rendered = logging.getLogger().handlers[0].formatter.format(record)
    payload = json.loads(rendered)
    assert payload["service"] == "test-service"
    assert payload["message"] == "configured"
    assert payload["extra"]["password"] == "[REDACTED]"
