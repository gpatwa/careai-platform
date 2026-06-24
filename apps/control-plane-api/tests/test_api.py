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
        model_id = create_demo_model(client)
        deployment_response = client.post(
            "/deployments",
            json={
                "model_id": model_id,
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


def create_demo_model(client: TestClient, version: str = "0.1.0") -> str:
    dataset_response = client.post(
        "/datasets",
        json={
            "name": "synthetic-claims",
            "version": f"2026.06-{version}",
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
            "version": version,
            "framework": "scikit-learn",
            "artifact_uri": f"azurite://models/claims-risk/{version}",
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


def test_deployment_canary_traffic_split_and_rollback_metadata() -> None:
    with make_client() as client:
        champion_id = create_demo_model(client, version="1.0.0")
        challenger_id = create_demo_model(client, version="1.1.0")
        deployment_response = client.post(
            "/deployments",
            json={
                "model_id": champion_id,
                "environment": "prod",
                "deployment_type": "blue-green",
                "endpoint_url": "http://localhost:8001/predict/claims-risk",
                "traffic_percent": 100,
                "status": "active",
            },
        )
        deployment = deployment_response.json()

        canary_response = client.post(
            f"/deployments/{deployment['id']}/canary",
            json={
                "challenger_model_id": challenger_id,
                "challenger_percent": 15,
                "actor": "release-manager",
                "notes": "Synthetic canary rollout.",
            },
        )
        invalid_traffic_response = client.post(
            f"/deployments/{deployment['id']}/set-traffic",
            json={
                "traffic_split_json": {champion_id: 80, challenger_id: 10},
                "actor": "release-manager",
            },
        )
        traffic_response = client.post(
            f"/deployments/{deployment['id']}/set-traffic",
            json={
                "traffic_split_json": {champion_id: 75, challenger_id: 25},
                "actor": "release-manager",
                "notes": "Expand synthetic challenger traffic.",
            },
        )
        rollback_response = client.post(
            f"/deployments/{deployment['id']}/rollback",
            json={"actor": "release-manager", "notes": "Rollback after safety trigger."},
        )
        audit_response = client.get("/audit-events")

    assert deployment_response.status_code == 201
    assert deployment["champion_model_id"] == champion_id
    assert deployment["rollback_model_id"] == champion_id
    assert deployment["traffic_split_json"] == {champion_id: 100}

    assert canary_response.status_code == 200
    canary = canary_response.json()
    assert canary["deployment_type"] == "canary"
    assert canary["challenger_model_id"] == challenger_id
    assert canary["traffic_split_json"] == {champion_id: 85, challenger_id: 15}
    assert canary["health_status"] == "canary"

    assert invalid_traffic_response.status_code == 422
    assert traffic_response.status_code == 200
    assert traffic_response.json()["traffic_split_json"] == {champion_id: 75, challenger_id: 25}

    assert rollback_response.status_code == 200
    rolled_back = rollback_response.json()
    assert rolled_back["champion_model_id"] == champion_id
    assert rolled_back["challenger_model_id"] is None
    assert rolled_back["traffic_split_json"] == {champion_id: 100}
    assert rolled_back["health_status"] == "rolled_back"

    audit_actions = {event["action"] for event in audit_response.json()}
    assert {
        "deployment.canary_started",
        "deployment.traffic_updated",
        "deployment.rolled_back",
    } <= audit_actions


def test_deployment_health_marks_rollback_recommended_on_slo_breach() -> None:
    with make_client() as client:
        champion_id = create_demo_model(client, version="2.0.0")
        deployment_response = client.post(
            "/deployments",
            json={
                "model_id": champion_id,
                "environment": "prod",
                "deployment_type": "blue-green",
                "endpoint_url": "http://localhost:8001/predict/claims-risk",
                "traffic_percent": 100,
                "status": "active",
            },
        )
        assert deployment_response.status_code == 201

        prediction_response = client.post(
            "/monitoring/prediction-events",
            json={
                "model_name": "claims-risk",
                "model_version": "2.0.0",
                "request_features_json": {
                    "age_bucket": "65+",
                    "plan_type": "medicare_advantage",
                    "prior_claim_count": 8,
                    "recent_visit_count": 4,
                    "medication_count": 6,
                    "chronic_condition_count": 3,
                    "region_code": "R03",
                },
                "prediction_score": 0.82,
                "risk_band": "high",
                "latency_ms": 20,
                "correlation_id": "corr-deployment-prediction",
            },
        )
        error_response = client.post(
            "/monitoring/error-events",
            json={
                "model_name": "claims-risk",
                "model_version": "2.0.0",
                "error_type": "model_prediction_failed",
                "error_message": "Model prediction failed; deterministic fallback score returned.",
                "status_code": 200,
                "latency_ms": 44,
                "correlation_id": "corr-deployment-error",
            },
        )
        deployments_response = client.get("/deployments")

    assert prediction_response.status_code == 201
    assert error_response.status_code == 201
    assert deployments_response.status_code == 200
    deployment = deployments_response.json()[0]
    assert deployment["health_status"] == "rollback_recommended"


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


def test_payment_integrity_case_launches_workflow_and_review_queue() -> None:
    with make_client() as client:
        case_response = client.post(
            "/payment-integrity/cases",
            headers={"x-tenant-id": "payer-acme", "x-actor": "payment-integrity-ops"},
            json={
                "claim_id_synthetic": "claim-synth-001",
                "member_id_synthetic": "member-synth-101",
                "provider_id_synthetic": "provider-synth-044",
                "policy_doc_id": "claims_review_policy",
                "requested_by": "payment-integrity-ops",
                "start_workflow": True,
            },
        )
        assert case_response.status_code == 201
        case_body = case_response.json()
        workflow_run_id = case_body["workflow_run_id"]

        workflow_response = client.get(
            f"/workflow-runs/{workflow_run_id}",
            headers={"x-tenant-id": "payer-acme"},
        )
        assert workflow_response.status_code == 200
        assert workflow_response.json()["workflow_type"] == "payment_integrity_claim_review"

        inference_signal = client.post(
            f"/workflow-runs/{workflow_run_id}/signals",
            headers={"x-tenant-id": "payer-acme", "x-actor": "inference-service"},
            json={
                "signal_type": "claims_risk_scored",
                "signal_metadata": {
                    "prediction_score": 0.83,
                    "risk_band": "high",
                },
                "actor": "inference-service",
            },
        )
        assert inference_signal.status_code == 200

        rag_signal = client.post(
            f"/workflow-runs/{workflow_run_id}/signals",
            headers={"x-tenant-id": "payer-acme", "x-actor": "rag-service"},
            json={
                "signal_type": "policy_answered",
                "signal_metadata": {
                    "retrieved_source_ids": ["claims_review_policy-0000"],
                    "human_review_required": True,
                },
                "actor": "rag-service",
            },
        )
        assert rag_signal.status_code == 200
        assert rag_signal.json()["status"] == "waiting_for_review"

        review_items_response = client.get(
            "/review-queue/items",
            headers={"x-tenant-id": "payer-acme"},
        )
        assert review_items_response.status_code == 200
        review_items = review_items_response.json()
        assert len(review_items) == 1
        assert review_items[0]["case_id"] == case_body["id"]
        assert review_items[0]["tenant_id"] == "payer-acme"

        case_after_signal = client.get(
            f"/payment-integrity/cases/{case_body['id']}",
            headers={"x-tenant-id": "payer-acme"},
        )
        assert case_after_signal.status_code == 200
        assert case_after_signal.json()["status"] == "pending_human_review"


def test_review_queue_resolution_completes_workflow_and_case() -> None:
    with make_client() as client:
        case_response = client.post(
            "/payment-integrity/cases",
            headers={"x-tenant-id": "payer-acme"},
            json={
                "claim_id_synthetic": "claim-synth-002",
                "member_id_synthetic": "member-synth-202",
                "provider_id_synthetic": "provider-synth-055",
                "policy_doc_id": "claims_review_policy",
                "requested_by": "payment-integrity-ops",
                "start_workflow": True,
            },
        )
        case_id = case_response.json()["id"]
        workflow_run_id = case_response.json()["workflow_run_id"]
        client.post(
            f"/workflow-runs/{workflow_run_id}/signals",
            headers={"x-tenant-id": "payer-acme"},
            json={
                "signal_type": "policy_answered",
                "signal_metadata": {
                    "retrieved_source_ids": ["claims_review_policy-0000"],
                    "human_review_required": True,
                },
                "actor": "rag-service",
            },
        )
        review_item = client.get(
            "/review-queue/items",
            headers={"x-tenant-id": "payer-acme"},
        ).json()[0]

        assign_response = client.post(
            f"/review-queue/items/{review_item['id']}/assign",
            headers={"x-tenant-id": "payer-acme"},
            json={"assigned_to": "clinical-reviewer-01", "actor": "review-manager"},
        )
        resolve_response = client.post(
            f"/review-queue/items/{review_item['id']}/resolve",
            headers={"x-tenant-id": "payer-acme"},
            json={
                "decision": "deny_and_escalate",
                "rationale": "Policy evidence supports manual escalation.",
                "actor": "clinical-reviewer-01",
            },
        )
        workflow_response = client.get(
            f"/workflow-runs/{workflow_run_id}",
            headers={"x-tenant-id": "payer-acme"},
        )
        case_resolution = client.post(
            f"/payment-integrity/cases/{case_id}/resolve",
            headers={"x-tenant-id": "payer-acme"},
            json={
                "final_decision": "deny_and_escalate",
                "rationale": "Manual review completed.",
                "actor": "clinical-reviewer-01",
            },
        )

    assert assign_response.status_code == 200
    assert resolve_response.status_code == 200
    assert workflow_response.status_code == 200
    assert workflow_response.json()["status"] == "completed"
    assert case_resolution.status_code == 200
    assert case_resolution.json()["final_decision"] == "deny_and_escalate"
    assert case_resolution.json()["status"] == "closed"


def test_tenant_scoped_reads_hide_other_tenant_records() -> None:
    with make_client() as client:
        payer_a_dataset = client.post(
            "/datasets",
            headers={"x-tenant-id": "payer-acme"},
            json={
                "name": "synthetic-claims",
                "version": "tenant-a-dataset",
                "owner": "platform-demo",
                "schema_uri": "azurite://schemas/claims.json",
                "storage_uri": "azurite://datasets/tenant-a",
                "pii_classification": "synthetic-no-phi",
            },
        )
        payer_b_dataset = client.post(
            "/datasets",
            headers={"x-tenant-id": "payer-bravo"},
            json={
                "name": "synthetic-claims",
                "version": "tenant-b-dataset",
                "owner": "platform-demo",
                "schema_uri": "azurite://schemas/claims.json",
                "storage_uri": "azurite://datasets/tenant-b",
                "pii_classification": "synthetic-no-phi",
            },
        )
        payer_a_model = client.post(
            "/models",
            headers={"x-tenant-id": "payer-acme"},
            json={
                "name": "claims-risk",
                "version": "tenant-a-model",
                "framework": "scikit-learn",
                "artifact_uri": "azurite://models/claims-risk/tenant-a",
                "training_dataset_id": payer_a_dataset.json()["id"],
                "metrics_json": {"auc": 0.91},
                "lineage_json": {"run_id": "tenant-a-run"},
                "stage": "dev",
            },
        )
        payer_b_model = client.post(
            "/models",
            headers={"x-tenant-id": "payer-bravo"},
            json={
                "name": "claims-risk",
                "version": "tenant-b-model",
                "framework": "scikit-learn",
                "artifact_uri": "azurite://models/claims-risk/tenant-b",
                "training_dataset_id": payer_b_dataset.json()["id"],
                "metrics_json": {"auc": 0.89},
                "lineage_json": {"run_id": "tenant-b-run"},
                "stage": "dev",
            },
        )

        payer_a_list = client.get("/datasets", headers={"x-tenant-id": "payer-acme"})
        payer_b_list = client.get("/datasets", headers={"x-tenant-id": "payer-bravo"})
        cross_tenant_get = client.get(
            f"/models/{payer_a_model.json()['id']}",
            headers={"x-tenant-id": "payer-bravo"},
        )

    assert payer_a_dataset.status_code == 201
    assert payer_b_dataset.status_code == 201
    assert payer_a_model.status_code == 201
    assert payer_b_model.status_code == 201
    assert [item["version"] for item in payer_a_list.json()] == ["tenant-a-dataset"]
    assert [item["version"] for item in payer_b_list.json()] == ["tenant-b-dataset"]
    assert cross_tenant_get.status_code == 404


def test_autonomous_planner_executes_payment_integrity_workflow_until_human_review() -> None:
    with make_client() as client:
        case_response = client.post(
            "/payment-integrity/cases",
            headers={"x-tenant-id": "payer-auto"},
            json={
                "claim_id_synthetic": "claim-auto-001",
                "member_id_synthetic": "member-auto-001",
                "provider_id_synthetic": "provider-auto-001",
                "policy_doc_id": "claims_review_policy",
                "requested_by": "payment-integrity-ops",
                "start_workflow": True,
                "autonomous_mode": True,
                "workflow_input_json": {
                    "planner_overrides": {"risk_score": 0.82, "human_review_required": True}
                },
            },
        )
        assert case_response.status_code == 201
        workflow_run_id = case_response.json()["workflow_run_id"]

        decision_response = client.get(
            f"/workflow-runs/{workflow_run_id}/planner-decision",
            headers={"x-tenant-id": "payer-auto"},
        )
        assert decision_response.status_code == 200
        assert decision_response.json()["tool_name"] == "claims_risk_scoring_tool"

        run_due_response = client.post(
            "/planner/run-due",
            headers={"x-tenant-id": "payer-auto"},
            json={"limit": 10, "max_steps_per_workflow": 5},
        )
        workflow_response = client.get(
            f"/workflow-runs/{workflow_run_id}",
            headers={"x-tenant-id": "payer-auto"},
        )
        review_items_response = client.get(
            "/review-queue/items",
            headers={"x-tenant-id": "payer-auto"},
        )
        case_after = client.get(
            f"/payment-integrity/cases/{case_response.json()['id']}",
            headers={"x-tenant-id": "payer-auto"},
        )

    assert run_due_response.status_code == 200
    assert run_due_response.json()["executed_count"] == 1
    assert workflow_response.status_code == 200
    assert workflow_response.json()["status"] == "waiting_for_review"
    assert workflow_response.json()["review_required"] is True
    assert workflow_response.json()["planner_state_json"]["last_decision"]["blocked_reason"] == (
        "human_review_required"
    )
    assert review_items_response.status_code == 200
    assert len(review_items_response.json()) == 1
    assert case_after.status_code == 200
    assert case_after.json()["risk_band"] == "high"
    assert case_after.json()["status"] == "pending_human_review"


def test_autonomous_prompt_optimization_can_self_deploy_when_explicitly_allowed() -> None:
    with make_client() as client:
        prompt_response = client.post(
            "/prompts",
            headers={"x-tenant-id": "payer-auto"},
            json={
                "name": "healthcare-ops-rag",
                "version": "local-v1",
                "template_text": "Answer from synthetic context: {context}",
                "owner": "llm-platform",
                "safety_notes": "Requires citations.",
                "status": "approved",
            },
        )
        assert prompt_response.status_code == 201
        prompt_id = prompt_response.json()["id"]

        prompt_card_response = client.post(
            "/prompt-cards",
            headers={"x-tenant-id": "payer-auto"},
            json=prompt_card_payload(prompt_id, approval_status="approved"),
        )
        assert prompt_card_response.status_code == 201

        evaluation_response = client.post(
            "/evaluations",
            headers={"x-tenant-id": "payer-auto"},
            json={
                "target_type": "prompt",
                "target_id": prompt_id,
                "metrics_json": {
                    "groundedness": 0.62,
                    "citation_coverage": 0.78,
                    "safety_flag_rate": 0.08,
                },
                "passed": True,
                "report_uri": "azurite://reports/prompt-baseline.json",
            },
        )
        assert evaluation_response.status_code == 201

        improvement_event = client.post(
            "/audit-events",
            headers={"x-tenant-id": "payer-auto"},
            json={
                "actor": "control-plane-api",
                "action": "rag.improvement_candidate_detected",
                "target_type": "prompt",
                "target_id": prompt_id,
                "correlation_id": "corr-prompt-opt",
                "metadata_json": {
                    "category": "citation_policy",
                    "priority": "high",
                    "message": "Citations need tightening.",
                    "evidence": {"missing_inline_citations": 2},
                },
            },
        )
        assert improvement_event.status_code == 201

        optimization_response = client.post(
            "/prompt-optimization-runs",
            headers={"x-tenant-id": "payer-auto"},
            json={
                "prompt_id": prompt_id,
                "requested_by": "llm-platform",
                "autonomous_mode": True,
                "auto_deploy": True,
                "allow_self_approval": True,
            },
        )
        assert optimization_response.status_code == 201
        workflow_run_id = optimization_response.json()["id"]

        run_due_response = client.post(
            "/planner/run-due",
            headers={"x-tenant-id": "payer-auto"},
            json={
                "limit": 10,
                "max_steps_per_workflow": 5,
                "workflow_type": "prompt_self_optimization",
            },
        )
        workflow_response = client.get(
            f"/workflow-runs/{workflow_run_id}",
            headers={"x-tenant-id": "payer-auto"},
        )
        prompts_response = client.get("/prompts", headers={"x-tenant-id": "payer-auto"})
        approvals_response = client.get("/approvals", headers={"x-tenant-id": "payer-auto"})

    assert run_due_response.status_code == 200
    assert run_due_response.json()["completed_count"] == 1
    assert workflow_response.status_code == 200
    assert workflow_response.json()["status"] == "completed"
    candidate_prompt_id = workflow_response.json()["output_json"]["candidate_deployed_prompt_id"]
    prompts = prompts_response.json()
    candidate_prompt = next(prompt for prompt in prompts if prompt["id"] == candidate_prompt_id)
    base_prompt = next(prompt for prompt in prompts if prompt["id"] == prompt_id)
    assert candidate_prompt["status"] == "approved"
    assert "Optimization notes" in candidate_prompt["template_text"]
    assert base_prompt["status"] == "deprecated"
    assert any(
        approval["target_type"] == "prompt" and approval["target_id"] == candidate_prompt_id
        for approval in approvals_response.json()
    )
