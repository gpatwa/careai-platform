from dataclasses import dataclass

from careai_rag_service.llm import LLMProvider, LLMResponse
from careai_rag_service.retrieval import Retriever
from careai_rag_service.safety import groundedness_score, has_source_citation
from careai_rag_service.schemas import PromptTemplate, RetrievedChunk

MIN_GROUNDEDNESS_SCORE = 0.55
MAX_AGENT_ATTEMPTS = 2


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    groundedness_score: float
    flags: list[str]
    feedback_messages: list[str]


@dataclass(frozen=True)
class AgentAttempt:
    attempt_number: int
    retrieval_query: str
    retrieved_chunks: list[RetrievedChunk]
    llm_response: LLMResponse
    verification: VerificationResult


@dataclass(frozen=True)
class AgentLoopResult:
    final_attempt: AgentAttempt
    attempts: list[AgentAttempt]
    combined_safety_flags: list[str]


def run_agent_loop(
    *,
    retriever: Retriever,
    llm_provider: LLMProvider,
    prompt: PromptTemplate,
    question: str,
    role: str,
    top_k: int,
    correlation_id: str,
    base_safety_flags: list[str],
    max_attempts: int = MAX_AGENT_ATTEMPTS,
) -> AgentLoopResult:
    attempts: list[AgentAttempt] = []
    feedback_messages: list[str] = []

    for attempt_number in range(1, max_attempts + 1):
        retrieval_query = build_retry_query(
            question=question,
            prior_attempts=attempts,
            feedback_messages=feedback_messages,
        )
        retrieved_chunks = retriever.search(
            query=retrieval_query,
            role=role,
            top_k=min(top_k + attempt_number - 1, 10),
        )
        llm_response = llm_provider.generate_answer(
            question=question,
            prompt=prompt,
            retrieved_chunks=retrieved_chunks,
            safety_flags=base_safety_flags,
            correlation_id=correlation_id,
            feedback_messages=feedback_messages,
            attempt_number=attempt_number,
            retrieval_query=retrieval_query,
        )
        verification = verify_answer(
            answer=llm_response.answer,
            retrieved_chunks=retrieved_chunks,
        )
        attempt = AgentAttempt(
            attempt_number=attempt_number,
            retrieval_query=retrieval_query,
            retrieved_chunks=retrieved_chunks,
            llm_response=llm_response,
            verification=verification,
        )
        attempts.append(attempt)
        if verification.passed:
            break
        feedback_messages = verification.feedback_messages

    final_attempt = attempts[-1]
    combined_flags = list(dict.fromkeys(base_safety_flags + final_attempt.verification.flags))
    if len(attempts) > 1:
        combined_flags.append("verification_retry_used")
    if not final_attempt.verification.passed:
        combined_flags.append("rag_quality_retry_exhausted_human_review")
    return AgentLoopResult(
        final_attempt=final_attempt,
        attempts=attempts,
        combined_safety_flags=list(dict.fromkeys(combined_flags)),
    )


def verify_answer(*, answer: str, retrieved_chunks: list[RetrievedChunk]) -> VerificationResult:
    flags: list[str] = []
    feedback_messages: list[str] = []
    score = groundedness_score(answer, retrieved_chunks)

    if not retrieved_chunks:
        flags.append("no_role_authorized_context_found")
        feedback_messages.append(
            "No approved context was retrieved. State that context is insufficient "
            "and route to human review."
        )
    if retrieved_chunks and not has_source_citation(answer, retrieved_chunks):
        flags.append("missing_inline_citations")
        feedback_messages.append(
            "Revise the answer with inline citations for each policy claim using "
            "the retrieved source ids."
        )
    if retrieved_chunks and score < MIN_GROUNDEDNESS_SCORE:
        flags.append("low_groundedness")
        feedback_messages.append(
            "Stay closer to the retrieved policy language and avoid claims not "
            "supported by the cited excerpts."
        )

    return VerificationResult(
        passed=not flags,
        groundedness_score=score,
        flags=flags,
        feedback_messages=feedback_messages,
    )


def build_retry_query(
    *,
    question: str,
    prior_attempts: list[AgentAttempt],
    feedback_messages: list[str],
) -> str:
    if not prior_attempts:
        return question

    if any("No approved context" in message for message in feedback_messages):
        return f"{question} policy criteria escalation documentation review requirements"

    if any("inline citations" in message for message in feedback_messages):
        return f"{question} source ids policy citation requirements"

    return f"{question} policy criteria decision workflow"
