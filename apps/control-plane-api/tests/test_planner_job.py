from careai_control_plane_api.database import Database
from careai_control_plane_api.models import PaymentIntegrityCaseORM, WorkflowRunORM
from careai_control_plane_api.planner_job import run_once
from sqlalchemy import select


def sqlite_url(tmp_path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


def test_run_once_executes_due_autonomous_workflow(tmp_path) -> None:
    database_url = sqlite_url(tmp_path, "planner-job.db")
    database = Database(database_url)
    database.prepare_schema()
    session_generator = database.session()
    session = next(session_generator)
    try:
        case = PaymentIntegrityCaseORM(
            tenant_id="payer-auto",
            claim_id_synthetic="claim-job-001",
            member_id_synthetic="member-job-001",
            provider_id_synthetic="provider-job-001",
            policy_doc_id="claims_review_policy",
        )
        session.add(case)
        session.flush()
        workflow = WorkflowRunORM(
            tenant_id="payer-auto",
            workflow_type="payment_integrity_claim_review",
            target_type="payment_integrity_case",
            target_id=case.id,
            status="pending",
            current_step="intake",
            requested_by="payment-integrity-ops",
            autonomous_mode=True,
            steps_json=[
                {"name": "intake", "kind": "system"},
                {"name": "claims_risk_scoring", "kind": "model"},
            ],
            input_json={"planner_overrides": {"risk_score": 0.2, "human_review_required": False}},
            output_json={},
            planner_state_json={},
            next_run_at=case.created_at,
        )
        session.add(workflow)
        session.commit()
    finally:
        session_generator.close()

    summary = run_once(
        database_url=database_url,
        limit=10,
        max_steps_per_workflow=5,
        workflow_type="payment_integrity_claim_review",
    )

    assert summary["executed_count"] == 1
    assert summary["completed_count"] == 1

    session_generator = database.session()
    session = next(session_generator)
    try:
        workflow = session.scalars(select(WorkflowRunORM)).one()
        loop_history = workflow.planner_state_json["loop_history"]
        assert [event["phase"] for event in loop_history] == [
            "plan",
            "verification",
            "plan",
            "verification",
            "plan",
            "verification",
        ]
        assert all(event["details"].get("passed", True) for event in loop_history)
    finally:
        session_generator.close()
