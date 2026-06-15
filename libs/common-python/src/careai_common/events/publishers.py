import json
import logging
import os
from pathlib import Path
from typing import Protocol

from careai_common.events.schemas import EventEnvelope

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> bool:
        """Publish an event envelope to a local or cloud-backed event bus."""


class DisabledEventPublisher:
    def publish(self, event: EventEnvelope) -> bool:
        return False


class LocalLoggingEventPublisher:
    """Local-first publisher that logs safe metadata and optionally appends JSONL."""

    def __init__(self, event_stream_path: str | None = None) -> None:
        self.events: list[EventEnvelope] = []
        self.event_stream_path = Path(event_stream_path) if event_stream_path else None

    def publish(self, event: EventEnvelope) -> bool:
        self.events.append(event)
        logger.info(
            "event published locally",
            extra={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "event_schema_version": event.schema_version,
                "source": event.source,
                "subject": event.subject,
                "correlation_id": event.correlation_id,
            },
        )
        if self.event_stream_path:
            self.event_stream_path.parent.mkdir(parents=True, exist_ok=True)
            with self.event_stream_path.open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
        return True


class AzureEventHubsPublisher:
    """Azure Event Hubs publisher with connection-string or managed-identity auth."""

    def __init__(
        self,
        *,
        eventhub_name: str,
        connection_string: str | None = None,
        fully_qualified_namespace: str | None = None,
    ) -> None:
        self.eventhub_name = eventhub_name
        self.connection_string = connection_string
        self.fully_qualified_namespace = fully_qualified_namespace

    def publish(self, event: EventEnvelope) -> bool:
        event_data = self._event_data(event)
        event_data.properties = {
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "correlation_id": event.correlation_id,
        }
        with self._create_producer() as producer:
            batch = producer.create_batch()
            batch.add(event_data)
            producer.send_batch(batch)
        return True

    def _create_producer(self):
        try:
            from azure.eventhub import EventHubProducerClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-eventhub is required when Azure Event Hubs publishing is configured"
            ) from exc

        if self.connection_string:
            return EventHubProducerClient.from_connection_string(
                conn_str=self.connection_string,
                eventhub_name=self.eventhub_name,
            )

        if self.fully_qualified_namespace:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise RuntimeError(
                    "azure-identity is required for managed-identity Event Hubs publishing"
                ) from exc
            return EventHubProducerClient(
                fully_qualified_namespace=self.fully_qualified_namespace,
                eventhub_name=self.eventhub_name,
                credential=DefaultAzureCredential(),
            )

        raise RuntimeError("Event Hubs publisher requires connection string or namespace")

    def _event_data(self, event: EventEnvelope):
        from azure.eventhub import EventData

        return EventData(json.dumps(event.model_dump(mode="json"), sort_keys=True))


def event_publisher_from_env(source: str) -> EventPublisher:
    if os.getenv("EVENT_PUBLISHING_ENABLED", "true").lower() != "true":
        return DisabledEventPublisher()

    eventhub_name = os.getenv("AZURE_EVENTHUB_NAME") or os.getenv("AZURE_EVENT_HUB_NAME")
    connection_string = os.getenv("AZURE_EVENTHUB_CONNECTION_STRING") or os.getenv(
        "AZURE_EVENT_HUB_CONNECTION_STRING"
    )
    namespace = os.getenv("AZURE_EVENTHUB_FULLY_QUALIFIED_NAMESPACE") or os.getenv(
        "AZURE_EVENT_HUB_FULLY_QUALIFIED_NAMESPACE"
    )

    if eventhub_name and (connection_string or namespace):
        logger.info(
            "Azure Event Hubs publisher configured",
            extra={"source": source, "eventhub_name": eventhub_name},
        )
        return AzureEventHubsPublisher(
            eventhub_name=eventhub_name,
            connection_string=connection_string,
            fully_qualified_namespace=namespace,
        )

    return LocalLoggingEventPublisher(event_stream_path=os.getenv("EVENT_STREAM_LOCAL_PATH"))


def read_local_event_stream(event_stream_path: str | Path) -> list[EventEnvelope]:
    path = Path(event_stream_path)
    if not path.exists():
        return []

    events: list[EventEnvelope] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            stripped = line.strip()
            if stripped:
                events.append(EventEnvelope.model_validate_json(stripped))
    return events
