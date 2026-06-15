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

    def send_prediction_event(
        self,
        *,
        actor: str,
        action: str,
        target_id: str,
        correlation_id: str,
        metadata: dict[str, Any],
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
                response = client.post(f"{self.control_plane_url}/audit-events", json=payload)
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
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning(
                "control-plane prediction-event delivery failed",
                extra={"error": str(exc)},
            )
            return False
