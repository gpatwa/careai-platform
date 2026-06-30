"""Bounded loop-engineering primitives for autonomous workflow execution."""

from dataclasses import asdict, dataclass
from typing import Any, Literal

MAX_LOOP_HISTORY = 40


@dataclass(frozen=True)
class LoopVerification:
    """A safe, JSON-serializable verifier result for one tool execution."""

    passed: bool
    next_action: Literal["advance", "retry", "human_review"]
    feedback: list[str]
    evidence_keys: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_tool_result(
    *,
    tool_name: str,
    output_json: dict[str, Any],
    review_required: bool,
) -> LoopVerification:
    """Verify a tool result using only bounded, non-sensitive workflow evidence."""
    if tool_name == "claims_risk_scoring_tool":
        claims_risk = dict(output_json.get("claims_risk", {}))
        score = claims_risk.get("prediction_score")
        risk_band = claims_risk.get("risk_band")
        valid_score = isinstance(score, (int, float)) and 0 <= float(score) <= 1
        valid_band = risk_band in {"low", "medium", "high"}
        feedback = []
        if not valid_score:
            feedback.append("prediction_score_missing_or_out_of_range")
        if not valid_band:
            feedback.append("risk_band_missing_or_invalid")
        return LoopVerification(
            passed=not feedback,
            next_action="advance" if not feedback else "human_review",
            feedback=feedback,
            evidence_keys=sorted(claims_risk.keys()),
        )

    if tool_name == "policy_retrieval_tool":
        policy_answer = dict(output_json.get("policy_answer", {}))
        source_ids = policy_answer.get("source_ids") or policy_answer.get("retrieved_source_ids")
        summary = policy_answer.get("summary")
        feedback = []
        if not isinstance(source_ids, list) or not source_ids:
            feedback.append("policy_evidence_missing")
        if not isinstance(summary, str) or not summary.strip():
            feedback.append("policy_summary_missing")
        return LoopVerification(
            passed=not feedback,
            next_action="advance"
            if not feedback
            else ("human_review" if review_required else "retry"),
            feedback=feedback,
            evidence_keys=sorted(policy_answer.keys()),
        )

    if tool_name == "case_resolution_tool":
        case_closed = dict(output_json.get("case_closed", {}))
        feedback = []
        if review_required:
            feedback.append("case_resolution_blocked_by_human_review")
        if not isinstance(case_closed.get("final_decision"), str):
            feedback.append("final_decision_missing")
        return LoopVerification(
            passed=not feedback,
            next_action="advance" if not feedback else "human_review",
            feedback=feedback,
            evidence_keys=sorted(case_closed.keys()),
        )

    return LoopVerification(
        passed=True,
        next_action="advance",
        feedback=[],
        evidence_keys=[],
    )


def append_loop_event(
    planner_state: dict[str, Any],
    *,
    phase: Literal["plan", "verification", "retry", "human_review"],
    tool_name: str | None,
    at: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    """Append bounded loop history for audit and restart-safe introspection."""
    state = dict(planner_state)
    history = list(state.get("loop_history", []))
    history.append(
        {
            "phase": phase,
            "tool_name": tool_name,
            "at": at,
            "details": details,
        }
    )
    state["loop_history"] = history[-MAX_LOOP_HISTORY:]
    return state


def retry_count(planner_state: dict[str, Any], tool_name: str) -> int:
    return int(dict(planner_state.get("verification_retries", {})).get(tool_name, 0))


def increment_retry(planner_state: dict[str, Any], tool_name: str) -> dict[str, Any]:
    state = dict(planner_state)
    retries = dict(state.get("verification_retries", {}))
    retries[tool_name] = retry_count(state, tool_name) + 1
    state["verification_retries"] = retries
    return state
