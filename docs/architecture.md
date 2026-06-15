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
- `apps/inference-service`: synthetic claims-risk inference with configurable local or MLflow model loading, Pydantic feature validation, feature freshness checks, safe prediction audit and monitoring events, SLO-oriented error events, and deterministic fallback scoring when no model is available.
- `apps/rag-service`: document ingestion, retrieval, prompt registry, safety checks, and RAG-facing endpoints.
- `libs/common-python`: shared settings, JSON logging, correlation IDs, audit schemas, and common errors.

## MLOps Pipeline

- `pipelines/train-claims-risk`: generates deterministic synthetic claims-risk data, trains a scikit-learn model, logs parameters/metrics/model artifacts to MLflow, writes control-plane-compatible metadata, and optionally registers the candidate model with `control-plane-api`.
- `pipelines/ingest-rag`: loads synthetic healthcare-operations Markdown documents, chunks text, generates embeddings through a provider abstraction, and writes either Azure AI Search chunks or a local JSON vector index fallback.

## LLMOps Ingestion

Synthetic policy and playbook documents live under `data/synthetic_docs`. Ingestion preserves document metadata (`doc_id`, `title`, `version`, `sensitivity_class`, `source_uri`, `allowed_roles`) on every chunk. Local demos use deterministic hash embeddings and a JSON vector index under `data/local/`. Azure demos use Azure OpenAI embeddings and Azure AI Search with a vector field plus searchable text for hybrid retrieval.

Role-based retrieval is modeled as document-level filtering before prompt construction. Azure queries use `allowed_roles/any(...)` filters; the local fallback applies the same filter in process before scoring.

## Monitoring

The control plane stores prediction events for synthetic aggregate claims-risk features, scores, risk bands, latency, model version, and correlation IDs. Drift checks compare baseline training feature distributions from model lineage or a request body against recent serving distributions. Numeric utilization features are binned before PSI calculations so training and serving distributions remain stable and interpretable. The demo uses PSI-style metrics with deterministic `green`, `yellow`, and `red` statuses.

Training-serving skew is represented by feature-level distribution differences. A `red` drift snapshot recommends rollback or human review. Latency monitoring tracks average and p95 latency; business monitoring tracks prediction score and high-risk rate. Error-rate monitoring is backed by structured model error events and SLO thresholds in the summary contract. The `careai-drift-check` CLI provides a scheduled drift-check hook for cron, GitHub Actions, or Azure Container Apps Jobs.

## Cloud Target

The default Azure path is Docker images in Azure Container Registry deployed to Azure Container Apps. Supporting Azure services include Azure AI Search, Key Vault, Storage Account, PostgreSQL, Redis, Event Hubs, Log Analytics, and Application Insights. AKS and Helm remain optional extensions.
