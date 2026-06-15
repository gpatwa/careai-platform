import argparse
import json
import logging
from collections import Counter
from collections.abc import Iterable
from typing import Any

from careai_common.events import EventEnvelope, read_local_event_stream
from sqlalchemy.orm import Session

from careai_control_plane_api.database import Database
from careai_control_plane_api.models import AuditEventORM, DriftSnapshotORM, PredictionEventORM

logger = logging.getLogger(__name__)


def consume_events(session: Session, events: Iterable[EventEnvelope]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        if event.event_type == "prediction.created":
            _consume_prediction_created(session, event)
        elif event.event_type == "audit.created":
            _consume_audit_created(session, event)
        elif event.event_type == "model.drift_detected":
            _consume_model_drift_detected(session, event)
        elif event.event_type == "model.promotion_requested":
            _consume_model_promotion_requested(session, event)
        elif event.event_type == "rag.query_answered":
            _consume_rag_query_answered(session, event)
        elif event.event_type == "feedback.received":
            _consume_feedback_received(session, event)
        else:
            logger.warning("unknown event type skipped", extra={"event_type": event.event_type})
            counts["skipped"] += 1
            continue

        counts[event.event_type] += 1

    session.commit()
    return dict(counts)


def consume_local_event_stream_once(
    *,
    database_url: str | None,
    event_stream_path: str,
    create_schema: bool = True,
    limit: int | None = None,
) -> dict[str, int]:
    database = Database(database_url)
    if create_schema:
        database.prepare_schema()

    events = read_local_event_stream(event_stream_path)
    if limit is not None:
        events = events[:limit]

    session_generator = database.session()
    session = next(session_generator)
    try:
        return consume_events(session, events)
    finally:
        session_generator.close()


def _consume_prediction_created(session: Session, event: EventEnvelope) -> None:
    payload = event.payload
    session.add(
        PredictionEventORM(
            model_name=str(payload["model_name"]),
            model_version=str(payload["model_version"]),
            request_features_json=dict(payload.get("request_features_json", {})),
            prediction_score=float(payload["prediction_score"]),
            risk_band=str(payload["risk_band"]),
            latency_ms=int(payload["latency_ms"]),
            correlation_id=event.correlation_id,
        )
    )


def _consume_audit_created(session: Session, event: EventEnvelope) -> None:
    payload = event.payload
    session.add(
        AuditEventORM(
            actor=str(payload["actor"]),
            action=str(payload["action"]),
            target_type=str(payload["target_type"]),
            target_id=str(payload["target_id"]),
            correlation_id=event.correlation_id,
            metadata_json=_metadata_with_event_id(event, payload.get("metadata_json", {})),
        )
    )


def _consume_model_drift_detected(session: Session, event: EventEnvelope) -> None:
    payload = event.payload
    metrics_json = dict(payload.get("metrics_json", {}))
    dashboard_contract = metrics_json.get("dashboard_contract", {})
    skew = dashboard_contract.get("training_serving_skew", {})
    snapshot_kwargs: dict[str, Any] = {}
    if payload.get("snapshot_id"):
        snapshot_kwargs["id"] = str(payload["snapshot_id"])

    session.add(
        DriftSnapshotORM(
            **snapshot_kwargs,
            model_name=str(payload["model_name"]),
            model_version=str(payload["model_version"]),
            drift_status=str(payload["drift_status"]),
            metrics_json=_metadata_with_event_id(event, metrics_json),
            baseline_count=int(skew.get("baseline_count", 0)),
            recent_count=int(skew.get("recent_count", 0)),
            correlation_id=event.correlation_id,
        )
    )


def _consume_model_promotion_requested(session: Session, event: EventEnvelope) -> None:
    payload = event.payload
    session.add(
        AuditEventORM(
            actor=str(payload["requested_by"]),
            action="model.promotion_requested",
            target_type="model",
            target_id=str(payload["model_id"]),
            correlation_id=event.correlation_id,
            metadata_json=_metadata_with_event_id(
                event,
                {
                    "model_name": payload["model_name"],
                    "model_version": payload["model_version"],
                    "from_stage": payload["from_stage"],
                    "to_stage": payload["to_stage"],
                    "notes": payload.get("notes", ""),
                },
            ),
        )
    )


def _consume_rag_query_answered(session: Session, event: EventEnvelope) -> None:
    payload = event.payload
    session.add(
        AuditEventORM(
            actor=str(payload["user_id"]),
            action="rag.query_answered",
            target_type="rag_query",
            target_id=event.correlation_id,
            correlation_id=event.correlation_id,
            metadata_json=_metadata_with_event_id(
                event,
                {
                    "role": payload["role"],
                    "prompt_template_id": payload["prompt_template_id"],
                    "prompt_version": payload["prompt_version"],
                    "retrieved_source_ids": payload.get("retrieved_source_ids", []),
                    "model_name": payload["model_name"],
                    "provider": payload["provider"],
                    "safety_flags": payload.get("safety_flags", []),
                    "human_review_required": payload["human_review_required"],
                    "groundedness_score": payload["groundedness_score"],
                    "fallback_mode": payload.get("fallback_mode", False),
                },
            ),
        )
    )


def _consume_feedback_received(session: Session, event: EventEnvelope) -> None:
    payload = event.payload
    session.add(
        AuditEventORM(
            actor=str(payload["submitted_by"]),
            action="feedback.received",
            target_type=str(payload["target_type"]),
            target_id=str(payload["target_id"]),
            correlation_id=event.correlation_id,
            metadata_json=_metadata_with_event_id(
                event,
                {
                    "feedback_id": payload["feedback_id"],
                    "rating": payload["rating"],
                    "notes_category": payload.get("notes_category", ""),
                    "metadata_json": payload.get("metadata_json", {}),
                },
            ),
        )
    )


def _metadata_with_event_id(event: EventEnvelope, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        **metadata,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "event_schema_version": event.schema_version,
        "event_source": event.source,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Consume local careai event stream once.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--event-stream-path", default="data/local/event-stream.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    result = consume_local_event_stream_once(
        database_url=args.database_url,
        event_stream_path=args.event_stream_path,
        limit=args.limit,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
