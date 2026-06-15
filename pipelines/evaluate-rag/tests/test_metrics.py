from evaluate_rag.metrics import (
    aggregate_metrics,
    citation_coverage,
    evaluate_item,
    keyword_relevance,
    report_passed,
    retrieval_hit,
)
from evaluate_rag.models import EvalItem, RagServiceResult, Thresholds


def test_retrieval_hit_matches_doc_or_chunk_identifier() -> None:
    assert retrieval_hit(
        ["prior_authorization_policy"],
        ["prior_authorization_policy-0000", "member_support_playbook"],
    )
    assert not retrieval_hit(["claims_review_policy"], ["member_support_playbook-0000"])


def test_citation_coverage_scores_expected_sources() -> None:
    assert (
        citation_coverage(
            ["prior_authorization_policy", "member_support_playbook"],
            ["prior_authorization_policy-0000"],
        )
        == 0.5
    )
    assert citation_coverage([], []) == 1.0


def test_keyword_relevance_counts_expected_phrases() -> None:
    score = keyword_relevance(
        "Routine reviews target two business days and expedited reviews target one business day.",
        ["two business days", "one business day", "manual review"],
    )

    assert score == 0.6667


def test_evaluate_item_combines_retrieval_citation_keyword_and_safety() -> None:
    item = EvalItem(
        question="What should be captured?",
        expected_sources=["responsible_ai_guidelines"],
        expected_keywords=["correlation ID", "prompt version"],
        role="model_risk_reviewer",
    )
    result = RagServiceResult(
        answer="Each RAG request should emit a correlation ID and prompt version.",
        citations=[
            {
                "source_id": "responsible_ai_guidelines-0000",
                "doc_id": "responsible_ai_guidelines",
                "chunk_id": "responsible_ai_guidelines-0000",
            }
        ],
        retrieved_chunks=[
            {
                "source_id": "responsible_ai_guidelines-0000",
                "doc_id": "responsible_ai_guidelines",
                "chunk_id": "responsible_ai_guidelines-0000",
            }
        ],
        groundedness_score=0.82,
        latency_ms=42,
        correlation_id="corr-eval-test",
    )

    metrics = evaluate_item(item, result, thresholds=Thresholds())

    assert metrics.retrieval_hit is True
    assert metrics.citation_coverage == 1.0
    assert metrics.keyword_relevance == 1.0
    assert metrics.groundedness == 0.82
    assert metrics.passed is True


def test_disallowed_claims_fail_item() -> None:
    item = EvalItem(
        question="What should not happen?",
        expected_sources=["responsible_ai_guidelines"],
        expected_keywords=["synthetic"],
        role="model_risk_reviewer",
        disallowed_claims=["real patient data is allowed"],
    )
    result = RagServiceResult(
        answer="Synthetic controls apply, but real patient data is allowed.",
        citations=[{"doc_id": "responsible_ai_guidelines"}],
        retrieved_chunks=[{"doc_id": "responsible_ai_guidelines"}],
        groundedness_score=0.9,
        latency_ms=20,
    )

    metrics = evaluate_item(item, result, thresholds=Thresholds())

    assert metrics.disallowed_claims_found == ["real patient data is allowed"]
    assert metrics.passed is False


def test_aggregate_metrics_and_report_pass_thresholds() -> None:
    thresholds = Thresholds(avg_latency_ms_max=100)
    passing = evaluate_item(
        EvalItem(
            question="What is required?",
            expected_sources=["prior_authorization_policy"],
            expected_keywords=["urgency"],
            role="clinical_ops",
        ),
        RagServiceResult(
            answer="Review requires urgency.",
            citations=[{"doc_id": "prior_authorization_policy"}],
            retrieved_chunks=[{"doc_id": "prior_authorization_policy"}],
            groundedness_score=0.7,
            latency_ms=50,
        ),
        thresholds=thresholds,
    )
    failing = passing.model_copy(
        update={
            "retrieval_hit": False,
            "citation_coverage": 0.0,
            "keyword_relevance": 0.0,
            "groundedness": 0.1,
            "passed": False,
            "latency_ms": 150,
        }
    )

    aggregate = aggregate_metrics([passing, failing])

    assert aggregate.retrieval_hit_rate == 0.5
    assert aggregate.citation_coverage == 0.5
    assert aggregate.avg_latency_ms == 100
    assert report_passed(aggregate, thresholds) is False
