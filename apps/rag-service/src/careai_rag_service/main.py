import logging
import os
from time import perf_counter

from careai_common.config import load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.events import EventPublisher, build_event, event_publisher_from_env
from careai_common.logging import setup_json_logging
from careai_common.observability import instrument_fastapi_app
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from careai_rag_service.agent import run_agent_loop
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
    AgentAttemptMetadata,
    AgentLoopMetadata,
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
setup_json_logging(settings.service_name, settings.log_level, settings.environment)
logger = logging.getLogger(__name__)


def cors_allowed_origins() -> list[str]:
    configured = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


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
    event_publisher: EventPublisher | None = None,
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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.retriever = runtime_retriever
    application.state.llm_provider = runtime_llm_provider
    application.state.prompt_registry = runtime_prompt_registry
    application.state.audit_client = runtime_audit_client
    application.state.event_publisher = event_publisher or event_publisher_from_env(
        settings.service_name
    )
    instrument_fastapi_app(application, settings)
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
        prompt = application.state.prompt_registry.select_prompt(payload.prompt_template_id)
        correlation_id = ensure_correlation_id()
        tenant_id = payload.tenant_id or settings.default_tenant_id
        agent_started_at = perf_counter()
        agent_result = run_agent_loop(
            retriever=application.state.retriever,
            llm_provider=application.state.llm_provider,
            prompt=prompt,
            question=payload.question,
            role=payload.role,
            top_k=payload.top_k,
            correlation_id=correlation_id,
            base_safety_flags=safety_flags,
        )
        agent_latency_ms = max((perf_counter() - agent_started_at) * 1000, 0.0)
        final_attempt = agent_result.final_attempt
        chunks = final_attempt.retrieved_chunks
        llm_response = final_attempt.llm_response
        citations = citations_from_chunks(chunks)
        score = final_attempt.verification.groundedness_score
        safety_flags = agent_result.combined_safety_flags
        source_ids = [chunk.source_id for chunk in chunks]
        review_required = human_review_required(safety_flags)
        attempt_count = len(agent_result.attempts)
        verification_passed = final_attempt.verification.passed
        retrieval_latency_ms = round(agent_latency_ms / max(attempt_count, 1), 2)
        llm_latency_ms = retrieval_latency_ms

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
                "attempt_count": attempt_count,
                "verification_passed": verification_passed,
                "retrieval_latency_ms": int(retrieval_latency_ms),
                "llm_latency_ms": int(llm_latency_ms),
            },
        )
        application.state.observability.record_rag_query(
            prompt_version=prompt.version,
            provider=llm_response.provider,
            safety_flags=safety_flags,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            fallback_mode=llm_response.fallback_mode,
        )

        application.state.audit_client.send_rag_query_event(
            user_id=payload.user_id,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            metadata={
                "prompt_template_id": prompt.id,
                "prompt_version": prompt.version,
                "retrieved_source_ids": source_ids,
                "model_name": llm_response.model_name,
                "provider": llm_response.provider,
                "safety_flags": safety_flags,
                "role": payload.role,
                "tenant_id": tenant_id,
                "workflow_run_id": payload.workflow_run_id,
                "payment_integrity_case_id": payload.payment_integrity_case_id,
                "human_review_required": review_required,
                "attempt_count": attempt_count,
                "verification_passed": verification_passed,
                "verification_flags": final_attempt.verification.flags,
                "conversation_present": payload.conversation_id is not None,
            },
        )
        if payload.workflow_run_id:
            application.state.audit_client.send_workflow_signal(
                workflow_run_id=payload.workflow_run_id,
                signal_type="policy_answered",
                actor="rag-service",
                tenant_id=tenant_id,
                signal_metadata={
                    "retrieved_source_ids": source_ids,
                    "role": payload.role,
                    "human_review_required": review_required,
                    "safety_flags": safety_flags,
                    "model_name": llm_response.model_name,
                    "provider": llm_response.provider,
                    "payment_integrity_case_id": payload.payment_integrity_case_id,
                    "source_ids": source_ids,
                    "attempt_count": attempt_count,
                    "verification_passed": verification_passed,
                    "verification_flags": final_attempt.verification.flags,
                },
            )
        publish_event_safely(
            application.state.event_publisher,
            build_event(
                event_type="rag.query_answered",
                source=settings.service_name,
                subject=f"conversation/{payload.conversation_id or correlation_id}",
                correlation_id=correlation_id,
                payload={
                    "user_id": payload.user_id,
                    "role": payload.role,
                    "prompt_template_id": prompt.id,
                    "prompt_version": prompt.version,
                    "tenant_id": tenant_id,
                    "workflow_run_id": payload.workflow_run_id,
                    "payment_integrity_case_id": payload.payment_integrity_case_id,
                    "retrieved_source_ids": source_ids,
                    "model_name": llm_response.model_name,
                    "provider": llm_response.provider,
                    "safety_flags": safety_flags,
                    "human_review_required": review_required,
                    "groundedness_score": score,
                    "fallback_mode": llm_response.fallback_mode,
                    "attempt_count": attempt_count,
                    "verification_passed": verification_passed,
                    "verification_flags": final_attempt.verification.flags,
                },
            ),
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
            agent_loop=AgentLoopMetadata(
                attempt_count=attempt_count,
                verification_passed=verification_passed,
                final_groundedness_score=score,
                attempts=[
                    AgentAttemptMetadata(
                        attempt_number=attempt.attempt_number,
                        retrieval_query=attempt.retrieval_query,
                        returned_chunks=len(attempt.retrieved_chunks),
                        source_ids=[chunk.source_id for chunk in attempt.retrieved_chunks],
                        verification_passed=attempt.verification.passed,
                        verification_flags=attempt.verification.flags,
                        groundedness_score=attempt.verification.groundedness_score,
                    )
                    for attempt in agent_result.attempts
                ],
            ),
            retrieved_chunks=chunks,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            workflow_run_id=payload.workflow_run_id,
            payment_integrity_case_id=payload.payment_integrity_case_id,
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


def publish_event_safely(event_publisher: EventPublisher, event) -> bool:
    try:
        return event_publisher.publish(event)
    except Exception as exc:
        logger.warning(
            "event publish failed",
            extra={"event_type": event.event_type, "error": str(exc)},
        )
        return False


app = create_app()
