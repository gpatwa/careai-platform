from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RagQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="Synthetic user or service identifier.")
    role: str = Field(..., description="Caller role used for retrieval filtering.")
    question: str = Field(..., min_length=3, description="Healthcare operations question.")
    conversation_id: str | None = Field(default=None)
    prompt_template_id: str | None = Field(default=None)
    top_k: int = Field(default=4, ge=1, le=10)
    tenant_id: str | None = Field(
        default=None,
        description="Optional tenant or customer identifier.",
    )
    workflow_run_id: str | None = Field(default=None, description="Optional linked workflow run.")
    payment_integrity_case_id: str | None = Field(
        default=None,
        description="Optional synthetic payment integrity case identifier.",
    )


class RetrievedChunk(BaseModel):
    source_id: str
    doc_id: str
    chunk_id: str
    title: str
    source_uri: str
    score: float
    excerpt: str


class Citation(BaseModel):
    source_id: str
    doc_id: str
    title: str
    chunk_id: str
    source_uri: str


class ProviderMetadata(BaseModel):
    provider: str
    model_name: str
    fallback_mode: bool = False


class PromptMetadata(BaseModel):
    prompt_template_id: str
    prompt_version: str
    source: str


class RetrievalMetadata(BaseModel):
    provider: str
    top_k: int
    returned_chunks: int
    role_filter: str
    source_ids: list[str]


class AgentAttemptMetadata(BaseModel):
    attempt_number: int
    retrieval_query: str
    returned_chunks: int
    source_ids: list[str]
    verification_passed: bool
    verification_flags: list[str]
    groundedness_score: float = Field(..., ge=0, le=1)


class AgentLoopMetadata(BaseModel):
    attempt_count: int
    verification_passed: bool
    final_groundedness_score: float = Field(..., ge=0, le=1)
    attempts: list[AgentAttemptMetadata]


class RagQueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    groundedness_score: float = Field(..., ge=0, le=1)
    safety_flags: list[str]
    human_review_required: bool
    provider_metadata: ProviderMetadata
    prompt: PromptMetadata
    retrieval_metadata: RetrievalMetadata
    agent_loop: AgentLoopMetadata
    retrieved_chunks: list[RetrievedChunk]
    correlation_id: str
    tenant_id: str = "default"
    workflow_run_id: str | None = None
    payment_integrity_case_id: str | None = None


class EvaluateAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=3)
    answer: str = Field(..., min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)


class EvaluateAnswerResponse(BaseModel):
    groundedness_score: float = Field(..., ge=0, le=1)
    passed: bool
    safety_flags: list[str]
    citation_count: int
    correlation_id: str


class PromptTemplateSummary(BaseModel):
    id: str
    name: str
    version: str
    status: str
    owner: str
    source: str
    safety_notes: str = ""


class PromptTemplate(BaseModel):
    id: str
    name: str
    version: str
    template_text: str
    owner: str
    safety_notes: str = ""
    status: str = "approved"
    source: str = "local"


class AuditMetadata(BaseModel):
    prompt_template_id: str
    prompt_version: str
    retrieved_source_ids: list[str]
    model_name: str
    provider: str
    safety_flags: list[str]
    role: str
    human_review_required: bool
    conversation_present: bool
    extra: dict[str, Any] = Field(default_factory=dict)
