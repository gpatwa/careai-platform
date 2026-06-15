import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from careai_common.config import load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.events import event_publisher_from_env
from careai_common.logging import setup_json_logging
from careai_common.observability import instrument_fastapi_app
from fastapi import FastAPI, Request, Response
from sqlalchemy import text

from careai_control_plane_api.api import router as control_plane_router
from careai_control_plane_api.database import Database

settings = load_settings("control-plane-api", 8000)
setup_json_logging(settings.service_name, settings.log_level, settings.environment)
logger = logging.getLogger(__name__)


def create_app(database_url: str | None = None, create_schema: bool = True) -> FastAPI:
    database = Database(database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if create_schema:
            database.prepare_schema()
        yield

    application = FastAPI(
        title="careai-platform Control Plane API",
        version="0.1.0",
        description=(
            "Control plane for datasets, model artifacts, deployments, prompts, "
            "evaluations, approvals, and audit events."
        ),
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Health", "description": "Service health and readiness endpoints."},
            {"name": "Datasets", "description": "Synthetic dataset asset registry."},
            {"name": "Models", "description": "Model artifact registry and promotion."},
            {"name": "Deployments", "description": "Deployment metadata tracking."},
            {"name": "Prompts", "description": "Prompt template registry and safety notes."},
            {"name": "Evaluations", "description": "Evaluation metrics and reports."},
            {"name": "Approvals", "description": "Human approval decisions."},
            {"name": "Audit", "description": "Immutable-style audit event trail."},
            {"name": "Monitoring", "description": "Prediction events, drift, and model telemetry."},
        ],
    )
    application.state.database = database
    application.state.event_publisher = event_publisher_from_env(settings.service_name)
    instrument_fastapi_app(application, settings)
    application.include_router(control_plane_router)
    register_core_routes(application)
    return application


async def correlation_middleware(request: Request, call_next) -> Response:
    token = set_correlation_id(request.headers.get("x-correlation-id"))
    try:
        response = await call_next(request)
        response.headers["x-correlation-id"] = ensure_correlation_id()
        return response
    finally:
        clear_correlation_id(token)


def register_core_routes(application: FastAPI) -> None:
    application.middleware("http")(correlation_middleware)

    @application.get(
        "/healthz",
        tags=["Health"],
        summary="Service health check",
        description="Returns service liveness without checking downstream dependencies.",
    )
    def healthz() -> dict[str, str]:
        logger.info("health check")
        return {"status": "ok", "service": settings.service_name}

    @application.get(
        "/readyz",
        tags=["Health"],
        summary="Service readiness check",
        description="Checks that the metadata database can respond to a trivial query.",
    )
    def readyz() -> dict[str, object]:
        database_status = "ready"
        session_generator = application.state.database.session()
        session = next(session_generator)
        try:
            session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("database readiness check failed")
            database_status = "unavailable"
        finally:
            session_generator.close()

        status_value = "ready" if database_status == "ready" else "degraded"
        return {
            "status": status_value,
            "service": settings.service_name,
            "dependencies": {
                "metadata_database": database_status,
                "redis": "configured",
                "mlflow": "configured",
            },
        }


app = create_app()
