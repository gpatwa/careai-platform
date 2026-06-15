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

- `apps/control-plane-api`: orchestration, metadata, registry, promotion, audit, and governance workflows. It tracks dataset assets, model artifacts, deployments, prompt templates, evaluation runs, approvals, and audit events through a FastAPI/SQLAlchemy service with demo `create_all` schema creation.
- `apps/inference-service`: synthetic claims-risk inference with configurable local or MLflow model loading, Pydantic feature validation, feature freshness checks, safe prediction audit events, and deterministic fallback scoring when no model is available.
- `apps/rag-service`: document ingestion, retrieval, prompt registry, safety checks, and RAG-facing endpoints.
- `libs/common-python`: shared settings, JSON logging, correlation IDs, audit schemas, and common errors.

## MLOps Pipeline

- `pipelines/train-claims-risk`: generates deterministic synthetic claims-risk data, trains a scikit-learn model, logs parameters/metrics/model artifacts to MLflow, writes control-plane-compatible metadata, and optionally registers the candidate model with `control-plane-api`.

## Cloud Target

The default Azure path is Docker images in Azure Container Registry deployed to Azure Container Apps. Supporting Azure services include Azure AI Search, Key Vault, Storage Account, PostgreSQL, Redis, Event Hubs, Log Analytics, and Application Insights. AKS and Helm remain optional extensions.
