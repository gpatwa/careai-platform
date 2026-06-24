import logging
import os
from functools import lru_cache
from time import perf_counter
from typing import Any

from careai_common.config import AppSettings

try:
    from azure.monitor.opentelemetry import configure_azure_monitor
except ImportError:  # pragma: no cover - exercised when optional package is absent
    configure_azure_monitor = None

try:
    from fastapi import FastAPI, Request, Response
    from opentelemetry import metrics, trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.metrics import Counter, Histogram, Observation
    from opentelemetry.trace import Status, StatusCode
except ImportError:  # pragma: no cover - dependencies are installed in normal dev/runtime
    FastAPI = Any  # type: ignore[misc,assignment]
    Request = Any  # type: ignore[misc,assignment]
    Response = Any  # type: ignore[misc,assignment]
    metrics = None  # type: ignore[assignment]
    trace = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    Counter = Any  # type: ignore[misc,assignment]
    Histogram = Any  # type: ignore[misc,assignment]
    Observation = None  # type: ignore[assignment]
    UpDownCounter = Any  # type: ignore[misc,assignment]
    Status = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DRIFT_STATUS_VALUES = {"green": 0, "yellow": 1, "red": 2}
_drift_status_by_model: dict[tuple[str, str], int] = {}


def patch_fastapi_instrumentation_route_details() -> None:
    try:
        import opentelemetry.instrumentation.fastapi as fastapi_instrumentation
    except ImportError:  # pragma: no cover - optional dependency
        return

    if getattr(fastapi_instrumentation, "_careai_route_patch_applied", False):
        return

    route_cls = fastapi_instrumentation.Route
    match_enum = fastapi_instrumentation.Match

    def safe_get_route_details(scope: dict[str, Any]) -> str | None:
        app = scope["app"]
        route = None

        for starlette_route in app.routes:
            match, _ = (
                route_cls.matches(starlette_route, scope)
                if isinstance(starlette_route, route_cls)
                else starlette_route.matches(scope)
            )
            candidate_route = getattr(starlette_route, "path", scope.get("path"))
            if match == match_enum.FULL:
                route = candidate_route
                break
            if match == match_enum.PARTIAL:
                route = candidate_route
        return route

    fastapi_instrumentation._get_route_details = safe_get_route_details
    fastapi_instrumentation._careai_route_patch_applied = True


def _drift_status_callback(_options: object) -> list[object]:
    if Observation is None:
        return []
    return [
        Observation(value, {"model_name": model_name, "environment": environment})
        for (model_name, environment), value in _drift_status_by_model.items()
    ]


class ObservabilityRecorder:
    def __init__(self, *, service_name: str, environment: str) -> None:
        self.service_name = service_name
        self.environment = environment
        self.meter = metrics.get_meter(service_name) if metrics else None
        self.request_count = self._counter(
            "careai.http.server.request.count",
            "HTTP request count.",
        )
        self.request_error_count = self._counter(
            "careai.http.server.error.count",
            "HTTP request error count.",
        )
        self.request_latency = self._histogram(
            "careai.http.server.latency_ms",
            "HTTP request latency in milliseconds.",
            "ms",
        )
        self.prediction_count = self._counter(
            "careai.prediction.count",
            "Claims-risk prediction count.",
        )
        self.fallback_count = self._counter(
            "careai.fallback.count",
            "Fallback execution count.",
        )
        self.rag_query_count = self._counter("careai.rag.query.count", "RAG query count.")
        self.retrieval_latency = self._histogram(
            "careai.rag.retrieval.latency_ms",
            "RAG retrieval latency in milliseconds.",
            "ms",
        )
        self.llm_latency = self._histogram(
            "careai.rag.llm.latency_ms",
            "LLM generation latency in milliseconds.",
            "ms",
        )
        self.safety_flag_count = self._counter(
            "careai.rag.safety_flag.count",
            "RAG safety flag count.",
        )
        self.drift_status_gauge = self._drift_status_gauge()

    def _attributes(self, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = {"service_name": self.service_name, "environment": self.environment}
        if attributes:
            merged.update({key: value for key, value in attributes.items() if value is not None})
        return merged

    def _counter(self, name: str, description: str) -> Counter | None:
        if self.meter is None:
            return None
        return self.meter.create_counter(name, unit="1", description=description)

    def _histogram(self, name: str, description: str, unit: str) -> Histogram | None:
        if self.meter is None:
            return None
        return self.meter.create_histogram(name, unit=unit, description=description)

    def _drift_status_gauge(self) -> object | None:
        if self.meter is None:
            return None
        return _create_drift_status_gauge(self.meter)

    def record_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        latency_ms: float,
    ) -> None:
        attributes = self._attributes(
            {"http_method": method, "http_route": route, "http_status_code": status_code}
        )
        if self.request_count:
            self.request_count.add(1, attributes)
        if self.request_latency:
            self.request_latency.record(latency_ms, attributes)
        if status_code >= 500 and self.request_error_count:
            self.request_error_count.add(1, attributes)

    def record_prediction(
        self,
        *,
        model_name: str,
        model_version: str,
        fallback_mode: bool,
        risk_band: str,
    ) -> None:
        attributes = self._attributes(
            {
                "model_name": model_name,
                "model_version": model_version,
                "risk_band": risk_band,
            }
        )
        if self.prediction_count:
            self.prediction_count.add(1, attributes)
        if fallback_mode and self.fallback_count:
            self.fallback_count.add(1, attributes | {"fallback_type": "claims-risk"})

    def record_drift_status(self, *, model_name: str, status: str) -> None:
        _drift_status_by_model[(model_name, self.environment)] = DRIFT_STATUS_VALUES.get(status, -1)

    def record_rag_query(
        self,
        *,
        prompt_version: str,
        provider: str,
        safety_flags: list[str],
        retrieval_latency_ms: float,
        llm_latency_ms: float,
        fallback_mode: bool,
    ) -> None:
        attributes = self._attributes({"prompt_version": prompt_version, "provider": provider})
        if self.rag_query_count:
            self.rag_query_count.add(1, attributes)
        if self.retrieval_latency:
            self.retrieval_latency.record(retrieval_latency_ms, attributes)
        if self.llm_latency:
            self.llm_latency.record(llm_latency_ms, attributes)
        if fallback_mode and self.fallback_count:
            self.fallback_count.add(1, attributes | {"fallback_type": "rag"})
        if self.safety_flag_count:
            for flag in safety_flags:
                self.safety_flag_count.add(1, attributes | {"safety_flag": flag})


@lru_cache(maxsize=1)
def _create_drift_status_gauge(meter: Any) -> object:
    return meter.create_observable_gauge(
        "careai.drift.status",
        callbacks=[_drift_status_callback],
        unit="1",
        description="Latest drift status by model: green=0, yellow=1, red=2.",
    )


def configure_application_insights(settings: AppSettings) -> bool:
    connection_string = settings.applicationinsights_connection_string or os.getenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING"
    )
    if not connection_string:
        return False
    if configure_azure_monitor is None:
        logger.warning("Application Insights configured but Azure Monitor exporter is unavailable")
        return False
    try:
        configure_azure_monitor(connection_string=connection_string)
    except Exception:
        logger.exception("Application Insights OpenTelemetry configuration failed")
        return False
    logger.info(
        "Application Insights OpenTelemetry export enabled",
        extra={"environment": settings.environment},
    )
    return True


def instrument_fastapi_app(application: FastAPI, settings: AppSettings) -> ObservabilityRecorder:
    app_insights_enabled = configure_application_insights(settings)
    if FastAPIInstrumentor is not None:
        try:
            patch_fastapi_instrumentation_route_details()
            FastAPIInstrumentor.instrument_app(application)
        except Exception:
            logger.exception("FastAPI OpenTelemetry instrumentation failed")

    recorder = ObservabilityRecorder(
        service_name=settings.service_name,
        environment=settings.environment,
    )
    application.state.observability = recorder
    application.state.application_insights_enabled = app_insights_enabled
    application.middleware("http")(observability_middleware(recorder))
    return recorder


def observability_middleware(recorder: ObservabilityRecorder):
    async def middleware(request: Request, call_next) -> Response:
        started_at = perf_counter()
        status_code = 500
        span = trace.get_current_span() if trace else None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            if span is not None and Status is not None and StatusCode is not None:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            route = (
                getattr(request.scope.get("route"), "path", None) or request.url.path or "unknown"
            )
            latency_ms = max((perf_counter() - started_at) * 1000, 0.0)
            recorder.record_request(
                method=request.method,
                route=route,
                status_code=status_code,
                latency_ms=latency_ms,
            )
            if span is not None:
                span.set_attribute("careai.service_name", recorder.service_name)
                span.set_attribute("careai.environment", recorder.environment)
                span.set_attribute("http.route", route)

    return middleware
