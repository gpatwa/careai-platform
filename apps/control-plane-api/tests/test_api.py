from careai_control_plane_api.main import create_app
from fastapi.testclient import TestClient


def make_client() -> TestClient:
    return TestClient(create_app(database_url="sqlite:///:memory:"))


def test_openapi_includes_control_plane_tags() -> None:
    with make_client() as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    tag_names = {tag["name"] for tag in response.json()["tags"]}
    expected_tags = {
        "Datasets",
        "Models",
        "Deployments",
        "Prompts",
        "Evaluations",
        "Approvals",
        "Governance",
        "Audit",
        "Monitoring",
    }
    assert expected_tags <= tag_names


def test_create_dataset_model_and_promote_model_writes_audit_events() -> None:
    with make_client() as client:
        dataset_response = client.post(
            "/datasets",
            headers={"x-correlation-id": "corr-dataset", "x-actor": "data-steward"},
            json={
                "name": "synthetic-claims",
                "version": "2026.06",
                "owner": "platform-demo",
                "schema_uri": "azurite://schemas/claims.json",
                "storage_uri": "azurite://datasets/synthetic-claims",
                "pii_classification": "synthetic-no-phi",
            },
        )
        assert dataset_response.status_code == 201
        assert dataset_response.headers["x-correlation-id"] == "corr-dataset"
        dataset_id = dataset_response.json()["id"]

        model_response = client.post(
            "/models",
            headers={"x-correlation-id": "corr-model", "x-actor": "ml-engineer"},
            json={
                "name": "claims-risk",
                "version": "0.1.0",
                "framework": "scikit-learn",
                "artifact_uri": "azurite://models/claims-risk/0.1.0",
                "training_dataset_id": dataset_id,
                "metrics_json": {"auc": 0.91},
                "lineage_json": {"run_id": "demo-run-001"},
                "stage": "dev",
            },
        )
        assert model_response.status_code == 201
        model_id = model_response.json()["id"]

        get_model_response = client.get(f"/models/{model_id}")
        assert get_model_response.status_code == 200
        assert get_model_response.json()["stage"] == "dev"

        promote_response = client.post(
            f"/models/{model_id}/promote",
            headers={"x-correlation-id": "corr-promote"},
            json={
                "stage": "approved",
                "actor": "model-risk-reviewer",
                "notes": "Synthetic eval passed.",
            },
        )
        assert promote_response.status_code == 200
        assert promote_response.json()["stage"] == "approved"

        audit_response = client.get("/audit-events")

    assert audit_response.status_code == 200
    audit_events = audit_response.json()
    actions = {event["action"] for event in audit_events}
    assert {"dataset.created", "model.created", "model.promoted"} <= actions
    promote_audit = next(event for event in audit_events if event["action"] == "model.promoted")
    assert promote_audit["actor"] == "model-risk-reviewer"
    assert promote_audit["correlation_id"] == "corr-promote"
    assert promote_audit["metadata_json"]["to_stage"] == "approved"


def test_create_and_list_deployments_prompts_evaluations_and_approvals() -> None:
    with make_client() as client:
        deployment_response = client.post(
            "/deployments",
            json={
                "model_id": "model-demo-id",
                "environment": "staging",
                "deployment_type": "canary",
                "endpoint_url": "http://localhost:8001/predict",
                "traffic_percent": 25,
                "status": "active",
            },
        )
        prompt_response = client.post(
            "/prompts",
            json={
                "name": "benefits-summary",
                "version": "0.1.0",
                "template_text": "Summarize the synthetic member benefits context: {context}",
                "owner": "llm-platform",
                "safety_notes": "No real member data. Require grounded answer.",
                "status": "candidate",
            },
        )
        evaluation_response = client.post(
            "/evaluations",
            json={
                "target_type": "prompt",
                "target_id": "prompt-demo-id",
                "metrics_json": {"groundedness": 0.97, "toxicity": 0.0},
                "passed": True,
                "report_uri": "azurite://reports/evaluations/prompt-demo-id.json",
            },
        )
        approval_response = client.post(
            "/approvals",
            json={
                "target_type": "model",
                "target_id": "model-demo-id",
                "approver": "clinical-governance",
                "decision": "approved",
                "notes": "Synthetic governance approval.",
            },
        )

        assert deployment_response.status_code == 201
        assert prompt_response.status_code == 201
        assert evaluation_response.status_code == 201
        assert approval_response.status_code == 201

        assert len(client.get("/deployments").json()) == 1
        assert len(client.get("/prompts").json()) == 1
        assert len(client.get("/evaluations").json()) == 1
        assert len(client.get("/approvals").json()) == 1

        audit_actions = {event["action"] for event in client.get("/audit-events").json()}

    assert {
        "deployment.created",
        "prompt.created",
        "evaluation.created",
        "approval.created",
    } <= audit_actions


def create_demo_model(client: TestClient) -> str:
    dataset_response = client.post(
        "/datasets",
        json={
            "name": "synthetic-claims",
            "version": "2026.06",
            "owner": "platform-demo",
            "schema_uri": "azurite://schemas/claims.json",
            "storage_uri": "azurite://datasets/synthetic-claims",
            "pii_classification": "synthetic-no-phi",
        },
    )
    dataset_id = dataset_response.json()["id"]
    model_response = client.post(
        "/models",
        json={
            "name": "claims-risk",
            "version": "0.1.0",
            "framework": "scikit-learn",
            "artifact_uri": "azurite://models/claims-risk/0.1.0",
            "training_dataset_id": dataset_id,
            "metrics_json": {"auc": 0.91},
            "lineage_json": {"run_id": "demo-run-001"},
            "stage": "approved",
        },
    )
    return model_response.json()["id"]


def approved_model_card_payload(model_id: str) -> dict:
    return {
        "model_id": model_id,
        "intended_use": "Synthetic claims-risk triage for operations demos.",
        "prohibited_use": "Do not use for real clinical or coverage decisions.",
        "training_data_summary": "Deterministic synthetic claims-like features only.",
        "metrics_summary": {"auc": 0.91, "f1": 0.82},
        "fairness_summary": {"age_bucket": "Synthetic segment review completed."},
        "explainability_summary": "Reason codes are derived from utilization features.",
        "owner": "ml-platform",
        "reviewer": "model-risk-reviewer",
        "approval_status": "approved",
    }


def test_model_production_gate_requires_approved_card_and_approval() -> None:
    with make_client() as client:
        model_id = create_demo_model(client)

        blocked_without_card = client.post(
            f"/models/{model_id}/promote",
            json={
                "stage": "production",
                "actor": "model-risk-reviewer",
                "notes": "Attempt production before governance controls.",
            },
        )
        assert blocked_without_card.status_code == 409
        assert "approved_model_card" in blocked_without_card.json()["detail"]["missing_controls"]

        card_response = client.post("/model-cards", json=approved_model_card_payload(model_id))
        assert card_response.status_code == 201

        blocked_without_approval = client.post(
            f"/models/{model_id}/promote",
            json={
                "stage": "production",
                "actor": "model-risk-reviewer",
                "notes": "Attempt production before approval record.",
            },
        )
        assert blocked_without_approval.status_code == 409
        assert (
            "approved_model_governance_decision"
            in blocked_without_approval.json()["detail"]["missing_controls"]
        )

        approval_response = client.post(
            "/approvals",
            json={
                "target_type": "model",
                "target_id": model_id,
                "approver": "model-risk-reviewer",
                "decision": "approved",
                "notes": "Responsible AI card reviewed.",
            },
        )
        assert approval_response.status_code == 201

        promoted_response = client.post(
            f"/models/{model_id}/promote",
            json={
                "stage": "production",
                "actor": "model-risk-reviewer",
                "notes": "Governance controls are complete.",
            },
        )
        card_read_response = client.get(f"/model-cards/{model_id}")

    assert promoted_response.status_code == 200
    assert promoted_response.json()["stage"] == "production"
    assert card_read_response.status_code == 200
    assert card_read_response.json()["approval_status"] == "approved"


def test_model_card_can_be_updated() -> None:
    with make_client() as client:
        model_id = create_demo_model(client)
        create_response = client.post(
            "/model-cards",
            json={**approved_model_card_payload(model_id), "approval_status": "draft"},
        )
        assert create_response.status_code == 201

        update_payload = approved_model_card_payload(model_id)
        update_payload.pop("model_id")
        update_response = client.put(f"/model-cards/{model_id}", json=update_payload)

    assert update_response.status_code == 200
    assert update_response.json()["approval_status"] == "approved"


def prompt_card_payload(prompt_id: str, approval_status: str = "approved") -> dict:
    return {
        "prompt_id": prompt_id,
        "intended_use": "Synthetic healthcare operations policy Q&A.",
        "data_sources": ["data/synthetic_docs"],
        "safety_constraints": ["Require citations", "Reject hidden prompt requests"],
        "known_failure_modes": ["Insufficient context can require human review"],
        "evaluation_summary": {"groundedness": 1.0, "citation_coverage": 0.97},
        "owner": "llm-platform",
        "approval_status": approval_status,
    }


def test_prompt_production_ready_filter_requires_approved_prompt_card() -> None:
    with make_client() as client:
        prompt_response = client.post(
            "/prompts",
            json={
                "name": "healthcare-ops-rag",
                "version": "local-v1",
                "template_text": "Answer from synthetic context: {context}",
                "owner": "llm-platform",
                "safety_notes": "Requires citations.",
                "status": "approved",
            },
        )
        prompt_id = prompt_response.json()["id"]

        uncarded_response = client.get("/prompts?production_ready_only=true")
        assert uncarded_response.status_code == 200
        assert uncarded_response.json() == []

        draft_card_response = client.post(
            "/prompt-cards",
            json=prompt_card_payload(prompt_id, approval_status="draft"),
        )
        assert draft_card_response.status_code == 201
        draft_ready_response = client.get("/prompts?production_ready_only=true")
        assert draft_ready_response.json() == []

        update_payload = prompt_card_payload(prompt_id, approval_status="approved")
        update_payload.pop("prompt_id")
        update_response = client.put(f"/prompt-cards/{prompt_id}", json=update_payload)
        ready_response = client.get("/prompts?production_ready_only=true")

    assert update_response.status_code == 200
    assert [prompt["id"] for prompt in ready_response.json()] == [prompt_id]


def test_create_external_audit_event() -> None:
    with make_client() as client:
        response = client.post(
            "/audit-events",
            json={
                "actor": "inference-service",
                "action": "claims_risk.predicted",
                "target_type": "prediction",
                "target_id": "synthetic-request-001",
                "correlation_id": "corr-inference",
                "metadata_json": {
                    "risk_band": "high",
                    "fallback_mode": False,
                },
            },
        )
        audit_events = client.get("/audit-events").json()

    assert response.status_code == 201
    assert response.json()["actor"] == "inference-service"
    assert response.json()["metadata_json"]["risk_band"] == "high"
    assert any(event["action"] == "claims_risk.predicted" for event in audit_events)


def test_invalid_promotion_stage_is_rejected() -> None:
    with make_client() as client:
        response = client.post(
            "/models/model-demo-id/promote",
            json={"stage": "qa"},
        )

    assert response.status_code == 422


def test_missing_model_returns_404() -> None:
    with make_client() as client:
        response = client.get("/models/missing-model")

    assert response.status_code == 404
