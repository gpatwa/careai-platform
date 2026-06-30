from careai_control_plane_api.api import route_verification_failure
from careai_control_plane_api.database import Database
from careai_control_plane_api.models import (
    PaymentIntegrityCaseORM,
    ReviewQueueItemORM,
    WorkflowRunORM,
)
from careai_control_plane_api.workflow_loop import (
    LoopVerification,
    append_loop_event,
    retry_count,
    verify_tool_result,
)


def test_policy_retrieval_verifier_requests_retry_when_evidence_is_missing() -> None:
    verification = verify_tool_result(
        tool_name="policy_retrieval_tool",
        output_json={"policy_answer": {"summary": "Synthetic summary."}},
        review_required=False,
    )

    assert verification.passed is False
    assert verification.next_action == "retry"
    assert verification.feedback == ["policy_evidence_missing"]


def test_claims_scoring_verifier_accepts_bounded_evidence() -> None:
    verification = verify_tool_result(
        tool_name="claims_risk_scoring_tool",
        output_json={
            "claims_risk": {
                "prediction_score": 0.42,
                "risk_band": "medium",
                "selected_tool": "claims_risk_scoring_tool",
            }
        },
        review_required=False,
    )

    assert verification.passed is True
    assert verification.next_action == "advance"
    assert verification.evidence_keys == ["prediction_score", "risk_band", "selected_tool"]


def test_loop_history_is_bounded() -> None:
    state = {}
    for index in range(45):
        state = append_loop_event(
            state,
            phase="plan",
            tool_name="claims_risk_scoring_tool",
            at=f"2026-06-24T00:00:{index:02d}Z",
            details={"step": index},
        )

    assert len(state["loop_history"]) == 40
    assert state["loop_history"][0]["details"] == {"step": 5}
    assert retry_count(state, "policy_retrieval_tool") == 0


def test_policy_evidence_failure_schedules_one_bounded_retry() -> None:
    workflow = WorkflowRunORM(
        tenant_id="payer-test",
        workflow_type="payment_integrity_claim_review",
        target_type="payment_integrity_case",
        target_id="case-001",
        output_json={"policy_answer": {"summary": "Synthetic summary."}},
        planner_state_json={},
    )
    verification = LoopVerification(
        passed=False,
        next_action="retry",
        feedback=["policy_evidence_missing"],
        evidence_keys=["summary"],
    )

    retried = route_verification_failure(
        None,  # type: ignore[arg-type]  # Retry path does not access the database session.
        workflow,
        tool_name="policy_retrieval_tool",
        verification=verification,
    )

    assert retried is True
    assert workflow.status == "running"
    assert workflow.current_step == "policy_retrieval"
    assert "policy_answer" not in workflow.output_json
    assert retry_count(workflow.planner_state_json, "policy_retrieval_tool") == 1
    assert workflow.planner_state_json["loop_history"][-1]["phase"] == "retry"


def test_verification_failure_hands_off_to_human_review() -> None:
    database = Database("sqlite:///:memory:")
    database.create_all()
    session_generator = database.session()
    session = next(session_generator)
    try:
        case = PaymentIntegrityCaseORM(
            tenant_id="payer-test",
            claim_id_synthetic="claim-001",
            member_id_synthetic="member-001",
            provider_id_synthetic="provider-001",
            policy_doc_id="claims-review-policy",
        )
        session.add(case)
        session.flush()
        workflow = WorkflowRunORM(
            tenant_id="payer-test",
            workflow_type="payment_integrity_claim_review",
            target_type="payment_integrity_case",
            target_id=case.id,
            output_json={"claims_risk": {"prediction_score": 0.4}},
            planner_state_json={},
        )
        session.add(workflow)
        session.flush()

        handed_off = route_verification_failure(
            session,
            workflow,
            tool_name="policy_retrieval_tool",
            verification=LoopVerification(
                passed=False,
                next_action="human_review",
                feedback=["policy_evidence_missing"],
                evidence_keys=[],
            ),
        )

        queue_item = session.query(ReviewQueueItemORM).one()
        assert handed_off is False
        assert workflow.status == "waiting_for_review"
        assert workflow.review_required is True
        assert case.status == "pending_human_review"
        assert queue_item.queue_name == "ai-evidence-review"
        assert workflow.planner_state_json["loop_history"][-1]["phase"] == "human_review"
    finally:
        session_generator.close()
