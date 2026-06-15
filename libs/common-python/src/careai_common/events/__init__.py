from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class EventEnvelope:
    event_type: str
    source: str
    payload: dict[str, Any]
    correlation_id: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> bool:
        """Publish an event envelope to a local or cloud-backed event bus."""


class InMemoryEventPublisher:
    """Event Hubs-compatible test double for local-first demos."""

    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    def publish(self, event: EventEnvelope) -> bool:
        self.events.append(event)
        return True


class DisabledEventPublisher:
    def publish(self, event: EventEnvelope) -> bool:
        return False
