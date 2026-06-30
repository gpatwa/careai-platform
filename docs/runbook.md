# Runbook

## Local Setup

```bash
make setup
cp .env.example .env
make local-up
make db-upgrade
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
curl http://localhost:8000/monitoring/models/claims-risk/error-events
curl http://localhost:8000/monitoring/models/claims-risk/summary
```

Create a safe synthetic error event for SLO testing:

```bash
curl -X POST http://localhost:8000/monitoring/error-events \
  -H 'content-type: application/json' \
  -d '{
    "model_name": "claims-risk",
    "model_version": "0.1.0",
    "error_type": "model_prediction_failed",
    "error_message": "Model prediction failed; deterministic fallback score returned.",
    "status_code": 200,
    "latency_ms": 42,
    "correlation_id": "demo-error-001"
  }'
```

Run a drift check after predictions have been ingested:

```bash
curl -X POST http://localhost:8000/monitoring/models/claims-risk/drift-check \
  -H 'content-type: application/json' \
  -d '{"minimum_events": 1}'
```

Run the same check as a one-shot scheduled job:

```bash
careai-drift-check \
  --control-plane-url http://localhost:8000 \
  --model-name claims-risk \
  --minimum-events 1
```

Drift compares baseline training distributions to recent serving distributions, with numeric utilization features binned before PSI calculations. Investigate `yellow`; treat `red` as a rollback or human-review trigger. Also review p95 latency, error rate, and high-risk-rate changes for signs of training-serving skew, data quality issues, or operational degradation. The summary endpoint marks SLO status as breached when p95 latency exceeds 750 ms or error rate exceeds 2%.

## Deployment Safety

Start a canary for an existing deployment:

```bash
curl -X POST http://localhost:8000/deployments/<deployment-id>/canary \
  -H "content-type: application/json" \
  -d '{
    "challenger_model_id": "<challenger-model-id>",
    "challenger_percent": 10,
    "actor": "release-manager"
  }' | jq
```

Increase or decrease traffic:

```bash
curl -X POST http://localhost:8000/deployments/<deployment-id>/set-traffic \
  -H "content-type: application/json" \
  -d '{
    "traffic_split_json": {
      "<champion-model-id>": 75,
      "<challenger-model-id>": 25
    },
    "actor": "release-manager"
  }' | jq
```

Rollback sends all traffic to `rollback_model_id` and clears challenger traffic:

```bash
curl -X POST http://localhost:8000/deployments/<deployment-id>/rollback \
  -H "content-type: application/json" \
  -d '{"actor":"release-manager","notes":"Rollback after SLO or drift trigger."}' | jq
```

For local inference traffic simulation, configure:

```bash
export CLAIMS_RISK_TRAFFIC_SPLIT_JSON='{"champion":90,"challenger":10}'
export CLAIMS_RISK_CHAMPION_MODEL_VERSION=0.1.0
export CLAIMS_RISK_CHALLENGER_MODEL_VERSION=0.2.0
```

Prediction responses include `selected_model_role` and selected `model_version`. The control plane marks deployments as `rollback_recommended` when champion error rate, latency, or drift crosses the demo thresholds.

## RAG Ingestion

Run local synthetic document ingestion:

```bash
python -m ingest_rag.ingest \
  --input-dir data/synthetic_docs \
  --output data/local/rag-index.json \
  --force-local
```

To use Azure AI Search, set `AZURE_AI_SEARCH_ENDPOINT`, `AZURE_AI_SEARCH_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, then omit `--force-local`. The pipeline creates or updates the `careai-rag-chunks` index, uploads chunks, and keeps `allowed_roles` metadata available for retrieval filters.

## RAG Gateway

Run a local query after installing dependencies:

```bash
uvicorn careai_rag_service.main:app --host 0.0.0.0 --port 8002
curl -s http://localhost:8002/rag/query \
  -H "content-type: application/json" \
  -d '{"user_id":"synthetic-user-001","role":"clinical_ops","question":"What should reviewers check before escalating prior authorization?","top_k":3}' | jq
```

If `data/local/rag-index.json` is missing, the service builds it from `data/synthetic_docs` with deterministic local embeddings. To use Azure-backed retrieval and generation, configure Azure AI Search, Azure OpenAI embeddings, and `AZURE_OPENAI_CHAT_DEPLOYMENT`.

Check `safety_flags`, `human_review_required`, `groundedness_score`, and `citations` on every response. Prompt-injection or secret requests should return HTTP 400. Diagnosis or treatment questions should set the human-review flag. Control-plane audit events should contain prompt/template metadata and source ids, not raw question or answer text.

For loop-engineering behavior, also inspect `agent_loop.attempt_count`, `agent_loop.verification_passed`, and per-attempt `verification_flags`. A retry with verifier feedback is expected for borderline answers and is a good interview talking point.

## RAG Evaluation

Run the GenAI evaluation gate against the local RAG gateway:

```bash
python -m evaluate_rag.run \
  --rag-url http://localhost:8002 \
  --eval-set data/eval/rag_eval_set.jsonl
```

The report is written to `data/local/rag-eval-report.json` by default. Review `retrieval_hit_rate`, `citation_coverage`, `keyword_relevance`, `groundedness`, `safety_flag_rate`, `disallowed_claim_rate`, and latency metrics before promoting prompt or retrieval changes. If the control plane URL is configured, the same aggregate metrics are posted to `/evaluations`.

To inspect the production-style hill-climbing view from live traces:

```bash
curl http://localhost:8000/monitoring/rag/improvement-summary
```

To preview or execute the autonomous planner for a workflow:

```bash
curl http://localhost:8000/workflow-runs/<workflow-run-id>/planner-decision
curl -X POST http://localhost:8000/workflow-runs/<workflow-run-id>/execute \
  -H 'content-type: application/json' \
  -d '{"max_steps": 5, "run_until_blocked": true}'
```

After execution, inspect the persisted bounded-loop state:

```bash
curl -s http://localhost:8000/workflow-runs/<workflow-run-id> | \
  jq '{status, current_step, review_required, planner_state_json}'
```

`planner_state_json.loop_history` keeps the latest 40 safe plan, verifier, retry, and handoff events. A missing policy-evidence check may retry once; any other failed verification creates a review queue item and leaves the workflow in `waiting_for_review`. The history intentionally stores metadata and evidence keys rather than raw question, claim, or member-like values.

To run due workflows as a background-style local scheduler:

```bash
.venv/bin/careai-autonomous-planner --limit 10 --max-steps-per-workflow 5
```

## Governance Gates

Create or review model cards and prompt cards before production use:

```bash
curl http://localhost:8000/model-cards | jq
curl http://localhost:8000/prompt-cards | jq
```

Production model promotion requires both an approved model card and an approved `Approval` record for the model. A blocked promotion returns HTTP 409 with the missing controls.

```bash
curl -X POST http://localhost:8000/models/<model-id>/promote \
  -H "content-type: application/json" \
  -d '{"stage":"production","actor":"model-risk-reviewer"}' | jq
```

Production RAG prompt selection uses only prompts returned by:

```bash
curl "http://localhost:8000/prompts?production_ready_only=true" | jq
```

Use `docs/templates/model_card_template.md` and `docs/templates/prompt_card_template.md` as review checklists. Keep all examples synthetic and avoid raw PHI/PII-like values in notes, cards, audit metadata, or screenshots.

## Shutdown

```bash
make local-down
```

## Safety

Use synthetic data only. Do not add secrets to environment files, logs, fixtures, tests, screenshots, or documentation.
