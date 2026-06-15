from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    expected_sources: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    disallowed_claims: list[str] = Field(default_factory=list)
    role: str


class RagServiceResult(BaseModel):
    status_code: int = 200
    answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    groundedness_score: float = 0.0
    safety_flags: list[str] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    prompt: dict[str, Any] = Field(default_factory=dict)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = ""
    latency_ms: int = 0
    token_count: int | None = None
    error: str | None = None


class ItemMetricResult(BaseModel):
    question: str
    role: str
    expected_sources: list[str]
    expected_keywords: list[str]
    retrieval_hit: bool
    citation_coverage: float
    keyword_relevance: float
    groundedness: float
    safety_flagged: bool
    latency_ms: int
    token_count: int | None
    disallowed_claims_found: list[str]
    passed: bool
    response_status_code: int
    correlation_id: str
    retrieved_source_ids: list[str]
    cited_source_ids: list[str]


class Thresholds(BaseModel):
    retrieval_hit_rate_min: float = 0.75
    citation_coverage_min: float = 0.70
    keyword_relevance_min: float = 0.45
    groundedness_min: float = 0.45
    safety_flag_rate_max: float = 0.25
    disallowed_claim_rate_max: float = 0.0
    avg_latency_ms_max: int = 3000


class AggregateMetrics(BaseModel):
    retrieval_hit_rate: float
    citation_coverage: float
    keyword_relevance: float
    groundedness: float
    safety_flag_rate: float
    disallowed_claim_rate: float
    avg_latency_ms: float
    p95_latency_ms: int
    token_count: int | None


class EvaluationReport(BaseModel):
    schema_version: str = "careai-rag-eval-report-v1"
    generated_at: str
    rag_url: str
    eval_set_uri: str
    item_count: int
    thresholds: Thresholds
    aggregate_metrics: AggregateMetrics
    passed: bool
    item_results: list[ItemMetricResult]
    control_plane_registration: dict[str, Any] = Field(default_factory=dict)
