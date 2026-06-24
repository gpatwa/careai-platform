from careai_common.events import build_event
from careai_control_plane_api.database import Database
from careai_control_plane_api.event_consumer import consume_events
from careai_control_plane_api.models import (
    AuditEventORM,
    DriftSnapshotORM,
    EvaluationRunORM,
    PredictionEventORM,
)
from sqlalchemy import select


def test_event_consumer_materializes_monitoring_and_audit_records() -> None:
    database = Database("sqlite:///:memory:")
    database.prepare_schema()
    session_generator = database.session()
    session = next(session_generator)
    try:
        counts = consume_events(
            session,
            [
                build_event(
                    event_type="prediction.created",
                    source="inference-service",
                    subject="model/claims-risk",
                    correlation_id="corr-prediction",
                    payload={
                        "model_name": "claims-risk",
                        "model_version": "candidate-1",
                        "feature_version": "features-v1",
                        "request_features_json": {"age_bucket": "65+", "plan_type": "gold"},
                        "prediction_score": 0.81,
                        "risk_band": "high",
                        "latency_ms": 22,
                        "fallback_mode": False,
                    },
                ),
                build_event(
                    event_type="rag.query_answered",
                    source="rag-service",
                    subject="conversation/corr-rag",
                    correlation_id="corr-rag",
                    payload={
                        "user_id": "synthetic-user-001",
                        "role": "clinical_ops",
                        "prompt_template_id": "prompt-local",
                        "prompt_version": "local-v1",
                        "tenant_id": "payer-demo",
                        "retrieved_source_ids": ["prior_authorization_policy-0000"],
                        "model_name": "local-deterministic-rag",
                        "provider": "local-mock",
                        "safety_flags": ["verification_retry_used"],
                        "human_review_required": False,
                        "groundedness_score": 0.42,
                        "fallback_mode": True,
                        "attempt_count": 2,
                        "verification_passed": False,
                        "verification_flags": ["missing_inline_citations", "low_groundedness"],
                    },
                ),
                build_event(
                    event_type="model.drift_detected",
                    source="control-plane-api",
                    subject="model/claims-risk",
                    correlation_id="corr-drift",
                    payload={
                        "model_name": "claims-risk",
                        "model_version": "candidate-1",
                        "drift_status": "red",
                        "snapshot_id": "snapshot-001",
                        "rollback_recommended": True,
                        "metrics_json": {
                            "dashboard_contract": {
                                "training_serving_skew": {
                                    "baseline_count": 10,
                                    "recent_count": 3,
                                }
                            }
                        },
                    },
                ),
            ],
        )

        prediction = session.scalars(select(PredictionEventORM)).one()
        audits = list(session.scalars(select(AuditEventORM).order_by(AuditEventORM.action)))
        evaluation = session.scalars(select(EvaluationRunORM)).one()
        drift = session.scalars(select(DriftSnapshotORM)).one()
    finally:
        session_generator.close()

    assert counts == {
        "prediction.created": 1,
        "rag.query_answered": 1,
        "model.drift_detected": 1,
    }
    assert prediction.model_name == "claims-risk"
    assert prediction.risk_band == "high"
    assert len(audits) == 4
    audit = next(item for item in audits if item.action == "rag.query_answered")
    assert audit.action == "rag.query_answered"
    assert audit.metadata_json["event_type"] == "rag.query_answered"
    assert audit.metadata_json["attempt_count"] == 2
    assert audit.metadata_json["verification_passed"] is False
    improvements = [item for item in audits if item.action == "rag.improvement_candidate_detected"]
    assert len(improvements) == 3
    assert all(item.target_type == "prompt" for item in improvements)
    assert evaluation.target_type == "rag_online"
    assert evaluation.passed is False
    assert evaluation.metrics_json["attempt_count"] == 2
    assert drift.id == "snapshot-001"
    assert drift.drift_status == "red"
    assert drift.baseline_count == 10
    assert drift.recent_count == 3
