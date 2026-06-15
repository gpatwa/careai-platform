#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-${AZURE_CONTROL_PLANE_URL:-}}"
INFERENCE_URL="${INFERENCE_URL:-${AZURE_INFERENCE_URL:-}}"
RAG_URL="${RAG_URL:-${AZURE_RAG_URL:-}}"
WEB_CONSOLE_URL="${WEB_CONSOLE_URL:-${AZURE_WEB_CONSOLE_URL:-}}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-20}"

strip_trailing_slash() {
  printf '%s' "${1%/}"
}

CONTROL_PLANE_URL="$(strip_trailing_slash "$CONTROL_PLANE_URL")"
INFERENCE_URL="$(strip_trailing_slash "$INFERENCE_URL")"
RAG_URL="$(strip_trailing_slash "$RAG_URL")"
WEB_CONSOLE_URL="$(strip_trailing_slash "$WEB_CONSOLE_URL")"

usage() {
  cat <<'EOF'
Set deployed Container Apps URLs, then run:

  CONTROL_PLANE_URL=https://<control-plane> \
  INFERENCE_URL=https://<inference> \
  RAG_URL=https://<rag> \
  WEB_CONSOLE_URL=https://<web-console> \
  scripts/demo_azure_smoke_test.sh

AZURE_CONTROL_PLANE_URL, AZURE_INFERENCE_URL, AZURE_RAG_URL, and
AZURE_WEB_CONSOLE_URL are also accepted.
EOF
}

require_url() {
  local value="$1"
  local label="$2"
  if [[ -z "$value" ]]; then
    printf 'Missing %s URL.\n\n' "$label" >&2
    usage >&2
    exit 1
  fi
}

check_get() {
  local url="$1"
  local label="$2"
  printf 'Checking %s: %s\n' "$label" "$url"
  curl -fsS --max-time "$REQUEST_TIMEOUT_SECONDS" "$url" >/dev/null
}

check_post() {
  local url="$1"
  local label="$2"
  local payload="$3"
  printf 'Checking %s: %s\n' "$label" "$url"
  curl -fsS --max-time "$REQUEST_TIMEOUT_SECONDS" \
    -X POST "$url" \
    -H 'content-type: application/json' \
    -H "x-correlation-id: azure-smoke-${label// /-}" \
    -d "$payload" >/dev/null
}

require_url "$CONTROL_PLANE_URL" "control plane"
require_url "$INFERENCE_URL" "inference service"
require_url "$RAG_URL" "RAG service"

check_get "$CONTROL_PLANE_URL/healthz" "control-plane health"
check_get "$CONTROL_PLANE_URL/readyz" "control-plane readiness"
check_get "$INFERENCE_URL/healthz" "inference health"
check_get "$INFERENCE_URL/readyz" "inference readiness"
check_get "$RAG_URL/healthz" "RAG health"
check_get "$RAG_URL/readyz" "RAG readiness"

check_post "$INFERENCE_URL/predict/claims-risk" "inference request" '{
  "request_id": "synthetic-azure-smoke-001",
  "features": {
    "age_bucket": "35-49",
    "plan_type": "gold",
    "prior_claim_count": 2,
    "recent_visit_count": 1,
    "medication_count": 2,
    "chronic_condition_count": 1,
    "region_code": "R02"
  }
}'

check_post "$RAG_URL/rag/query" "RAG request" '{
  "user_id": "azure-smoke-user",
  "role": "clinical_ops",
  "question": "What governance information should be recorded for prior authorization decisions?",
  "conversation_id": "azure-smoke-conversation",
  "top_k": 3
}'

if [[ -n "$WEB_CONSOLE_URL" ]]; then
  check_get "$WEB_CONSOLE_URL" "web console"
else
  printf 'WEB_CONSOLE_URL not set; skipping web console root check.\n'
fi

printf 'Azure smoke tests passed.\n'
