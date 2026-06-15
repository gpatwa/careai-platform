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

## Monitoring Checks

Prediction events are emitted by `inference-service` when `CONTROL_PLANE_API_URL` and `INFERENCE_MONITORING_ENABLED=true` are configured.

```bash
curl http://localhost:8000/monitoring/models/claims-risk/events
curl http://localhost:8000/monitoring/models/claims-risk/summary
```

Run a drift check after predictions have been ingested:

```bash
curl -X POST http://localhost:8000/monitoring/models/claims-risk/drift-check \
  -H 'content-type: application/json' \
  -d '{"minimum_events": 1}'
```

Drift compares baseline training distributions to recent serving distributions. Investigate `yellow`; treat `red` as a rollback or human-review trigger. Also review p95 latency, error rate, and high-risk-rate changes for signs of training-serving skew, data quality issues, or operational degradation.

## Shutdown

```bash
make local-down
```

## Safety

Use synthetic data only. Do not add secrets to environment files, logs, fixtures, tests, screenshots, or documentation.
