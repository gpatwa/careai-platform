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

- `apps/control-plane-api`: orchestration, metadata, registry, promotion, monitoring, audit, and governance workflows. It tracks dataset assets, model artifacts, deployments, prompt templates, evaluation runs, approvals, audit events, prediction events, and drift snapshots through a FastAPI/SQLAlchemy service with demo `create_all` schema creation.
- `apps/inference-service`: synthetic claims-risk inference with configurable local or MLflow model loading, Pydantic feature validation, feature freshness checks, safe prediction audit and monitoring events, and deterministic fallback scoring when no model is available.
- `apps/rag-service`: document ingestion, retrieval, prompt registry, safety checks, and RAG-facing endpoints.
- `libs/common-python`: shared settings, JSON logging, correlation IDs, audit schemas, and common errors.

## MLOps Pipeline

- `pipelines/train-claims-risk`: generates deterministic synthetic claims-risk data, trains a scikit-learn model, logs parameters/metrics/model artifacts to MLflow, writes control-plane-compatible metadata, and optionally registers the candidate model with `control-plane-api`.

## Monitoring

The control plane stores prediction events for synthetic aggregate claims-risk features, scores, risk bands, latency, model version, and correlation IDs. Drift checks compare baseline training feature distributions from model lineage or a request body against recent serving distributions. The demo uses PSI-style metrics with deterministic `green`, `yellow`, and `red` statuses.

Training-serving skew is represented by feature-level distribution differences. A `red` drift snapshot recommends rollback or human review. Latency monitoring tracks average and p95 latency; business monitoring tracks prediction score and high-risk rate. Error-rate wiring is represented in the dashboard contract and can later be backed by structured error events or Azure Application Insights.

## Cloud Target

The default Azure path is Docker images in Azure Container Registry deployed to Azure Container Apps. Supporting Azure services include Azure AI Search, Key Vault, Storage Account, PostgreSQL, Redis, Event Hubs, Log Analytics, and Application Insights. AKS and Helm remain optional extensions.
