from collections import Counter
from statistics import mean
from typing import Any

from careai_control_plane_api.models import AuditEventORM, EvaluationRunORM


def summarize_rag_improvements(
    *,
    rag_events: list[AuditEventORM],
    evaluation_runs: list[EvaluationRunORM],
) -> dict[str, Any]:
    total_queries = len(rag_events)
    if total_queries == 0:
        return {
            "total_queries": 0,
            "retry_rate": 0.0,
            "verification_failure_rate": 0.0,
            "fallback_rate": 0.0,
            "average_groundedness": 0.0,
            "flag_counts": {},
            "failed_eval_count": sum(1 for run in evaluation_runs if not run.passed),
            "recommendations": [],
        }

    retry_count = 0
    verification_failures = 0
    fallback_count = 0
    groundedness_scores: list[float] = []
    flag_counts: Counter[str] = Counter()

    for event in rag_events:
        metadata = event.metadata_json or {}
        if metadata.get("attempt_count", 1) > 1:
            retry_count += 1
        if not metadata.get("verification_passed", True):
            verification_failures += 1
        if metadata.get("fallback_mode", False):
            fallback_count += 1
        groundedness_scores.append(float(metadata.get("groundedness_score", 0.0)))
        for flag in metadata.get("safety_flags", []):
            flag_counts[str(flag)] += 1
        for flag in metadata.get("verification_flags", []):
            flag_counts[str(flag)] += 1

    retry_rate = round(retry_count / total_queries, 4)
    verification_failure_rate = round(verification_failures / total_queries, 4)
    fallback_rate = round(fallback_count / total_queries, 4)
    average_groundedness = round(mean(groundedness_scores), 4) if groundedness_scores else 0.0
    failed_eval_count = sum(1 for run in evaluation_runs if not run.passed)

    recommendations: list[dict[str, Any]] = []
    if retry_rate >= 0.20:
        recommendations.append(
            recommendation(
                category="retrieval",
                priority="medium",
                message=(
                    "High retry volume suggests the first retrieval pass is too "
                    "weak for consistent answers."
                ),
                evidence={"retry_rate": retry_rate, "threshold": 0.20},
            )
        )
    if verification_failure_rate >= 0.10:
        recommendations.append(
            recommendation(
                category="prompt_and_grader",
                priority="high",
                message=(
                    "Verification failures should tighten the prompt rubric and "
                    "keep citation checks as a release gate."
                ),
                evidence={
                    "verification_failure_rate": verification_failure_rate,
                    "threshold": 0.10,
                },
            )
        )
    if flag_counts.get("missing_inline_citations", 0) > 0:
        recommendations.append(
            recommendation(
                category="citation_policy",
                priority="high",
                message=(
                    "Missing inline citations were observed. Strengthen answer "
                    "formatting and keep answer retries enabled."
                ),
                evidence={"missing_inline_citations": flag_counts["missing_inline_citations"]},
            )
        )
    if flag_counts.get("no_role_authorized_context_found", 0) > 0:
        recommendations.append(
            recommendation(
                category="corpus_and_access",
                priority="medium",
                message=(
                    "Role-filtered retrieval returned no authorized context for "
                    "some requests. Expand corpus coverage or role mapping."
                ),
                evidence={
                    "no_role_authorized_context_found": flag_counts[
                        "no_role_authorized_context_found"
                    ]
                },
            )
        )
    if fallback_rate >= 0.10:
        recommendations.append(
            recommendation(
                category="provider_operations",
                priority="medium",
                message=(
                    "Fallback usage is elevated. Verify Azure OpenAI configuration "
                    "and provider health before production rollout."
                ),
                evidence={"fallback_rate": fallback_rate, "threshold": 0.10},
            )
        )
    if average_groundedness < 0.65:
        recommendations.append(
            recommendation(
                category="groundedness",
                priority="high",
                message=(
                    "Average groundedness is below the desired production target. "
                    "Tune chunking, retrieval, or answer constraints."
                ),
                evidence={"average_groundedness": average_groundedness, "target": 0.65},
            )
        )
    if failed_eval_count > 0:
        recommendations.append(
            recommendation(
                category="promotion_gate",
                priority="high",
                message=(
                    "Recent RAG evaluations failed. Block prompt promotion until "
                    "the failing metrics recover."
                ),
                evidence={"failed_eval_count": failed_eval_count},
            )
        )

    return {
        "total_queries": total_queries,
        "retry_rate": retry_rate,
        "verification_failure_rate": verification_failure_rate,
        "fallback_rate": fallback_rate,
        "average_groundedness": average_groundedness,
        "flag_counts": dict(flag_counts),
        "failed_eval_count": failed_eval_count,
        "recommendations": recommendations,
    }


def recommendation(
    *,
    category: str,
    priority: str,
    message: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "category": category,
        "priority": priority,
        "message": message,
        "evidence": evidence,
    }


def recommendations_from_rag_event_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    verification_flags = [str(flag) for flag in metadata.get("verification_flags", [])]
    if metadata.get("attempt_count", 1) > 1:
        recommendations.append(
            recommendation(
                category="retry_trace",
                priority="medium",
                message=(
                    "This query required a verifier-driven retry before the final "
                    "answer was returned."
                ),
                evidence={"attempt_count": metadata.get("attempt_count", 1)},
            )
        )
    if "missing_inline_citations" in verification_flags:
        recommendations.append(
            recommendation(
                category="citation_policy",
                priority="high",
                message=(
                    "The answer failed citation checks in at least one iteration. "
                    "Strengthen prompt instructions or grader policy."
                ),
                evidence={"verification_flags": verification_flags},
            )
        )
    if "low_groundedness" in verification_flags:
        recommendations.append(
            recommendation(
                category="groundedness",
                priority="high",
                message=(
                    "The answer showed low groundedness relative to retrieved "
                    "context. Review chunking and retrieval quality."
                ),
                evidence={
                    "verification_flags": verification_flags,
                    "groundedness_score": metadata.get("groundedness_score", 0.0),
                },
            )
        )
    if "no_role_authorized_context_found" in verification_flags:
        recommendations.append(
            recommendation(
                category="corpus_and_access",
                priority="medium",
                message=(
                    "No role-authorized context was found for this query. Review "
                    "access filters and corpus coverage."
                ),
                evidence={"verification_flags": verification_flags},
            )
        )
    return recommendations
