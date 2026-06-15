import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from careai_common.config import load_settings
from careai_common.correlation import (
    clear_correlation_id,
    ensure_correlation_id,
    set_correlation_id,
)
from careai_common.events import EventPublisher, build_event, event_publisher_from_env
from careai_common.logging import setup_json_logging
from careai_common.observability import instrument_fastapi_app
from fastapi import FastAPI, Request, Response

from careai_inference_service.audit import AuditClient
from careai_inference_service.model_manager import InferenceSettings, ModelManager
from careai_inference_service.schemas import (
    ActiveModelResponse,
    ClaimsRiskPredictionRequest,
    ClaimsRiskPredictionResponse,
    ReloadModelResponse,
)
from careai_inference_service.scoring import (
    fallback_score,
    feature_warnings,
    reason_codes,
    risk_band,
)

settings = load_settings("inference-service", 8001)
setup_json_logging(settings.service_name, settings.log_level, settings.environment)
logger = logging.getLogger(__name__)


async def correlation_middleware(request: Request, call_next) -> Response:
    token = set_correlation_id(request.headers.get("x-correlation-id"))
    try:
        response = await call_next(request)
        response.headers["x-correlation-id"] = ensure_correlation_id()
        return response
    finally:
        clear_correlation_id(token)


def create_app(
    inference_settings: InferenceSettings | None = None,
    load_model: bool = True,
    event_publisher: EventPublisher | None = None,
) -> FastAPI:
    runtime_settings = inference_settings or InferenceSettings.from_env()
    model_manager = ModelManager(runtime_settings)
    audit_client = AuditClient(
        control_plane_url=runtime_settings.control_plane_url,
        enabled=runtime_settings.audit_enabled,
        monitoring_enabled=runtime_settings.monitoring_enabled,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if load_model:
            app.state.model_manager.load()
        yield

    application = FastAPI(
        title="careai-platform Inference Service",
        version="0.1.0",
        description="Real-time inference API for synthetic claims-risk scoring.",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Health", "description": "Service health and readiness."},
            {"name": "Predictions", "description": "Synthetic claims-risk predictions."},
            {"name": "Models", "description": "Active model metadata and reload controls."},
        ],
    )
    application.state.inference_settings = runtime_settings
    application.state.model_manager = model_manager
    application.state.audit_client = audit_client
    application.state.event_publisher = event_publisher or event_publisher_from_env(
        settings.service_name
    )
    instrument_fastapi_app(application, settings)
    application.middleware("http")(correlation_middleware)
    register_routes(application)
    return application


def register_routes(application: FastAPI) -> None:
    @application.get(
        "/healthz",
        tags=["Health"],
        summary="Service health check",
        description="Returns service liveness without requiring a loaded model.",
    )
    def healthz() -> dict[str, str]:
        logger.info("health check")
        return {"status": "ok", "service": settings.service_name}

    @application.get(
        "/readyz",
        tags=["Health"],
        summary="Service readiness check",
        description="Returns ready when the service can score using either model or fallback mode.",
    )
    def readyz() -> dict[str, object]:
        model_manager: ModelManager = application.state.model_manager
        active_model = model_manager.active_model()
        return {
            "status": "ready",
            "service": settings.service_name,
            "dependencies": {
                "model": "loaded" if active_model.model_loaded else "fallback",
                "control_plane_audit": (
                    "configured"
                    if application.state.audit_client.control_plane_url
                    else "not_configured"
                ),
            },
            "fallback_mode": active_model.fallback_mode,
        }

    @application.get(
        "/models/active",
        response_model=ActiveModelResponse,
        tags=["Models"],
        summary="Get active claims-risk model metadata",
        description="Returns loaded model metadata or fallback model status.",
    )
    def get_active_model() -> ActiveModelResponse:
        model_manager: ModelManager = application.state.model_manager
        return model_manager.active_model()

    @application.post(
        "/admin/reload-model",
        response_model=ReloadModelResponse,
        tags=["Models"],
        summary="Reload configured model",
        description="Reloads the configured model URI/path and reports active model state.",
    )
    def reload_model() -> ReloadModelResponse:
        model_manager: ModelManager = application.state.model_manager
        reloaded = model_manager.load()
        return ReloadModelResponse(reloaded=reloaded, active_model=model_manager.active_model())

    @application.post(
        "/predict/claims-risk",
        response_model=ClaimsRiskPredictionResponse,
        tags=["Predictions"],
        summary="Predict synthetic claims risk",
        description=(
            "Scores synthetic healthcare-like claims features. No real patient data, PHI, "
            "or PII should be sent."
        ),
    )
    def predict_claims_risk(payload: ClaimsRiskPredictionRequest) -> ClaimsRiskPredictionResponse:
        started_at = perf_counter()
        model_manager: ModelManager = application.state.model_manager
        active_model = model_manager.active_model()
        correlation_id = ensure_correlation_id()
        target_id = payload.request_id or str(uuid4())
        selected_model = model_manager.select_model(target_id or correlation_id)
        warnings = feature_warnings(
            payload.features,
            application.state.inference_settings.max_feature_age_minutes,
        )
        prediction_error_type: str | None = None

        try:
            score = model_manager.predict_score(payload.features)
        except Exception as exc:
            logger.exception("claims-risk model prediction failed; fallback scoring enabled")
            prediction_error_type = exc.__class__.__name__
            score = None
            warnings.append("model_prediction_failed_rules_fallback_used")

        fallback_mode = score is None
        if fallback_mode:
            score = fallback_score(payload.features)
            if "model_prediction_failed_rules_fallback_used" not in warnings:
                warnings.append("model_unavailable_rules_fallback_used")

        band = risk_band(score)
        latency_ms = max(int((perf_counter() - started_at) * 1000), 0)

        logger.info(
            "claims-risk prediction",
            extra={
                "target_id": target_id,
                "risk_band": band,
                "model_name": selected_model.model_name,
                "model_version": selected_model.model_version,
                "selected_model_role": selected_model.role,
                "fallback_mode": fallback_mode,
                "warning_count": len(warnings),
                "latency_ms": latency_ms,
            },
        )
        application.state.observability.record_prediction(
            model_name=selected_model.model_name,
            model_version=selected_model.model_version,
            fallback_mode=fallback_mode,
            risk_band=band,
        )

        application.state.audit_client.send_prediction_event(
            actor="inference-service",
            action="claims_risk.predicted",
            target_id=target_id,
            correlation_id=correlation_id,
            metadata={
                "risk_band": band,
                "model_name": selected_model.model_name,
                "model_version": selected_model.model_version,
                "selected_model_role": selected_model.role,
                "traffic_split_json": selected_model.traffic_split_json,
                "feature_version": active_model.feature_version,
                "fallback_mode": fallback_mode,
                "warnings": warnings,
            },
        )
        application.state.audit_client.send_monitoring_prediction_event(
            model_name=selected_model.model_name,
            model_version=selected_model.model_version,
            request_features=payload.features.feature_frame_record(),
            prediction_score=score,
            risk_band=band,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
        )
        publish_event_safely(
            application.state.event_publisher,
            build_event(
                event_type="prediction.created",
                source=settings.service_name,
                subject=f"model/{selected_model.model_name}",
                correlation_id=correlation_id,
                payload={
                    "model_name": selected_model.model_name,
                    "model_version": selected_model.model_version,
                    "selected_model_role": selected_model.role,
                    "traffic_split_json": selected_model.traffic_split_json,
                    "feature_version": active_model.feature_version,
                    "request_features_json": payload.features.feature_frame_record(),
                    "prediction_score": score,
                    "risk_band": band,
                    "latency_ms": latency_ms,
                    "fallback_mode": fallback_mode,
                },
            ),
        )
        if prediction_error_type:
            application.state.audit_client.send_monitoring_error_event(
                model_name=selected_model.model_name,
                model_version=selected_model.model_version,
                error_type="model_prediction_failed",
                error_message="Model prediction failed; deterministic fallback score returned.",
                status_code=200,
                latency_ms=latency_ms,
                correlation_id=correlation_id,
            )

        return ClaimsRiskPredictionResponse(
            prediction_score=score,
            risk_band=band,
            model_name=selected_model.model_name,
            model_version=selected_model.model_version,
            selected_model_role=selected_model.role,
            traffic_split_json=selected_model.traffic_split_json,
            feature_version=active_model.feature_version,
            decision_reason_codes=reason_codes(payload.features, score),
            correlation_id=correlation_id,
            warnings=warnings,
            fallback_mode=fallback_mode,
        )


def publish_event_safely(event_publisher: EventPublisher, event) -> bool:
    try:
        return event_publisher.publish(event)
    except Exception as exc:
        logger.warning(
            "event publish failed",
            extra={"event_type": event.event_type, "error": str(exc)},
        )
        return False


app = create_app()
