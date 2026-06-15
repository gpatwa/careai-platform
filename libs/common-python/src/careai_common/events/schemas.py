from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

EVENT_SCHEMA_VERSION = "1.0"

EventType = Literal[
    "prediction.created",
    "audit.created",
    "model.drift_detected",
    "model.promotion_requested",
    "rag.query_answered",
    "feedback.received",
]

RiskBand = Literal["low", "medium", "high"]
DriftStatus = Literal["green", "yellow", "red"]
ModelStage = Literal["dev", "candidate", "staging", "approved", "production", "deprecated"]
FeedbackRating = Literal["positive", "negative", "neutral"]


class EventPayload(BaseModel):
    schema_version: str = Field(default=EVENT_SCHEMA_VERSION)


class PredictionCreatedPayload(EventPayload):
    model_name: str
    model_version: str
    feature_version: str
    request_features_json: dict[str, Any] = Field(default_factory=dict)
    prediction_score: float = Field(..., ge=0, le=1)
    risk_band: RiskBand
    latency_ms: int = Field(..., ge=0)
    fallback_mode: bool = False


class AuditCreatedPayload(EventPayload):
    actor: str
    action: str
    target_type: str
    target_id: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelDriftDetectedPayload(EventPayload):
    model_name: str
    model_version: str
    drift_status: DriftStatus
    snapshot_id: str | None = None
    rollback_recommended: bool
    metrics_json: dict[str, Any] = Field(default_factory=dict)


class ModelPromotionRequestedPayload(EventPayload):
    model_id: str
    model_name: str
    model_version: str
    from_stage: ModelStage
    to_stage: ModelStage
    requested_by: str
    notes: str = ""


class RagQueryAnsweredPayload(EventPayload):
    user_id: str
    role: str
    prompt_template_id: str
    prompt_version: str
    retrieved_source_ids: list[str] = Field(default_factory=list)
    model_name: str
    provider: str
    safety_flags: list[str] = Field(default_factory=list)
    human_review_required: bool
    groundedness_score: float = Field(..., ge=0, le=1)
    fallback_mode: bool = False


class FeedbackReceivedPayload(EventPayload):
    feedback_id: str
    target_type: str
    target_id: str
    rating: FeedbackRating
    submitted_by: str
    notes_category: str = ""
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    schema_version: str = Field(default=EVENT_SCHEMA_VERSION)
    source: str
    subject: str
    correlation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any]


PAYLOAD_MODELS: dict[EventType, type[EventPayload]] = {
    "prediction.created": PredictionCreatedPayload,
    "audit.created": AuditCreatedPayload,
    "model.drift_detected": ModelDriftDetectedPayload,
    "model.promotion_requested": ModelPromotionRequestedPayload,
    "rag.query_answered": RagQueryAnsweredPayload,
    "feedback.received": FeedbackReceivedPayload,
}


def validate_payload(event_type: EventType, payload: dict[str, Any]) -> dict[str, Any]:
    return PAYLOAD_MODELS[event_type](**payload).model_dump(mode="json")


def build_event(
    *,
    event_type: EventType,
    source: str,
    subject: str,
    correlation_id: str,
    payload: dict[str, Any],
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source=source,
        subject=subject,
        correlation_id=correlation_id,
        payload=validate_payload(event_type, payload),
    )
