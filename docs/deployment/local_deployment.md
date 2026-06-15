# Local Deployment

This runbook starts the local-first demo stack with Docker Compose dependencies, FastAPI services, pipelines, and the web console.

## Prerequisites

- Python 3.11+
- Node.js LTS
- Docker Desktop or compatible runtime
- Make

## Setup

```bash
make setup
cp .env.example .env
```

Start local dependencies and containerized app services:

```bash
make local-up
```

`docker-compose.yml` health-gates PostgreSQL, Redis, MLflow, and the app services so startup order is deterministic. MLflow uses the v3 container image to match the training pipeline’s current logging API, and it keeps its tracking metadata in a local SQLite file under the MLflow volume so it does not collide with the control-plane Postgres migrations.

Local app-service Docker builds default to `linux/amd64` for Azure Container Apps parity, which is especially important on Apple Silicon macOS. To build native local images only for local experimentation, override the platform:

```bash
DOCKER_PLATFORM=linux/arm64 make docker-build
```

Apply database migrations if you run services outside Compose:

```bash
make db-upgrade
```

## Local URLs

| Service | URL |
| --- | --- |
| Web console | `http://localhost:3000` |
| Control plane | `http://localhost:8000` |
| Control plane docs | `http://localhost:8000/docs` |
| Inference | `http://localhost:8001` |
| RAG | `http://localhost:8002` |
| MLflow | `http://localhost:5001` |

Health checks:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8001/healthz
curl http://localhost:8002/healthz
```

## End-To-End Demo

```bash
scripts/demo_local.sh
```

The script is the fastest walkthrough path. It starts services, generates synthetic claims data, trains a model, registers metadata, creates governance artifacts, creates deployment metadata, calls inference, ingests synthetic RAG docs, runs a RAG query, and writes a local evaluation report.

## Manual Pipeline Commands

Generate data and train:

```bash
python -m train_claims_risk.generate_data --output data/synthetic_claims.csv --rows 5000
python -m train_claims_risk.train \
  --data data/synthetic_claims.csv \
  --register-control-plane-url http://localhost:8000
```

Ingest synthetic RAG documents:

```bash
python -m ingest_rag.run \
  --docs-dir data/synthetic_docs \
  --output data/local/rag-index.json
```

Run RAG evaluation:

```bash
python -m evaluate_rag.run \
  --rag-url http://localhost:8002 \
  --eval-set data/eval/rag_eval_set.jsonl
```

## Configuration Notes

- The inference service uses a deterministic fallback scorer unless `CLAIMS_RISK_MODEL_URI`, `CLAIMS_RISK_MODEL_PATH`, or champion/challenger model configuration is provided.
- The RAG service uses local deterministic embeddings and a mock chat provider unless Azure AI Search and Azure OpenAI variables are configured.
- Compose passes Azure-related variables through from `.env`, so local testing can use Azure AI Search, Azure OpenAI, or Event Hubs without changing code.
- Do not put real secrets in `.env.example` or committed files. Use local `.env` only.

## Shutdown

```bash
make local-down
```

To remove local data volumes as well:

```bash
docker compose down -v
```
