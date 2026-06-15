from time import perf_counter

import httpx

from evaluate_rag.models import EvalItem, RagServiceResult


class RagGatewayClient:
    def __init__(self, rag_url: str, timeout_seconds: float = 15.0) -> None:
        self.rag_url = rag_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def query(self, item: EvalItem, *, top_k: int = 4) -> RagServiceResult:
        started_at = perf_counter()
        payload = {
            "user_id": "rag-evaluator",
            "role": item.role,
            "question": item.question,
            "top_k": top_k,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.rag_url}/rag/query", json=payload)
                latency_ms = max(int((perf_counter() - started_at) * 1000), 0)
                if response.status_code >= 400:
                    return RagServiceResult(
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        safety_flags=safety_flags_from_error(response),
                        error=safe_error_message(response),
                    )
                body = response.json()
        except httpx.HTTPError as exc:
            return RagServiceResult(
                status_code=503,
                latency_ms=max(int((perf_counter() - started_at) * 1000), 0),
                safety_flags=["rag_gateway_unavailable"],
                error=exc.__class__.__name__,
            )

        provider_metadata = body.get("provider_metadata", {})
        token_count = provider_metadata.get("token_count")
        if token_count is not None:
            token_count = int(token_count)

        return RagServiceResult(
            status_code=response.status_code,
            answer=str(body.get("answer", "")),
            citations=list(body.get("citations", [])),
            retrieved_chunks=list(body.get("retrieved_chunks", [])),
            groundedness_score=float(body.get("groundedness_score", 0.0)),
            safety_flags=list(body.get("safety_flags", [])),
            provider_metadata=dict(provider_metadata),
            prompt=dict(body.get("prompt", {})),
            retrieval_metadata=dict(body.get("retrieval_metadata", {})),
            correlation_id=str(body.get("correlation_id", "")),
            latency_ms=latency_ms,
            token_count=token_count,
        )


def safety_flags_from_error(response: httpx.Response) -> list[str]:
    try:
        body = response.json()
    except ValueError:
        return ["rag_gateway_error"]

    detail = body.get("detail", {})
    if isinstance(detail, dict):
        flags = detail.get("safety_flags", [])
        if isinstance(flags, list):
            return [str(flag) for flag in flags]
    return ["rag_gateway_error"]


def safe_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"

    detail = body.get("detail", "")
    if isinstance(detail, dict):
        return str(detail.get("message", f"HTTP {response.status_code}"))
    return str(detail)[:120]
