# Data Flow

This document summarizes the main runtime and batch flows. All examples use synthetic data and synthetic policy documents only.

## MLOps Training And Registration

```mermaid
sequenceDiagram
    participant Dev as Developer or CI
    participant Gen as Synthetic data generator
    participant Train as Claims-risk trainer
    participant MLflow as MLflow tracking
    participant CP as Control plane
    participant Store as Artifact storage

    Dev->>Gen: Generate synthetic_claims.csv
    Gen-->>Dev: CSV with synthetic features and label
    Dev->>Train: Train model from CSV
    Train->>Train: Split train/test and calculate metrics
    Train->>MLflow: Log params, metrics, MLflow model, feature list, data hash
    Train->>Store: Write model.joblib, model-metadata.json, metrics, feature list
    Train->>CP: Register candidate ModelArtifact when available
    CP-->>Train: Model id and audit event
```

The training command does not automatically publish the serialized model bundle to Azure Blob Storage. For Azure inference, upload a versioned `model.joblib` plus matching `model-metadata.json` to the private artifacts container, then configure `CLAIMS_RISK_MODEL_URI` and `CLAIMS_RISK_MODEL_METADATA_PATH`. See [artifact deployment wiring](../artifact_deployment_wiring.md).

## Real-Time Inference And Monitoring

```mermaid
sequenceDiagram
    participant Client
    participant Infer as inference-service
    participant Model as Loaded model or fallback rules
    participant CP as control-plane-api
    participant Events as Local log or Event Hubs

    Client->>Infer: POST /predict/claims-risk
    Infer->>Infer: Validate schema, freshness, missingness
    Infer->>Model: Score request or use deterministic fallback
    Model-->>Infer: Score, risk band, reason codes
    Infer->>CP: PredictionEvent and AuditEvent, if configured
    Infer->>Events: prediction.created
    Infer-->>Client: Score, band, model metadata, correlation id
```

Monitoring reads persisted prediction events from the control plane. Drift checks compare baseline distributions against recent prediction features and return `green`, `yellow`, or `red` status with deterministic PSI-style metrics.

## LLMOps Ingestion, Retrieval, And Evaluation

```mermaid
sequenceDiagram
    participant Ingest as ingest-rag pipeline
    participant Docs as Synthetic docs
    participant Embed as Embedding provider
    participant Index as Local JSON index or Azure AI Search
    participant RAG as rag-service
    participant CP as control-plane-api
    participant Eval as evaluate-rag pipeline

    Ingest->>Docs: Load markdown policies
    Ingest->>Ingest: Chunk and attach metadata
    Ingest->>Embed: Generate embeddings
    Ingest->>Index: Upsert chunks
    RAG->>CP: Fetch approved prompt when available
    RAG->>Index: Retrieve chunks filtered by allowed_roles
    RAG->>RAG: Apply safety checks and provider abstraction
    RAG->>CP: Audit prompt version, source ids, safety flags
    Eval->>RAG: Run 20-question synthetic eval set
    Eval->>CP: Register EvaluationRun when available
```

Terraform provisions Azure AI Search but does not run the ingestion pipeline. Run the ingestion job with the Search and Azure OpenAI embedding configuration before enabling Azure-backed retrieval.

## Bounded Workflow Orchestration

```mermaid
sequenceDiagram
    participant Case as Payment Integrity Case
    participant CP as Control Plane / WorkflowRun
    participant Score as Inference Service
    participant RAG as RAG Service
    participant Review as Human Review Queue

    Case->>CP: Create tenant-scoped WorkflowRun
    CP->>CP: Plan one allowlisted tool and persist plan event
    CP->>Score: Claims-risk scoring
    Score-->>CP: Score and risk band
    CP->>CP: Verify score/band evidence
    CP->>RAG: Policy retrieval when needed
    RAG-->>CP: Policy source ids and summary
    CP->>CP: Verify policy evidence
    alt evidence incomplete, first occurrence
        CP->>CP: Persist retry event and retry retrieval once
    else verification failure or review required
        CP->>Review: Create review item; mark waiting_for_review
    else verified
        CP->>CP: Resolve case and persist final decision
    end
```

The planner is deterministic rather than an LLM or LangGraph graph. It persists the latest 40 plan, verification, retry, and handoff events in `WorkflowRun.planner_state_json.loop_history`, avoiding raw request values in the history.

## Data Classification

| Data | Classification | Storage | Notes |
| --- | --- | --- | --- |
| Synthetic claims CSV | Synthetic, no PHI | Local `data/` or Azure Storage datasets container | Used for model training and testing. |
| Synthetic model artifacts | Synthetic demo model | MLflow artifact store or Azure Storage artifacts container | May be promoted through control-plane metadata. |
| Synthetic policy documents | Synthetic operational content | Repository `data/synthetic_docs/` | Indexed locally or in Azure AI Search. |
| Prediction events | No raw PHI/PII-like values | PostgreSQL and optional Event Hubs | Contains synthetic feature values, score, band, latency, and correlation id. |
| Audit events | Metadata only | PostgreSQL and optional Event Hubs | Avoids raw sensitive payloads; stores target ids, actor, action, and metadata. |

## Correlation And Audit

Every service accepts or creates an `x-correlation-id`. That id is included in responses, structured logs, audit events, prediction events, and published event envelopes so a demo incident can be traced from UI/API request to model/RAG behavior and governance records.
