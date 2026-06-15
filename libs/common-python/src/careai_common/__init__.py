"""Shared utilities for careai-platform services."""

from careai_common.audit import AuditActor, AuditEvent
from careai_common.config import AppSettings, load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from careai_common.errors import CareAIError, ConfigurationError, DependencyUnavailableError
from careai_common.logging import setup_json_logging

__all__ = [
    "AppSettings",
    "AuditActor",
    "AuditEvent",
    "CareAIError",
    "ConfigurationError",
    "DependencyUnavailableError",
    "clear_correlation_id",
    "ensure_correlation_id",
    "get_correlation_id",
    "load_settings",
    "set_correlation_id",
    "setup_json_logging",
]

