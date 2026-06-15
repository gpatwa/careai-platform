import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from evaluate_rag.client import RagGatewayClient
from evaluate_rag.metrics import aggregate_metrics, evaluate_item, report_passed
from evaluate_rag.models import EvalItem, EvaluationReport, Thresholds

DEFAULT_EVAL_SET = Path("data/eval/rag_eval_set.jsonl")
DEFAULT_REPORT_PATH = Path("data/local/rag-eval-report.json")


def load_eval_set(path: str | Path) -> list[EvalItem]:
    eval_path = Path(path)
    items: list[EvalItem] = []
    for line_number, line in enumerate(eval_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(EvalItem.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"Invalid eval item at {eval_path}:{line_number}") from exc
    return items


def run_evaluation(
    *,
    rag_url: str,
    eval_set: str | Path,
    output: str | Path,
    thresholds: Thresholds,
    top_k: int = 4,
    control_plane_url: str | None = None,
    client: RagGatewayClient | None = None,
) -> EvaluationReport:
    items = load_eval_set(eval_set)
    rag_client = client or RagGatewayClient(rag_url)
    item_results = [
        evaluate_item(item, rag_client.query(item, top_k=top_k), thresholds=thresholds)
        for item in items
    ]
    aggregate = aggregate_metrics(item_results)
    report = EvaluationReport(
        generated_at=datetime.now(UTC).isoformat(),
        rag_url=rag_url,
        eval_set_uri=Path(eval_set).resolve().as_uri(),
        item_count=len(item_results),
        thresholds=thresholds,
        aggregate_metrics=aggregate,
        passed=report_passed(aggregate, thresholds),
        item_results=item_results,
    )

    output_path = write_report(report, output)
    registration = register_control_plane_evaluation(
        control_plane_url=control_plane_url,
        report=report,
        report_uri=output_path.resolve().as_uri(),
    )
    if registration:
        report.control_plane_registration = registration
        write_report(report, output)
    return report


def write_report(report: EvaluationReport, output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def register_control_plane_evaluation(
    *,
    control_plane_url: str | None,
    report: EvaluationReport,
    report_uri: str,
) -> dict[str, Any]:
    if not control_plane_url:
        return {"registered": False, "reason": "control_plane_url_not_configured"}

    payload = {
        "target_type": "rag",
        "target_id": report.rag_url,
        "metrics_json": report.aggregate_metrics.model_dump(mode="json"),
        "passed": report.passed,
        "report_uri": report_uri,
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(f"{control_plane_url.rstrip('/')}/evaluations", json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        return {
            "registered": False,
            "reason": "control_plane_unavailable",
            "error_type": exc.__class__.__name__,
        }

    return {
        "registered": True,
        "evaluation_run_id": body.get("id"),
        "target_type": body.get("target_type"),
        "target_id": body.get("target_id"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate RAG quality and safety.")
    parser.add_argument("--rag-url", default="http://localhost:8002")
    parser.add_argument("--eval-set", default=str(DEFAULT_EVAL_SET))
    parser.add_argument("--output", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--control-plane-url", default=os.getenv("CONTROL_PLANE_API_URL"))
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--retrieval-hit-rate-min", type=float, default=0.75)
    parser.add_argument("--citation-coverage-min", type=float, default=0.70)
    parser.add_argument("--keyword-relevance-min", type=float, default=0.45)
    parser.add_argument("--groundedness-min", type=float, default=0.45)
    parser.add_argument("--safety-flag-rate-max", type=float, default=0.25)
    parser.add_argument("--disallowed-claim-rate-max", type=float, default=0.0)
    parser.add_argument("--avg-latency-ms-max", type=int, default=3000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    thresholds = Thresholds(
        retrieval_hit_rate_min=args.retrieval_hit_rate_min,
        citation_coverage_min=args.citation_coverage_min,
        keyword_relevance_min=args.keyword_relevance_min,
        groundedness_min=args.groundedness_min,
        safety_flag_rate_max=args.safety_flag_rate_max,
        disallowed_claim_rate_max=args.disallowed_claim_rate_max,
        avg_latency_ms_max=args.avg_latency_ms_max,
    )
    report = run_evaluation(
        rag_url=args.rag_url,
        eval_set=args.eval_set,
        output=args.output,
        thresholds=thresholds,
        top_k=args.top_k,
        control_plane_url=args.control_plane_url,
    )
    print(
        json.dumps(
            {
                "report_path": str(Path(args.output)),
                "passed": report.passed,
                "item_count": report.item_count,
                "aggregate_metrics": report.aggregate_metrics.model_dump(mode="json"),
                "control_plane_registration": report.control_plane_registration,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
