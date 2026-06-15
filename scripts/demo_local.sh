#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://localhost:8000}"
INFERENCE_URL="${INFERENCE_URL:-http://localhost:8001}"
RAG_URL="${RAG_URL:-http://localhost:8002}"
MLFLOW_HOST_PORT="${MLFLOW_HOST_PORT:-5001}"
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://localhost:${MLFLOW_HOST_PORT}}"
WEB_CONSOLE_URL="${WEB_CONSOLE_URL:-http://localhost:3000}"

DEMO_ROWS="${DEMO_ROWS:-5000}"
DEMO_MODEL_VERSION="${DEMO_MODEL_VERSION:-0.1.0-demo}"
DEMO_OUTPUT_DIR="${DEMO_OUTPUT_DIR:-data/local/demo}"
DEMO_START_SERVICES="${DEMO_START_SERVICES:-true}"
DEMO_BUILD_IMAGES="${DEMO_BUILD_IMAGES:-true}"
DEMO_SKIP_SETUP="${DEMO_SKIP_SETUP:-false}"

CLAIMS_DATA_PATH="$DEMO_OUTPUT_DIR/synthetic_claims.csv"
TRAIN_OUTPUT_DIR="$DEMO_OUTPUT_DIR/train-claims-risk"
TRAIN_LOG_PATH="$DEMO_OUTPUT_DIR/train.log"
CONTROL_PLANE_SUMMARY_PATH="$DEMO_OUTPUT_DIR/control-plane-demo.json"
INFERENCE_RESPONSE_PATH="$DEMO_OUTPUT_DIR/inference-response.json"
RAG_QUERY_RESPONSE_PATH="$DEMO_OUTPUT_DIR/rag-query-response.json"
RAG_EVAL_REPORT_PATH="$DEMO_OUTPUT_DIR/rag-eval-report.json"
RAG_INDEX_PATH="${RAG_INDEX_PATH:-data/local/rag-index.json}"

log() {
  printf '\n==> %s\n' "$*"
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-60}"
  local delay_seconds="${4:-2}"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      printf '%s is ready at %s\n' "$label" "$url"
      return 0
    fi
    sleep "$delay_seconds"
  done

  printf 'Timed out waiting for %s at %s\n' "$label" "$url" >&2
  return 1
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    return 1
  fi
}

pretty_print_json() {
  local path="$1"
  if [[ -s "$path" ]]; then
    "$PYTHON_BIN" -m json.tool "$path" || cat "$path"
  else
    printf 'No JSON output at %s\n' "$path"
  fi
}

mkdir -p "$DEMO_OUTPUT_DIR" "$TRAIN_OUTPUT_DIR" "$(dirname "$RAG_INDEX_PATH")"

require_command curl

if [[ "$DEMO_SKIP_SETUP" != "true" ]]; then
  log "Installing local developer dependencies"
  make setup
else
  log "Skipping dependency setup because DEMO_SKIP_SETUP=true"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  printf 'Python environment not found at %s. Run make setup first.\n' "$PYTHON_BIN" >&2
  exit 1
fi

if [[ "$DEMO_START_SERVICES" == "true" ]]; then
  require_command docker
  log "Starting local services with Docker Compose"
  compose_build_arg=""
  if [[ "$DEMO_BUILD_IMAGES" == "true" ]]; then
    compose_build_arg="--build"
  fi
  docker compose up -d $compose_build_arg \
    postgres redis mlflow azurite control-plane-api inference-service rag-service web-console
else
  log "Skipping service startup because DEMO_START_SERVICES=false"
fi

log "Waiting for services"
wait_for_url "$CONTROL_PLANE_URL/healthz" "control plane"
wait_for_url "$INFERENCE_URL/healthz" "inference service"
wait_for_url "$RAG_URL/healthz" "RAG service"
wait_for_url "$MLFLOW_TRACKING_URI" "MLflow" 60 3

log "Generating deterministic synthetic claims data"
"$PYTHON_BIN" -m train_claims_risk.generate_data \
  --output "$CLAIMS_DATA_PATH" \
  --rows "$DEMO_ROWS"

log "Training and registering the claims-risk model"
MLFLOW_TRACKING_URI="$MLFLOW_TRACKING_URI" "$PYTHON_BIN" -m train_claims_risk.train \
  --data "$CLAIMS_DATA_PATH" \
  --register-control-plane-url "$CONTROL_PLANE_URL" \
  --tracking-uri "$MLFLOW_TRACKING_URI" \
  --output-dir "$TRAIN_OUTPUT_DIR" \
  --model-version "$DEMO_MODEL_VERSION" | tee "$TRAIN_LOG_PATH"

MODEL_ID="$(awk -F': ' '/Control-plane model id/ {print $2}' "$TRAIN_LOG_PATH" | tail -n 1)"
if [[ -z "$MODEL_ID" ]]; then
  MODEL_ID="$("$PYTHON_BIN" - "$CONTROL_PLANE_URL" "$DEMO_MODEL_VERSION" <<'PY'
import json
import sys
import urllib.request

base_url, version = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(f"{base_url.rstrip('/')}/models", timeout=10) as response:
    models = json.load(response)
for model in reversed(models):
    if model.get("name") == "claims-risk" and model.get("version") == version:
        print(model["id"])
        break
PY
)"
fi

if [[ -z "$MODEL_ID" ]]; then
  printf 'Model registration did not return a model id. Check %s and control-plane logs.\n' "$TRAIN_LOG_PATH" >&2
  exit 1
fi

log "Creating governance, approval, deployment, and canary demo metadata"
"$PYTHON_BIN" - "$CONTROL_PLANE_URL" "$MODEL_ID" "$TRAIN_OUTPUT_DIR/model-metadata.json" "$TRAIN_OUTPUT_DIR/metrics.json" "$DEMO_MODEL_VERSION" "$CONTROL_PLANE_SUMMARY_PATH" <<'PY'
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

base_url = sys.argv[1].rstrip("/")
model_id = sys.argv[2]
metadata_path = Path(sys.argv[3])
metrics_path = Path(sys.argv[4])
model_version = sys.argv[5]
summary_path = Path(sys.argv[6])


def request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {
        "content-type": "application/json",
        "x-actor": "demo-operator",
        "x-correlation-id": "demo-local-control-plane",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"detail": body}
        return exc.code, parsed


metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
model_card_payload = {
    "model_id": model_id,
    "intended_use": "Synthetic claims-risk prioritization demo for operations review.",
    "prohibited_use": "Do not use for clinical diagnosis, coverage denial, or real patient decisions.",
    "training_data_summary": "Deterministic synthetic healthcare-like claims features only; no real PHI or PII.",
    "metrics_summary": metrics.get("overall", {}),
    "fairness_summary": {
        "segments_reviewed": ["age_bucket", "plan_type"],
        "demo_note": "Segment metrics are synthetic and used only to demonstrate governance review.",
    },
    "explainability_summary": "Response reason codes are simplified operational signals based on safe aggregate features.",
    "owner": "platform-demo",
    "reviewer": "model-risk-reviewer",
    "approval_status": "approved",
}
status, card = request("POST", "/model-cards", model_card_payload)
if status == 409:
    status, card = request("PUT", f"/model-cards/{model_id}", {k: v for k, v in model_card_payload.items() if k != "model_id"})
if status >= 400:
    raise SystemExit(f"model card request failed: {status} {card}")

status, approval = request(
    "POST",
    "/approvals",
    {
        "target_type": "model",
        "target_id": model_id,
        "approver": "model-risk-reviewer",
        "decision": "approved",
        "notes": "Approved for synthetic interview demo only.",
    },
)
if status >= 400:
    raise SystemExit(f"approval request failed: {status} {approval}")

promotions = []
for stage in ["staging", "approved", "production"]:
    status, promoted = request(
        "POST",
        f"/models/{model_id}/promote",
        {
            "stage": stage,
            "actor": "demo-operator",
            "notes": "End-to-end local demo promotion gate.",
        },
    )
    if status >= 400:
        raise SystemExit(f"promotion to {stage} failed: {status} {promoted}")
    promotions.append({"stage": stage, "model_id": promoted.get("id")})

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata["version"] = f"{model_version}-challenger"
metadata["stage"] = "candidate"
metadata.setdefault("lineage_json", {})["demo_relationship"] = f"challenger copy of {model_id}"
status, challenger = request("POST", "/models", metadata)
if status >= 400:
    raise SystemExit(f"challenger registration failed: {status} {challenger}")
challenger_id = challenger["id"]

status, deployment = request(
    "POST",
    "/deployments",
    {
        "model_id": model_id,
        "champion_model_id": model_id,
        "environment": "demo-prod",
        "deployment_type": "blue_green",
        "endpoint_url": "http://localhost:8001/predict/claims-risk",
        "traffic_percent": 100,
        "traffic_split_json": {model_id: 100},
        "rollback_model_id": model_id,
        "health_status": "healthy",
        "status": "active",
    },
)
if status >= 400:
    raise SystemExit(f"deployment creation failed: {status} {deployment}")

status, canary = request(
    "POST",
    f"/deployments/{deployment['id']}/canary",
    {
        "challenger_model_id": challenger_id,
        "challenger_percent": 15,
        "actor": "demo-operator",
        "notes": "15 percent synthetic canary for interview walkthrough.",
    },
)
if status >= 400:
    raise SystemExit(f"canary request failed: {status} {canary}")

summary = {
    "model_id": model_id,
    "model_card_id": card.get("id"),
    "approval_id": approval.get("id"),
    "challenger_model_id": challenger_id,
    "deployment_id": deployment.get("id"),
    "canary_traffic_split_json": canary.get("traffic_split_json"),
    "promotions": promotions,
}
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
PY

log "Calling the synthetic claims-risk inference endpoint"
curl -fsS -X POST "$INFERENCE_URL/predict/claims-risk" \
  -H 'content-type: application/json' \
  -H 'x-correlation-id: demo-local-inference-001' \
  -d '{
    "request_id": "synthetic-request-001",
    "features": {
      "age_bucket": "50-64",
      "plan_type": "silver",
      "prior_claim_count": 6,
      "recent_visit_count": 3,
      "medication_count": 4,
      "chronic_condition_count": 2,
      "region_code": "R03"
    }
  }' | tee "$INFERENCE_RESPONSE_PATH" >/dev/null
pretty_print_json "$INFERENCE_RESPONSE_PATH"

log "Ingesting synthetic RAG documents into the local JSON vector index"
"$PYTHON_BIN" -m ingest_rag.ingest \
  --input-dir data/synthetic_docs \
  --output "$RAG_INDEX_PATH" \
  --force-local

log "Calling the RAG gateway with role-filtered retrieval"
curl -fsS -X POST "$RAG_URL/rag/query" \
  -H 'content-type: application/json' \
  -H 'x-correlation-id: demo-local-rag-001' \
  -d '{
    "user_id": "demo-user-clinical-ops",
    "role": "clinical_ops",
    "question": "What intake information is required for a prior authorization review?",
    "conversation_id": "demo-conversation-001",
    "top_k": 4
  }' | tee "$RAG_QUERY_RESPONSE_PATH" >/dev/null
pretty_print_json "$RAG_QUERY_RESPONSE_PATH"

log "Running the RAG evaluation report"
set +e
"$PYTHON_BIN" -m evaluate_rag.run \
  --rag-url "$RAG_URL" \
  --eval-set data/eval/rag_eval_set.jsonl \
  --output "$RAG_EVAL_REPORT_PATH" \
  --control-plane-url "$CONTROL_PLANE_URL" \
  --retrieval-hit-rate-min 0.50 \
  --citation-coverage-min 0.50 \
  --keyword-relevance-min 0.25 \
  --groundedness-min 0.25
eval_status=$?
set -e
if [[ "$eval_status" -ne 0 ]]; then
  printf 'RAG evaluation completed with a failing gate. Review %s for metrics.\n' "$RAG_EVAL_REPORT_PATH" >&2
fi

log "Demo complete"
cat <<EOF
Open these local endpoints:
- Web console: $WEB_CONSOLE_URL
- Control plane docs: $CONTROL_PLANE_URL/docs
- MLflow: $MLFLOW_TRACKING_URI

Generated demo artifacts:
- Claims data: $CLAIMS_DATA_PATH
- Training outputs: $TRAIN_OUTPUT_DIR
- Control-plane summary: $CONTROL_PLANE_SUMMARY_PATH
- Inference response: $INFERENCE_RESPONSE_PATH
- RAG response: $RAG_QUERY_RESPONSE_PATH
- RAG eval report: $RAG_EVAL_REPORT_PATH
EOF
