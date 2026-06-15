# Interview Storyboard

This is a 10-minute end-to-end interview walkthrough for `careai-platform`. It uses deterministic synthetic healthcare-like data only. Do not describe it as real clinical, claims, member, or patient data.

## Quick Start

From a fresh clone:

```bash
scripts/demo_local.sh
```

The script installs local dependencies, starts Docker Compose services, trains and registers a synthetic model, creates governance metadata, creates a canary deployment, runs inference, ingests synthetic documents, runs a RAG query, and writes a RAG evaluation report. Key outputs land in `data/local/demo/`.

Open these after the script completes:

- Web console: `http://localhost:3000`
- Control plane API docs: `http://localhost:8000/docs`
- MLflow: `http://localhost:5001`

## 10-Minute Walkthrough

### 0:00-1:00 Problem Statement

Start with the enterprise problem: teams need one governed platform path for predictive ML and GenAI workloads. In healthcare-style operations, the platform must prove lineage, approvals, auditability, monitoring, rollback, and safety without exposing PHI.

Say explicitly:

- All data and documents are synthetic.
- The demo shows platform controls, not production clinical decisioning.
- The same local-first contracts map to Azure Container Apps, Azure AI Search, Event Hubs, Key Vault, Storage, PostgreSQL, Redis, and Application Insights.

### 1:00-2:00 Architecture

Show the Overview page and the architecture diagram in `README.md`.

Walk the boundaries:

- Control plane tracks datasets, models, deployments, prompt templates, evaluations, approvals, model cards, prompt cards, audit events, prediction events, drift snapshots, and rollback health.
- Inference service serves the synthetic claims-risk API with validation, feature checks, audit events, monitoring events, fallback scoring, and champion/challenger routing metadata.
- RAG service retrieves from Azure AI Search when configured or a local JSON vector index otherwise, then applies prompt registry, safety checks, citations, and audit logging.
- MLflow stores experiment runs and model artifacts.
- PostgreSQL is the metadata/audit store; Redis represents online cache infrastructure; Azurite represents local storage.

### 2:00-3:15 Train Synthetic Model

In the terminal, point to the script steps:

```bash
python -m train_claims_risk.generate_data \
  --output data/local/demo/synthetic_claims.csv \
  --rows 5000

python -m train_claims_risk.train \
  --data data/local/demo/synthetic_claims.csv \
  --register-control-plane-url http://localhost:8000 \
  --tracking-uri http://localhost:5001
```

Explain that the data generator produces only aggregate synthetic fields such as age bucket, plan type, prior claim count, visit count, medication count, chronic condition count, synthetic region code, and a synthetic high-risk label.

Show MLflow:

- Experiment parameters: seed, row count, test split, model type.
- Metrics: AUC, precision, recall, F1, calibration summary, segment metrics.
- Artifacts: model, feature list, metrics, metadata.
- Lineage: training data hash, code version placeholder, baseline feature distributions.

### 3:15-4:15 Register, Evaluate, and Govern

Show Models and Governance in the web console.

The training pipeline registers a candidate `claims-risk` artifact in the control plane. The demo script then creates:

- Approved model card.
- Human approval decision.
- Promotion path through `staging`, `approved`, and `production`.
- Audit events for registration, model card, approval, and promotion.

Call out the production gate: the control plane blocks `production` promotion unless the model has an approved model card and an approved human decision.

### 4:15-5:15 Deploy, Canary, and Rollback Safety

Open Deployments.

Show:

- Champion model id.
- Challenger model id.
- Traffic split, for example 85 percent champion and 15 percent challenger.
- Rollback model id.
- Health status.

Explain that canary and traffic APIs model production rollout safety:

```bash
POST /deployments/{id}/canary
POST /deployments/{id}/set-traffic
POST /deployments/{id}/rollback
```

The automatic rollback placeholder marks `health_status=rollback_recommended` when error rate, latency, or drift breaches a configured threshold. For the local demo, inference simulates champion/challenger selection metadata; a production extension would load separate artifacts per route.

### 5:15-6:15 Call Inference Endpoint

Show the sample response saved by the script:

```bash
cat data/local/demo/inference-response.json
```

Highlight:

- Validated synthetic features.
- Prediction score and risk band.
- Model name/version.
- Selected model role.
- Feature version.
- Reason codes.
- Correlation ID.
- Fallback warning if a real artifact is unavailable.

Reinforce that logs and audit events avoid raw PHI/PII-like values.

### 6:15-7:00 Monitoring and Drift

Open Monitoring and Audit.

Explain:

- Inference emits prediction events to the control plane.
- Monitoring summarizes prediction counts, latency, risk-band mix, missingness, and SLO status.
- Drift compares baseline training distributions with recent inference events using deterministic PSI-style metrics.
- Rollback triggers are tied to error rate, latency, and red drift status.

Use this language: monitoring is not just charts; it is part of the release safety loop.

### 7:00-8:15 RAG Query With Citations and Safety

Open RAG.

Ask:

```text
What intake information is required for a prior authorization review?
```

Use role `clinical_ops`.

Highlight:

- Role-based retrieval filtering through document metadata.
- Local deterministic embeddings for tests and demos.
- Azure AI Search-compatible schema when cloud env vars are present.
- Citations returned with source ids, titles, chunks, and source URIs.
- Safety checks reject prompt extraction/secrets requests and flag medical diagnosis requests for human review.
- Audit logs capture prompt version, source ids, model/provider metadata, safety flags, and correlation id without storing raw sensitive values.

### 8:15-9:00 RAG Evaluation Gate

Show:

```bash
cat data/local/demo/rag-eval-report.json
```

Explain the LLMOps metrics:

- Retrieval hit rate.
- Citation coverage.
- Keyword relevance.
- Groundedness heuristic.
- Safety flag rate.
- Latency.
- Pass/fail thresholds.

Tie this to promotion gates: a real platform would require passing evaluation reports and approved prompt cards before production prompt or retrieval changes.

### 9:00-10:00 Azure Deployment

Show `infra/terraform` and `.github/workflows/deploy-azure-container-apps.yml`.

Explain the Azure path:

- Terraform provisions resource group, Azure Container Registry, Container Apps environment, Log Analytics, Application Insights, Key Vault, Storage, Azure AI Search, Event Hubs, and optional PostgreSQL/Redis/Azure ML.
- GitHub Actions uses OIDC or documented secrets to build images, push to ACR, deploy Container Apps, and run smoke tests.
- OpenTelemetry exports traces, logs, and metrics to Application Insights when configured.
- Event Hubs provides the Kafka-style event backbone for prediction, audit, feedback, drift, and retraining-trigger events.

For deployed smoke tests:

```bash
CONTROL_PLANE_URL=https://<control-plane-app> \
INFERENCE_URL=https://<inference-app> \
RAG_URL=https://<rag-app> \
WEB_CONSOLE_URL=https://<web-console-app> \
scripts/demo_azure_smoke_test.sh
```

## Demo Command Reference

Run the full local demo:

```bash
scripts/demo_local.sh
```

Run without rebuilding Docker images:

```bash
DEMO_BUILD_IMAGES=false scripts/demo_local.sh
```

Run against services you already started:

```bash
DEMO_START_SERVICES=false scripts/demo_local.sh
```

Use smaller data for a faster rehearsal:

```bash
DEMO_ROWS=1000 scripts/demo_local.sh
```

Stop local services:

```bash
make local-down
```

## Troubleshooting

- Docker ports are already in use: stop local processes on ports `3000`, `5001`, `8000`, `8001`, `8002`, `5432`, or `6379`, or run with `DEMO_START_SERVICES=false` if services are already healthy.
- Services are slow to start: rerun `scripts/demo_local.sh`. The script is resumable and overwrites generated artifacts under `data/local/demo/`.
- `make setup` fails because Node.js is missing: install Node.js LTS or rerun with `DEMO_SKIP_SETUP=true` after Python dependencies are installed.
- MLflow is unavailable: check `docker compose logs mlflow postgres`. Training can use a local file store by setting `MLFLOW_TRACKING_URI=file:$(pwd)/mlruns`, but the interview script defaults to the MLflow container.
- Model registration fails: open `http://localhost:8000/readyz` and check `docker compose logs control-plane-api`.
- Inference returns fallback metadata: this is acceptable for the platform demo when no model artifact URI is mounted into the service. The response still demonstrates validation, scoring contract, audit logging, monitoring, and traffic-selection metadata.
- RAG returns no context: confirm synthetic docs exist under `data/synthetic_docs/`, then rerun `python -m ingest_rag.ingest --input-dir data/synthetic_docs --output data/local/rag-index.json --force-local`.
- RAG evaluation fails thresholds: inspect `data/local/demo/rag-eval-report.json`. A failed gate is useful to explain LLMOps promotion controls.
- Azure smoke test fails: verify Container App URLs, ingress settings, app environment variables, and Application Insights/Key Vault references. Start with `/healthz`, then `/readyz`, then POST smoke requests.
