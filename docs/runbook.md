# Runbook

## Local Setup

```bash
make setup
cp .env.example .env
make local-up
```

Run the services locally:

```bash
.venv/bin/uvicorn careai_control_plane_api.main:app --reload --port 8000
.venv/bin/uvicorn careai_inference_service.main:app --reload --port 8001
.venv/bin/uvicorn careai_rag_service.main:app --reload --port 8002
npm --prefix apps/web-console run dev
```

## Health Checks

```bash
curl http://localhost:8000/healthz
curl http://localhost:8001/healthz
curl http://localhost:8002/healthz
curl http://localhost:8000/readyz
curl http://localhost:8001/readyz
curl http://localhost:8002/readyz
```

## Shutdown

```bash
make local-down
```

## Safety

Use synthetic data only. Do not add secrets to environment files, logs, fixtures, tests, screenshots, or documentation.

