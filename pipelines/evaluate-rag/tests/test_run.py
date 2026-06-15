import json
from pathlib import Path

from evaluate_rag.models import EvalItem, RagServiceResult, Thresholds
from evaluate_rag.run import load_eval_set, run_evaluation


class FakeRagClient:
    def query(self, item: EvalItem, *, top_k: int = 4) -> RagServiceResult:
        return RagServiceResult(
            answer=(
                f"{item.expected_keywords[0]} is supported by synthetic policy context "
                f"[{item.expected_sources[0]}-0000]."
            ),
            citations=[
                {
                    "source_id": f"{item.expected_sources[0]}-0000",
                    "doc_id": item.expected_sources[0],
                    "chunk_id": f"{item.expected_sources[0]}-0000",
                    "title": "Synthetic Policy",
                    "source_uri": "file:///synthetic/policy.md",
                }
            ],
            retrieved_chunks=[
                {
                    "source_id": f"{item.expected_sources[0]}-0000",
                    "doc_id": item.expected_sources[0],
                    "chunk_id": f"{item.expected_sources[0]}-0000",
                    "title": "Synthetic Policy",
                    "source_uri": "file:///synthetic/policy.md",
                    "excerpt": "synthetic policy context",
                    "score": 1.0,
                }
            ],
            groundedness_score=0.8,
            latency_ms=25,
            correlation_id="corr-fake-eval",
        )


def test_load_eval_set_reads_jsonl(tmp_path: Path) -> None:
    eval_set = tmp_path / "eval.jsonl"
    eval_set.write_text(
        json.dumps(
            {
                "question": "What is required?",
                "expected_sources": ["prior_authorization_policy"],
                "expected_keywords": ["urgency"],
                "role": "clinical_ops",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    items = load_eval_set(eval_set)

    assert len(items) == 1
    assert items[0].role == "clinical_ops"


def test_run_evaluation_writes_report_with_thresholds(tmp_path: Path) -> None:
    eval_set = tmp_path / "eval.jsonl"
    eval_set.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "question": "What is required?",
                        "expected_sources": ["prior_authorization_policy"],
                        "expected_keywords": ["urgency"],
                        "role": "clinical_ops",
                    }
                ),
                json.dumps(
                    {
                        "question": "What is tracked?",
                        "expected_sources": ["responsible_ai_guidelines"],
                        "expected_keywords": ["correlation ID"],
                        "role": "model_risk_reviewer",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    report = run_evaluation(
        rag_url="http://rag-service",
        eval_set=eval_set,
        output=output,
        thresholds=Thresholds(keyword_relevance_min=0.4),
        client=FakeRagClient(),  # type: ignore[arg-type]
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert report.item_count == 2
    assert saved["schema_version"] == "careai-rag-eval-report-v1"
    assert saved["thresholds"]["keyword_relevance_min"] == 0.4
    assert saved["aggregate_metrics"]["retrieval_hit_rate"] == 1.0
    assert saved["passed"] is True
