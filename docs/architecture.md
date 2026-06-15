# Architecture

`careai-platform` is a local-first enterprise demo for MLOps and LLMOps workflows using synthetic healthcare-like data only.

## Local Runtime

- PostgreSQL stores platform metadata, lineage records, registry metadata, and audit events.
- Redis supports online feature/cache demos.
- MLflow provides local experiment tracking.
- Azurite provides optional blob-storage-like local development.
- FastAPI services expose the control plane, model inference, and RAG workflows.
- The web console provides a small TypeScript UI for interview demos.

## Service Boundaries

- `apps/control-plane-api`: orchestration, metadata, registry, promotion, monitoring, audit, and governance workflows. It tracks dataset assets, model artifacts, deployments, prompt templates, evaluation runs, approvals, audit events, prediction events, model error events, and drift snapshots through a FastAPI/SQLAlchemy service with Alembic migrations for persistent databases.
- `apps/inference-service`: synthetic claims-risk inference with configurable local or MLflow model loading, Pydantic feature validation, feature freshness checks, safe prediction audit and monitoring events, SLO-oriented error events, `prediction.created` publication, and deterministic fallback scoring when no model is available.
- `apps/rag-service`: document ingestion, retrieval, prompt registry, safety checks, RAG-facing endpoints, and `rag.query_answered` publication without raw question or answer text.
- `libs/common-python`: shared settings, JSON logging, correlation IDs, audit schemas, event schemas/publishers, observability helpers, and common errors.

## MLOps Pipeline

- `pipelines/train-claims-risk`: generates deterministic synthetic claims-risk data, trains a scikit-learn model, logs parameters/metrics/model artifacts to MLflow, writes control-plane-compatible metadata, and optionally registers the candidate model with `control-plane-api`.
- `pipelines/ingest-rag`: loads synthetic healthcare-operations Markdown documents, chunks text, generates embeddings through a provider abstraction, and writes either Azure AI Search chunks or a local JSON vector index fallback.
- `pipelines/evaluate-rag`: runs a synthetic RAG evaluation set against `rag-service`, writes a JSON quality/safety report, and optionally registers aggregate metrics as a control-plane `EvaluationRun`.

## LLMOps Ingestion

Synthetic policy and playbook documents live under `data/synthetic_docs`. Ingestion preserves document metadata (`doc_id`, `title`, `version`, `sensitivity_class`, `source_uri`, `allowed_roles`) on every chunk. Local demos use deterministic hash embeddings and a JSON vector index under `data/local/`. Azure demos use Azure OpenAI embeddings and Azure AI Search with a vector field plus searchable text for hybrid retrieval.

Role-based retrieval is modeled as document-level filtering before prompt construction. Azure queries use `allowed_roles/any(...)` filters; the local fallback applies the same filter in process before scoring.

`apps/rag-service` is the LLM gateway. It retrieves authorized chunks, selects an approved prompt from `control-plane-api` when available, otherwise uses a local default prompt, and routes generation to Azure OpenAI chat when configured or a deterministic local mock provider for tests and offline demos. Responses include citations, prompt version, provider metadata, retrieval metadata, groundedness score, safety flags, and the active correlation ID.

Safety controls reject prompt-injection and secret-exfiltration attempts before retrieval. Medical diagnosis or treatment requests are answered only as policy-context responses and flagged for human review. Audit events sent to the control plane include prompt id/version, retrieved source ids, model/provider metadata, role, and safety flags; raw question and answer text are intentionally excluded.

RAG evaluation is the pre-promotion LLMOps gate. The evaluator measures retrieval hit rate, citation coverage, keyword relevance, groundedness, safety flag rate, disallowed-claim rate, latency, and provider token counts when available. Failed thresholds block promotion until the prompt, retrieval index, safety policy, or model configuration is reviewed.

## Monitoring

The control plane stores prediction events for synthetic aggregate claims-risk features, scores, risk bands, latency, model version, and correlation IDs. Drift checks compare baseline training feature distributions from model lineage or a request body against recent serving distributions. Numeric utilization features are binned before PSI calculations so training and serving distributions remain stable and interpretable. The demo uses PSI-style metrics with deterministic `green`, `yellow`, and `red` statuses.

Training-serving skew is represented by feature-level distribution differences. A `red` drift snapshot recommends rollback or human review. Latency monitoring tracks average and p95 latency; business monitoring tracks prediction score and high-risk rate. Error-rate monitoring is backed by structured model error events and SLO thresholds in the summary contract. The `careai-drift-check` CLI provides a scheduled drift-check hook for cron, GitHub Actions, or Azure Container Apps Jobs.

## Event Backbone

The platform includes a Kafka/Event Hubs-style event backbone abstraction in `libs/common-python`. Event envelopes carry `event_id`, `event_type`, `schema_version`, `source`, `subject`, `correlation_id`, `created_at`, and a schema-versioned payload. Supported event contracts are:

- `prediction.created`
- `audit.created`
- `model.drift_detected`
- `model.promotion_requested`
- `rag.query_answered`
- `feedback.received`

Local development uses `LocalLoggingEventPublisher`, which logs safe event metadata and can append envelopes to `EVENT_STREAM_LOCAL_PATH` as JSONL. This JSONL file acts like a compact local topic for tests and interview demos. Azure deployments use `AzureEventHubsPublisher` when `AZURE_EVENTHUB_NAME` is set with either `AZURE_EVENTHUB_FULLY_QUALIFIED_NAMESPACE` for managed identity or `AZURE_EVENTHUB_CONNECTION_STRING` for secret-backed demos.

The mapping to Kafka/pub-sub is intentionally direct:

- Event Hubs namespace or Kafka cluster: shared streaming backbone.
- Event hub or Kafka topic: `careai-events`.
- Event type: routing key for consumers and dashboards.
- Correlation ID: distributed trace and audit join key.
- Schema version: compatibility boundary for producers and consumers.
- Consumer group: each projection job, monitor, or retraining trigger reads independently.

`careai-event-consumer` is the local projection job. It reads the JSONL stream once and materializes operational views into PostgreSQL or SQLite: `prediction.created` becomes `PredictionEvent`, `model.drift_detected` becomes `DriftSnapshot`, and governance/RAG/feedback events become safe `AuditEvent` rows. In Azure, the same pattern would run as an Azure Container Apps Job or Function subscribed to Event Hubs consumer groups. Downstream extensions can add retraining triggers, drift-alert notifications, human-feedback aggregation, or feature-store refreshes without coupling producers to those workflows.

## Cloud Target

The default Azure path is implemented in `infra/terraform`: Docker images are pushed to Azure Container Registry and deployed to Azure Container Apps with a shared user-assigned managed identity. Supporting Azure services include Azure AI Search, Key Vault, Storage Account, Event Hubs, Log Analytics, and Application Insights. PostgreSQL, Redis, and Azure ML are Terraform-controlled optional resources so demo environments can avoid unnecessary cost. AKS and Helm remain optional extensions.
