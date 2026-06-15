# Responsible AI Guidelines

Version: 2026.06

These synthetic guidelines describe responsible AI controls for the careai-platform demo. They are intended for architecture review and interview discussion, not production compliance advice.

## Data Safety

Only synthetic healthcare-like data is allowed. Prompts, logs, traces, documents, embeddings, and evaluation fixtures must avoid real PHI, PII, credentials, and proprietary branding.

## Retrieval Governance

Retrieval must preserve document metadata, including document identifier, title, version, sensitivity class, source URI, and allowed roles. Role-based retrieval should filter results before context is passed to a model.

## Prompt Safety

RAG prompts should instruct the model to answer from retrieved context, say when evidence is insufficient, avoid clinical advice, and route safety-sensitive cases to a human reviewer.

## Evaluation

Evaluations should cover groundedness, refusal behavior, role filtering, source citation, stale-document detection, and unsafe data leakage. Failed evaluations block promotion until reviewed.

## Audit

Each RAG request should emit a correlation ID, actor role, prompt version, retrieved document identifiers, safety check result, and response disposition. Audit metadata must remain safe and synthetic.
