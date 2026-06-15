import logging
import os

from careai_common.config import load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.logging import setup_json_logging
from fastapi import FastAPI, HTTPException, Request, Response, status

from careai_rag_service.audit import AuditClient
from careai_rag_service.llm import LLMProvider, llm_provider_from_env
from careai_rag_service.prompts import PromptRegistry
from careai_rag_service.retrieval import Retriever, retriever_from_env
from careai_rag_service.safety import (
    advisory_safety_flags,
    groundedness_score,
    has_source_citation,
    human_review_required,
    rejected_safety_flags,
)
from careai_rag_service.schemas import (
    Citation,
    EvaluateAnswerRequest,
    EvaluateAnswerResponse,
    PromptMetadata,
    PromptTemplateSummary,
    ProviderMetadata,
    RagQueryRequest,
    RagQueryResponse,
    RetrievalMetadata,
    RetrievedChunk,
)

settings = load_settings("rag-service", 8002)
setup_json_logging(settings.service_name, settings.log_level)
logger = logging.getLogger(__name__)


async def correlation_middleware(request: Request, call_next) -> Response:
    token = set_correlation_id(request.headers.get("x-correlation-id"))
    try:
        response = await call_next(request)
        response.headers["x-correlation-id"] = ensure_correlation_id()
        return response
    finally:
        clear_correlation_id(token)


def create_app(
    *,
    retriever: Retriever | None = None,
    llm_provider: LLMProvider | None = None,
    prompt_registry: PromptRegistry | None = None,
    audit_client: AuditClient | None = None,
) -> FastAPI:
    runtime_retriever = retriever or retriever_from_env()
    runtime_llm_provider = llm_provider or llm_provider_from_env()
    runtime_prompt_registry = prompt_registry or PromptRegistry(os.getenv("CONTROL_PLANE_API_URL"))
    runtime_audit_client = audit_client or AuditClient(
        os.getenv("CONTROL_PLANE_API_URL"),
        enabled=os.getenv("RAG_AUDIT_ENABLED", "true").lower() == "true",
    )

    application = FastAPI(
        title="careai-platform RAG Service",
        version="0.1.0",
        description=(
            "Production-style RAG gateway for synthetic healthcare operations documents "
            "with prompt registry, safety checks, citations, and audit logging."
        ),
        openapi_tags=[
            {"name": "Health", "description": "Service health and readiness."},
            {"name": "RAG", "description": "Question answering and answer evaluation."},
            {"name": "Prompts", "description": "Prompt registry views."},
        ],
    )
    application.state.retriever = runtime_retriever
    application.state.llm_provider = runtime_llm_provider
    application.state.prompt_registry = runtime_prompt_registry
    application.state.audit_client = runtime_audit_client
    application.middleware("http")(correlation_middleware)
    register_routes(application)
    return application


def register_routes(application: FastAPI) -> None:
    @application.get(
        "/healthz",
        tags=["Health"],
        summary="Service health check",
        description="Returns service liveness.",
    )
    def healthz() -> dict[str, str]:
        logger.info("health check")
        return {"status": "ok", "service": settings.service_name}

    @application.get(
        "/readyz",
        tags=["Health"],
        summary="Service readiness check",
        description="Returns configured retrieval, prompt registry, and LLM provider status.",
    )
    def readyz() -> dict[str, object]:
        return {
            "status": "ready",
            "service": settings.service_name,
            "dependencies": {
                "retrieval": application.state.retriever.provider_name,
                "prompt_registry": (
                    "control-plane"
                    if application.state.prompt_registry.control_plane_url
                    else "local-default"
                ),
                "control_plane_audit": (
                    "configured"
                    if application.state.audit_client.control_plane_url
                    else "not_configured"
                ),
            },
        }

    @application.get(
        "/rag/prompts",
        response_model=list[PromptTemplateSummary],
        tags=["Prompts"],
        summary="List available RAG prompts",
        description=(
            "Lists approved control-plane prompts when available, otherwise the local default."
        ),
    )
    def get_prompts() -> list[PromptTemplateSummary]:
        return application.state.prompt_registry.get_prompts()

    @application.post(
        "/rag/query",
        response_model=RagQueryResponse,
        tags=["RAG"],
        summary="Answer a synthetic healthcare operations question",
        description=(
            "Retrieves role-authorized chunks, applies safety checks, generates an answer, "
            "returns citations, and emits a safe audit event."
        ),
    )
    def query_rag(payload: RagQueryRequest) -> RagQueryResponse:
        reject_flags = rejected_safety_flags(payload.question)
        if reject_flags:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Question rejected by safety policy.",
                    "safety_flags": reject_flags,
                    "correlation_id": ensure_correlation_id(),
                },
            )

        safety_flags = advisory_safety_flags(payload.question)
        chunks = application.state.retriever.search(
            query=payload.question,
            role=payload.role,
            top_k=payload.top_k,
        )
        if not chunks:
            safety_flags.append("no_role_authorized_context_found")

        prompt = application.state.prompt_registry.select_prompt(payload.prompt_template_id)
        correlation_id = ensure_correlation_id()
        llm_response = application.state.llm_provider.generate_answer(
            question=payload.question,
            prompt=prompt,
            retrieved_chunks=chunks,
            safety_flags=safety_flags,
            correlation_id=correlation_id,
        )
        citations = citations_from_chunks(chunks)
        if chunks and not has_source_citation(llm_response.answer, chunks):
            safety_flags.append("missing_inline_citations")

        score = groundedness_score(llm_response.answer, chunks)
        source_ids = [chunk.source_id for chunk in chunks]
        review_required = human_review_required(safety_flags)

        logger.info(
            "RAG query answered",
            extra={
                "role": payload.role,
                "retrieved_chunk_count": len(chunks),
                "provider": llm_response.provider,
                "model_name": llm_response.model_name,
                "prompt_template_id": prompt.id,
                "prompt_version": prompt.version,
                "safety_flag_count": len(safety_flags),
                "human_review_required": review_required,
            },
        )

        application.state.audit_client.send_rag_query_event(
            user_id=payload.user_id,
            correlation_id=correlation_id,
            metadata={
                "prompt_template_id": prompt.id,
                "prompt_version": prompt.version,
                "retrieved_source_ids": source_ids,
                "model_name": llm_response.model_name,
                "provider": llm_response.provider,
                "safety_flags": safety_flags,
                "role": payload.role,
                "human_review_required": review_required,
                "conversation_present": payload.conversation_id is not None,
            },
        )

        return RagQueryResponse(
            answer=llm_response.answer,
            citations=citations,
            groundedness_score=score,
            safety_flags=safety_flags,
            human_review_required=review_required,
            provider_metadata=ProviderMetadata(
                provider=llm_response.provider,
                model_name=llm_response.model_name,
                fallback_mode=llm_response.fallback_mode,
            ),
            prompt=PromptMetadata(
                prompt_template_id=prompt.id,
                prompt_version=prompt.version,
                source=prompt.source,
            ),
            retrieval_metadata=RetrievalMetadata(
                provider=application.state.retriever.provider_name,
                top_k=payload.top_k,
                returned_chunks=len(chunks),
                role_filter=payload.role,
                source_ids=source_ids,
            ),
            retrieved_chunks=chunks,
            correlation_id=correlation_id,
        )

    @application.post(
        "/rag/evaluate-answer",
        response_model=EvaluateAnswerResponse,
        tags=["RAG"],
        summary="Evaluate a RAG answer",
        description="Runs deterministic citation and groundedness checks for a generated answer.",
    )
    def evaluate_answer(payload: EvaluateAnswerRequest) -> EvaluateAnswerResponse:
        safety_flags = advisory_safety_flags(payload.question)
        if payload.retrieved_chunks and not has_source_citation(
            payload.answer,
            payload.retrieved_chunks,
        ):
            safety_flags.append("missing_inline_citations")
        if not payload.citations:
            safety_flags.append("missing_citation_records")

        score = groundedness_score(payload.answer, payload.retrieved_chunks)
        return EvaluateAnswerResponse(
            groundedness_score=score,
            passed=score >= 0.5 and not any(flag.startswith("missing_") for flag in safety_flags),
            safety_flags=safety_flags,
            citation_count=len(payload.citations),
            correlation_id=ensure_correlation_id(),
        )


def citations_from_chunks(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            source_id=chunk.source_id,
            doc_id=chunk.doc_id,
            title=chunk.title,
            chunk_id=chunk.chunk_id,
            source_uri=chunk.source_uri,
        )
        for chunk in chunks
    ]


app = create_app()
