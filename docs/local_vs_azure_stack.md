# Local vs Azure Stack

This page is a compact interview aid for `careai-platform`.

## Local Stack

| Layer | Stack |
| --- | --- |
| Language | Python 3.11+ |
| Backend services | FastAPI, Pydantic, SQLAlchemy/SQLModel |
| ML workflow | scikit-learn, MLflow |
| Data stores | PostgreSQL, Redis |
| File/object storage | Azurite or local JSON/file fallbacks |
| RAG ingestion | Local deterministic embeddings, JSON vector index fallback |
| Frontend | TypeScript, React/Vite |
| Runtime | Docker Compose |
| Quality gates | pytest, ruff, structured JSON logging |

## Azure Stack

| Layer | Stack |
| --- | --- |
| Compute | Azure Container Apps |
| Container registry | Azure Container Registry |
| Infrastructure as code | Terraform |
| Metadata store | Azure Database for PostgreSQL Flexible Server, optional |
| Cache | Azure Cache for Redis, optional |
| Storage | Azure Storage Account |
| Search | Azure AI Search |
| Event backbone | Azure Event Hubs |
| Secrets | Azure Key Vault |
| Observability | Log Analytics, Application Insights, OpenTelemetry |
| Optional MLOps platform | Azure Machine Learning |
| AI providers | Azure OpenAI for chat and embeddings when configured |
| Delivery | GitHub Actions with OIDC or documented secret fallback |

## One-Slide Architecture

```mermaid
flowchart LR
    subgraph Local["Local-first developer loop"]
        UI["Web Console"]
        CP["Control Plane API"]
        INF["Inference Service"]
        RAG["RAG Service"]
        ML["MLflow"]
        PG["PostgreSQL"]
        REDIS["Redis"]
        FS["Local files / Azurite / JSON index"]
    end

    subgraph Azure["Azure deployment path"]
        ACR["Azure Container Registry"]
        ACA["Azure Container Apps"]
        KV["Key Vault"]
        AI["Application Insights"]
        LA["Log Analytics"]
        SEARCH["Azure AI Search"]
        EH["Event Hubs"]
        ST["Storage Account"]
        ADB["PostgreSQL Flexible Server"]
        ACREDIS["Azure Cache for Redis"]
    end

    UI --> CP
    UI --> RAG
    CP --> PG
    CP --> REDIS
    INF --> CP
    RAG --> CP
    ML --> PG
    RAG --> FS
    INF --> FS

    ACR --> ACA
    ACA --> KV
    ACA --> AI
    AI --> LA
    ACA --> SEARCH
    ACA --> EH
    ACA --> ST
    ACA --> ADB
    ACA --> ACREDIS
```

## 60-Second Talk Track

`careai-platform` is a local-first enterprise demo that shows how a healthcare-style platform can support both MLOps and LLMOps without using real PHI.

Locally, we run FastAPI services, PostgreSQL, Redis, MLflow, and a React/Vite console through Docker Compose. The training pipeline generates synthetic claims-risk data, trains a scikit-learn model, logs it to MLflow, and registers metadata in the control plane. The RAG pipeline ingests synthetic policy docs, chunks them, embeds them, and serves them through a retrieval layer with safety checks and citations.

On Azure, the same services are containerized and deployed to Azure Container Apps from Azure Container Registry. Terraform provisions the platform dependencies: Key Vault, Storage, Azure AI Search, Event Hubs, Log Analytics, Application Insights, and optional PostgreSQL or Redis. OpenTelemetry and structured logs feed observability, while Event Hubs provides the streaming backbone for prediction, audit, drift, and feedback events.

The interview message is simple: the local stack proves the workflow quickly, and the Azure stack shows how the same design becomes a governed enterprise platform.

