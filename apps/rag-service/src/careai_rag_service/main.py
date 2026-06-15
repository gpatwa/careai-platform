import logging

from careai_common.config import load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.logging import setup_json_logging
from fastapi import FastAPI, Request, Response

settings = load_settings("rag-service", 8002)
setup_json_logging(settings.service_name, settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="careai-platform RAG Service",
    version="0.1.0",
    description="RAG service skeleton for synthetic document retrieval and safety workflows.",
)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next) -> Response:
    token = set_correlation_id(request.headers.get("x-correlation-id"))
    try:
        response = await call_next(request)
        response.headers["x-correlation-id"] = ensure_correlation_id()
        return response
    finally:
        clear_correlation_id(token)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    logger.info("health check")
    return {"status": "ok", "service": settings.service_name}


@app.get("/readyz")
def readyz() -> dict[str, object]:
    return {
        "status": "ready",
        "service": settings.service_name,
        "dependencies": {
            "azure_ai_search": "local-placeholder",
            "storage": "configured",
        },
    }
