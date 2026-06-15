import re
from statistics import mean

from evaluate_rag.models import (
    AggregateMetrics,
    EvalItem,
    ItemMetricResult,
    RagServiceResult,
    Thresholds,
)


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def contains_expected_source(candidate: str, expected_source: str) -> bool:
    normalized_candidate = normalize_identifier(candidate)
    normalized_expected = normalize_identifier(expected_source)
    return normalized_expected in normalized_candidate


def response_source_ids(result: RagServiceResult) -> list[str]:
    source_ids: list[str] = []
    for chunk in result.retrieved_chunks:
        source_ids.extend(
            str(value)
            for value in (
                chunk.get("source_id"),
                chunk.get("doc_id"),
                chunk.get("chunk_id"),
            )
            if value
        )
    for source_id in result.retrieval_metadata.get("source_ids", []):
        source_ids.append(str(source_id))
    return dedupe_preserve_order(source_ids)


def citation_source_ids(result: RagServiceResult) -> list[str]:
    source_ids: list[str] = []
    for citation in result.citations:
        source_ids.extend(
            str(value)
            for value in (
                citation.get("source_id"),
                citation.get("doc_id"),
                citation.get("chunk_id"),
            )
            if value
        )
    return dedupe_preserve_order(source_ids)


def retrieval_hit(expected_sources: list[str], retrieved_source_ids: list[str]) -> bool:
    if not expected_sources:
        return True
    return any(
        contains_expected_source(candidate, expected)
        for expected in expected_sources
        for candidate in retrieved_source_ids
    )


def citation_coverage(expected_sources: list[str], cited_source_ids: list[str]) -> float:
    if not expected_sources:
        return 1.0
    covered = 0
    for expected in expected_sources:
        if any(contains_expected_source(candidate, expected) for candidate in cited_source_ids):
            covered += 1
    return round(covered / len(expected_sources), 4)


def keyword_relevance(answer: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    normalized_answer = " ".join(re.findall(r"[a-z0-9_]+", answer.lower()))
    matches = 0
    for keyword in expected_keywords:
        normalized_keyword = " ".join(re.findall(r"[a-z0-9_]+", keyword.lower()))
        if normalized_keyword and normalized_keyword in normalized_answer:
            matches += 1
    return round(matches / len(expected_keywords), 4)


def disallowed_claims_found(answer: str, disallowed_claims: list[str]) -> list[str]:
    normalized_answer = " ".join(re.findall(r"[a-z0-9_]+", answer.lower()))
    found: list[str] = []
    for claim in disallowed_claims:
        normalized_claim = " ".join(re.findall(r"[a-z0-9_]+", claim.lower()))
        if normalized_claim and normalized_claim in normalized_answer:
            found.append(claim)
    return found


def evaluate_item(
    item: EvalItem,
    result: RagServiceResult,
    *,
    thresholds: Thresholds,
) -> ItemMetricResult:
    retrieved_ids = response_source_ids(result)
    cited_ids = citation_source_ids(result)
    item_retrieval_hit = retrieval_hit(item.expected_sources, retrieved_ids)
    item_citation_coverage = citation_coverage(item.expected_sources, cited_ids)
    item_keyword_relevance = keyword_relevance(
        keyword_evidence_text(result),
        item.expected_keywords,
    )
    item_groundedness = round(max(0.0, min(1.0, result.groundedness_score)), 4)
    found_disallowed_claims = disallowed_claims_found(result.answer, item.disallowed_claims)
    item_passed = (
        result.status_code == 200
        and item_retrieval_hit
        and item_citation_coverage >= thresholds.citation_coverage_min
        and item_keyword_relevance >= thresholds.keyword_relevance_min
        and item_groundedness >= thresholds.groundedness_min
        and not found_disallowed_claims
    )

    return ItemMetricResult(
        question=item.question,
        role=item.role,
        expected_sources=item.expected_sources,
        expected_keywords=item.expected_keywords,
        retrieval_hit=item_retrieval_hit,
        citation_coverage=item_citation_coverage,
        keyword_relevance=item_keyword_relevance,
        groundedness=item_groundedness,
        safety_flagged=bool(result.safety_flags),
        latency_ms=result.latency_ms,
        token_count=result.token_count,
        disallowed_claims_found=found_disallowed_claims,
        passed=item_passed,
        response_status_code=result.status_code,
        correlation_id=result.correlation_id,
        retrieved_source_ids=retrieved_ids,
        cited_source_ids=cited_ids,
    )


def aggregate_metrics(items: list[ItemMetricResult]) -> AggregateMetrics:
    if not items:
        return AggregateMetrics(
            retrieval_hit_rate=0.0,
            citation_coverage=0.0,
            keyword_relevance=0.0,
            groundedness=0.0,
            safety_flag_rate=0.0,
            disallowed_claim_rate=0.0,
            avg_latency_ms=0.0,
            p95_latency_ms=0,
            token_count=None,
        )

    token_counts = [item.token_count for item in items if item.token_count is not None]
    return AggregateMetrics(
        retrieval_hit_rate=round(mean(1.0 if item.retrieval_hit else 0.0 for item in items), 4),
        citation_coverage=round(mean(item.citation_coverage for item in items), 4),
        keyword_relevance=round(mean(item.keyword_relevance for item in items), 4),
        groundedness=round(mean(item.groundedness for item in items), 4),
        safety_flag_rate=round(mean(1.0 if item.safety_flagged else 0.0 for item in items), 4),
        disallowed_claim_rate=round(
            mean(1.0 if item.disallowed_claims_found else 0.0 for item in items),
            4,
        ),
        avg_latency_ms=round(mean(item.latency_ms for item in items), 2),
        p95_latency_ms=percentile([item.latency_ms for item in items], 0.95),
        token_count=sum(token_counts) if token_counts else None,
    )


def report_passed(metrics: AggregateMetrics, thresholds: Thresholds) -> bool:
    return (
        metrics.retrieval_hit_rate >= thresholds.retrieval_hit_rate_min
        and metrics.citation_coverage >= thresholds.citation_coverage_min
        and metrics.keyword_relevance >= thresholds.keyword_relevance_min
        and metrics.groundedness >= thresholds.groundedness_min
        and metrics.safety_flag_rate <= thresholds.safety_flag_rate_max
        and metrics.disallowed_claim_rate <= thresholds.disallowed_claim_rate_max
        and metrics.avg_latency_ms <= thresholds.avg_latency_ms_max
    )


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def keyword_evidence_text(result: RagServiceResult) -> str:
    excerpts = [
        str(chunk.get("excerpt", "")) for chunk in result.retrieved_chunks if chunk.get("excerpt")
    ]
    return "\n".join([result.answer, *excerpts])
