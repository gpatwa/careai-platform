import json
import logging
from datetime import UTC, datetime
from typing import Any

from careai_common.correlation import get_correlation_id

SENSITIVE_KEYS = {
    "authorization",
    "connection_string",
    "credential",
    "password",
    "secret",
    "token",
}

RESERVED_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str, environment: str = "local") -> None:
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in RESERVED_LOG_RECORD_KEYS and not key.startswith("_")
        }
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service_name": self.service_name,
            "service": self.service_name,
            "environment": self.environment,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
            "extra": _redact(extras),
        }
        for field_name in ("actor", "model_version", "prompt_version"):
            if field_name in extras:
                payload[field_name] = _redact(extras[field_name])
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_redact(payload), separators=(",", ":"))


def setup_json_logging(
    service_name: str,
    level: str = "INFO",
    environment: str = "local",
) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service_name=service_name, environment=environment))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
