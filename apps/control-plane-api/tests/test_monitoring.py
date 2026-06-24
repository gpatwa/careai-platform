from careai_control_plane_api.main import create_app
from careai_control_plane_api.monitoring import (
    calculate_drift,
    feature_distribution,
    slo_status,
)
from fastapi.testclient import TestClient


def make_client() -> TestClient:
    return TestClient(create_app(database_url="sqlite:///:memory:"))


def synthetic_features(age_bucket: str = "65+", plan_type: str = "medicare_advantage") -> dict:
    return {
        "age_bucket": age_bucket,
        "plan_type": plan_type,
        "prior_claim_count": 8,
        "recent_visit_count": 4,
        "medication_count": 6,
        "chronic_condition_count": 3,
        "region_code": "R03",
    }


def test_drift_calculation_is_deterministic() -> None:
    baseline = feature_distribution(
        [
            synthetic_features("18-34", "gold"),
            synthetic_features("18-34", "gold"),
            synthetic_features("35-49", "silver"),
            synthetic_features("35-49", "silver"),
        ]
    )
    recent = feature_distribution(
        [
            synthetic_features("65+", "medicare_advantage"),
            synthetic_features("65+", "medicare_advantage"),
            synthetic_features("65+", "medicare_advantage"),
            synthetic_features("65+", "medicare_advantage"),
        ]
    )

    first_status, first_metrics = calculate_drift(
        baseline_distribution=baseline,
        recent_distribution=recent,
    )
    second_status, second_metrics = calculate_drift(
        baseline_distribution=baseline,
        recent_distribution=recent,
    )

    assert first_status == "red"
    assert first_status == second_status
    assert first_metrics == second_metrics
    assert any(metric["feature_name"] == "age_bucket" for metric in first_metrics)
    assert baseline["prior_claim_count"] == {"6-10": 1.0}
    assert recent["medication_count"] == {"6-10": 1.0}


def test_slo_status_uses_error_rate_and_latency_thresholds() -> None:
    assert (
        slo_status(
            event_count=0,
            error_rate=0,
            p95_latency_ms=None,
            error_rate_slo=0.02,
            latency_slo_ms=750,
        )
        == "unknown"
    )
    assert (
        slo_status(
            event_count=10,
            error_rate=0.03,
            p95_latency_ms=100,
            error_rate_slo=0.02,
            latency_slo_ms=750,
        )
        == "breached"
    )
    assert (
        slo_status(
            event_count=10,
            error_rate=0.0,
            p95_latency_ms=800,
            error_rate_slo=0.02,
            latency_slo_ms=750,
        )
        == "breached"
    )
    assert (
        slo_status(
            event_count=10,
            error_rate=0.0,
            p95_latency_ms=120,
            error_rate_slo=0.02,
            latency_slo_ms=750,
        )
        == "healthy"
    )


def test_prediction_event_persistence_drift_check_and_summary() -> None:
    baseline_records = [
        synthetic_features("18-34", "gold"),
        synthetic_features("18-34", "gold"),
        synthetic_features("35-49", "silver"),
        synthetic_features("35-49", "silver"),
    ]

    with make_client() as client:
        model_response = client.post(
            "/models",
            json={
                "name": "claims-risk",
                "version": "test",
                "framework": "scikit-learn",
                "artifact_uri": "file:///tmp/synthetic-model",
                "training_dataset_id": "synthetic-dataset",
                "metrics_json": {"auc": 0.9},
                "lineage_json": {
                    "baseline_feature_distribution": feature_distribution(baseline_records),
                    "baseline_feature_count": len(baseline_records),
                },
                "stage": "candidate",
            },
        )
        assert model_response.status_code == 201

        for index in range(3):
            event_response = client.post(
                "/monitoring/prediction-events",
                json={
                    "model_name": "claims-risk",
                    "model_version": "test",
                    "request_features_json": synthetic_features(),
                    "prediction_score": 0.82 + index / 100,
                    "risk_band": "high",
                    "latency_ms": 20 + index,
                    "correlation_id": f"corr-monitoring-{index}",
                },
            )
            assert event_response.status_code == 201

        error_response = client.post(
            "/monitoring/error-events",
            json={
                "model_name": "claims-risk",
                "model_version": "test",
                "error_type": "model_prediction_failed",
                "error_message": "Model prediction failed; deterministic fallback score returned.",
                "status_code": 200,
                "latency_ms": 44,
                "correlation_id": "corr-monitoring-error",
            },
        )
        assert error_response.status_code == 201

        events_response = client.get("/monitoring/models/claims-risk/events")
        error_events_response = client.get("/monitoring/models/claims-risk/error-events")
        drift_response = client.post(
            "/monitoring/models/claims-risk/drift-check",
            json={"minimum_events": 3},
        )
        summary_response = client.get("/monitoring/models/claims-risk/summary")
        audit_response = client.get("/audit-events")

    assert events_response.status_code == 200
    assert len(events_response.json()) == 3
    assert error_events_response.status_code == 200
    assert len(error_events_response.json()) == 1
    assert drift_response.status_code == 200
    drift_body = drift_response.json()
    assert drift_body["drift_status"] == "red"
    assert drift_body["rollback_recommended"] is True
    assert drift_body["baseline_count"] == 4
    assert drift_body["recent_count"] == 3
    assert drift_body["dashboard_contract"]["schema_version"] == "model-drift-v1"

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["event_count"] == 3
    assert summary["error_count"] == 1
    assert summary["error_rate"] == 0.25
    assert summary["slo_status"] == "breached"
    assert summary["latency_slo_ms"] == 750
    assert summary["error_rate_slo"] == 0.02
    assert summary["risk_band_counts"]["high"] == 3
    assert summary["latest_drift_status"] == "red"
    assert summary["dashboard_contract"]["schema_version"] == "monitoring-dashboard-v1"
    assert summary["dashboard_contract"]["slos"]["error_rate"] == 0.02

    audit_actions = {event["action"] for event in audit_response.json()}
    assert {
        "prediction_event.ingested",
        "model_error_event.ingested",
        "drift_check.completed",
    } <= audit_actions


def test_rag_improvement_summary_surfaces_loop_engineering_signals() -> None:
    with make_client() as client:
        response = client.post(
            "/audit-events",
            json={
                "actor": "synthetic-user-001",
                "action": "rag.query_answered",
                "target_type": "rag_query",
                "target_id": "corr-rag-001",
                "correlation_id": "corr-rag-001",
                "metadata_json": {
                    "prompt_template_id": "prompt-001",
                    "prompt_version": "v2",
                    "retrieved_source_ids": ["prior_authorization_policy-0000"],
                    "model_name": "local-rag",
                    "provider": "local-mock",
                    "safety_flags": ["verification_retry_used"],
                    "human_review_required": False,
                    "groundedness_score": 0.41,
                    "fallback_mode": True,
                    "attempt_count": 2,
                    "verification_passed": False,
                    "verification_flags": ["missing_inline_citations", "low_groundedness"],
                },
            },
        )
        assert response.status_code == 201

        eval_response = client.post(
            "/evaluations",
            json={
                "target_type": "rag",
                "target_id": "prompt-001",
                "metrics_json": {"groundedness": 0.41},
                "passed": False,
                "report_uri": "file:///tmp/rag-eval-report.json",
            },
        )
        assert eval_response.status_code == 201

        summary_response = client.get("/monitoring/rag/improvement-summary")

    assert summary_response.status_code == 200
    body = summary_response.json()
    assert body["total_queries"] == 1
    assert body["retry_rate"] == 1.0
    assert body["verification_failure_rate"] == 1.0
    assert body["failed_eval_count"] == 1
    categories = {item["category"] for item in body["recommendations"]}
    assert {"prompt_and_grader", "citation_policy", "provider_operations"} <= categories
