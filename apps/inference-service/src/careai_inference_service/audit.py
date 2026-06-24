import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AuditClient:
    def __init__(
        self,
        control_plane_url: str | None,
        enabled: bool = True,
        monitoring_enabled: bool = True,
    ) -> None:
        self.control_plane_url = control_plane_url.rstrip("/") if control_plane_url else None
        self.enabled = enabled
        self.monitoring_enabled = monitoring_enabled

    def _headers(self, tenant_id: str | None = None) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if tenant_id:
            headers["x-tenant-id"] = tenant_id
        return headers

    def send_prediction_event(
        self,
        *,
        actor: str,
        action: str,
        target_id: str,
        correlation_id: str,
        metadata: dict[str, Any],
        tenant_id: str | None = None,
    ) -> bool:
        if not self.enabled or not self.control_plane_url:
            return False

        payload = {
            "actor": actor,
            "action": action,
            "target_type": "prediction",
            "target_id": target_id,
            "correlation_id": correlation_id,
            "metadata_json": metadata,
        }
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(
                    f"{self.control_plane_url}/audit-events",
                    json=payload,
                    headers=self._headers(tenant_id),
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning("control-plane audit delivery failed", extra={"error": str(exc)})
            return False

    def send_monitoring_prediction_event(
        self,
        *,
        model_name: str,
        model_version: str,
        request_features: dict[str, Any],
        prediction_score: float,
        risk_band: str,
        latency_ms: int,
        correlation_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        if not self.monitoring_enabled or not self.control_plane_url:
            return False

        payload = {
            "model_name": model_name,
            "model_version": model_version,
            "request_features_json": request_features,
            "prediction_score": prediction_score,
            "risk_band": risk_band,
            "latency_ms": latency_ms,
            "correlation_id": correlation_id,
        }
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(
                    f"{self.control_plane_url}/monitoring/prediction-events",
                    json=payload,
                    headers=self._headers(tenant_id),
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning(
                "control-plane prediction-event delivery failed",
                extra={"error": str(exc)},
            )
            return False

    def send_monitoring_error_event(
        self,
        *,
        model_name: str,
        model_version: str,
        error_type: str,
        error_message: str,
        status_code: int,
        latency_ms: int,
        correlation_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        if not self.monitoring_enabled or not self.control_plane_url:
            return False

        payload = {
            "model_name": model_name,
            "model_version": model_version,
            "error_type": error_type,
            "error_message": error_message,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "correlation_id": correlation_id,
        }
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(
                    f"{self.control_plane_url}/monitoring/error-events",
                    json=payload,
                    headers=self._headers(tenant_id),
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning(
                "control-plane model-error-event delivery failed",
                extra={"error": str(exc)},
            )
            return False

    def send_workflow_signal(
        self,
        *,
        workflow_run_id: str,
        signal_type: str,
        signal_metadata: dict[str, Any],
        actor: str,
        tenant_id: str | None = None,
    ) -> bool:
        if not self.enabled or not self.control_plane_url:
            return False

        payload = {
            "signal_type": signal_type,
            "signal_metadata": signal_metadata,
            "actor": actor,
        }
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(
                    f"{self.control_plane_url}/workflow-runs/{workflow_run_id}/signals",
                    json=payload,
                    headers=self._headers(tenant_id),
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning(
                "control-plane workflow-signal delivery failed",
                extra={"error": str(exc), "signal_type": signal_type},
            )
            return False
