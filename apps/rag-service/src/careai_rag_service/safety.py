import re

from careai_rag_service.schemas import RetrievedChunk

REJECT_PATTERNS = {
    "prompt_injection": re.compile(
        r"\b(ignore|bypass|override)\b.*\b(instruction|policy|system|developer)\b",
        re.IGNORECASE,
    ),
    "hidden_prompt_request": re.compile(
        r"\b(system prompt|developer message|hidden instruction|internal prompt)\b",
        re.IGNORECASE,
    ),
    "secret_request": re.compile(
        r"\b(secret|api key|password|token|private key|credential)\b",
        re.IGNORECASE,
    ),
}

MEDICAL_REVIEW_PATTERN = re.compile(
    r"\b(diagnos(?:e|is)|treat(?:ment)?|medication dose|symptom|clinical advice)\b",
    re.IGNORECASE,
)


def rejected_safety_flags(question: str) -> list[str]:
    return [flag for flag, pattern in REJECT_PATTERNS.items() if pattern.search(question)]


def advisory_safety_flags(question: str) -> list[str]:
    flags: list[str] = []
    if MEDICAL_REVIEW_PATTERN.search(question):
        flags.append("medical_diagnosis_or_treatment_request_human_review")
    return flags


def human_review_required(safety_flags: list[str]) -> bool:
    return any(flag.endswith("_human_review") for flag in safety_flags)


def groundedness_score(answer: str, retrieved_chunks: list[RetrievedChunk]) -> float:
    if not answer.strip() or not retrieved_chunks:
        return 0.0

    answer_terms = {
        term
        for term in re.findall(r"[a-z0-9_]+", answer.lower())
        if len(term) > 3 and not term.startswith("source_")
    }
    if not answer_terms:
        return 0.0

    source_terms: set[str] = set()
    for chunk in retrieved_chunks:
        source_terms.update(
            term
            for term in re.findall(r"[a-z0-9_]+", chunk.excerpt.lower())
            if len(term) > 3
        )

    overlap = len(answer_terms & source_terms) / len(answer_terms)
    cited_source_ids = {citation for citation in re.findall(r"\[([a-zA-Z0-9_.:-]+)\]", answer)}
    available_source_ids = {chunk.source_id for chunk in retrieved_chunks}
    citation_bonus = 0.2 if cited_source_ids & available_source_ids else 0.0
    return round(min(1.0, overlap + citation_bonus), 4)


def has_source_citation(answer: str, retrieved_chunks: list[RetrievedChunk]) -> bool:
    available_source_ids = {chunk.source_id for chunk in retrieved_chunks}
    cited_source_ids = {citation for citation in re.findall(r"\[([a-zA-Z0-9_.:-]+)\]", answer)}
    return bool(cited_source_ids & available_source_ids)
