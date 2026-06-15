from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from careai_common.correlation import ensure_correlation_id


class AuditActor(BaseModel):
    """Actor metadata that avoids raw PHI/PII-like values."""

    actor_id: str = Field(..., examples=["demo-user"])
    actor_type: str = Field(default="user", examples=["user", "service"])
    roles: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """Audit event schema shared by platform services."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    action: str
    outcome: str = "success"
    actor: AuditActor
    resource_type: str
    resource_id: str
    correlation_id: str = Field(default_factory=ensure_correlation_id)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
