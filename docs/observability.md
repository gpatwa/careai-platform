# Observability

`careai-platform` instruments the control plane, inference service, and RAG service with OpenTelemetry. Local runs work without Azure credentials. When `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, traces, logs, and metrics are exported to Application Insights through Azure Monitor OpenTelemetry.

## Signals

Every service emits:

- Distributed traces for FastAPI requests.
- Structured JSON logs with `service_name`, `environment`, `correlation_id`, and safe domain fields such as `actor`, `model_version`, and `prompt_version`.
- Request metrics:
  - `careai.http.server.request.count`
  - `careai.http.server.latency_ms`
  - `careai.http.server.error.count`

MLOps-specific metrics:

- `careai.prediction.count`
- `careai.fallback.count` with `fallback_type=claims-risk`
- `careai.drift.status` where `green=0`, `yellow=1`, and `red=2`

LLMOps-specific metrics:

- `careai.rag.query.count`
- `careai.rag.retrieval.latency_ms`
- `careai.rag.llm.latency_ms`
- `careai.rag.safety_flag.count`
- `careai.fallback.count` with `fallback_type=rag`

## Local Usage

No Application Insights setup is required for local development:

```bash
make setup
make local-up
.venv/bin/uvicorn careai_control_plane_api.main:app --reload --port 8000
.venv/bin/uvicorn careai_inference_service.main:app --reload --port 8001
.venv/bin/uvicorn careai_rag_service.main:app --reload --port 8002
```

Logs remain structured JSON on stdout. Correlation IDs propagate through the `x-correlation-id` response header.

## Azure Usage

Set the Application Insights connection string through Container App secrets or local environment variables:

```bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="<from-application-insights>"
export ENVIRONMENT=dev
```

The Terraform stack creates Application Insights and the deployment workflow can pass `APPLICATIONINSIGHTS_CONNECTION_STRING` as a GitHub secret. Do not commit the connection string to `.env`, Terraform files, or workflow files.

## Suggested Dashboard

Application map:

- Control plane API dependencies: PostgreSQL, inference service audit calls, RAG audit calls.
- Inference service dependencies: control plane audit and monitoring ingestion.
- RAG service dependencies: Azure AI Search and Azure OpenAI when configured.

MLOps dashboard:

- Request count and p95 latency by `service_name`.
- Prediction count by `model_version` and `risk_band`.
- Fallback count by `fallback_type`.
- Drift status gauge by `model_name`.
- Error count and error rate by route.

LLMOps dashboard:

- RAG query count by `prompt_version` and provider.
- Retrieval latency p50/p95.
- LLM latency p50/p95.
- Safety flag count by `safety_flag`.
- Fallback count for local mock provider usage.

Governance dashboard:

- Audit event logs by `actor`, `action`, and `target_type`.
- Promotion and approval events correlated by `correlation_id`.
- Safety flag trends by role and prompt version.

## Suggested Alerts

- API p95 latency exceeds 750 ms for 10 minutes.
- HTTP 5xx error rate exceeds 2% for 10 minutes.
- `careai.fallback.count` increases above zero in production for the claims-risk model.
- `careai.drift.status` equals `2` for any production model.
- RAG `careai.rag.safety_flag.count` increases sharply for prompt injection or hidden prompt flags.
- RAG LLM p95 latency exceeds 5 seconds for 10 minutes.
- No prediction events received for an active production deployment for 30 minutes.

## Kusto Starting Points

Recent service logs:

```kusto
traces
| where timestamp > ago(1h)
| extend service_name = tostring(customDimensions.service_name)
| project timestamp, severityLevel, service_name, message, customDimensions
| order by timestamp desc
```

Correlate one request:

```kusto
union traces, requests, dependencies
| where tostring(customDimensions.correlation_id) == "corr-demo-001"
| order by timestamp asc
```

Fallback events:

```kusto
customMetrics
| where name == "careai.fallback.count"
| summarize fallback_count = sum(value) by tostring(customDimensions.fallback_type), bin(timestamp, 5m)
```

Drift status:

```kusto
customMetrics
| where name == "careai.drift.status"
| summarize latest_status = arg_max(timestamp, value) by tostring(customDimensions.model_name)
```
