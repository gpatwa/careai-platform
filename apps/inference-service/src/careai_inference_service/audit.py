import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AuditClient:
    def __init__(self, control_plane_url: str | None, enabled: bool = True) -> None:
        self.control_plane_url = control_plane_url.rstrip("/") if control_plane_url else None
        self.enabled = enabled

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

