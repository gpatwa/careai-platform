import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AuditClient:
    def __init__(self, control_plane_url: str | None, enabled: bool = True) -> None:
        self.control_plane_url = control_plane_url.rstrip("/") if control_plane_url else None
        self.enabled = enabled

    def _headers(self, tenant_id: str | None = None) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if tenant_id:
            headers["x-tenant-id"] = tenant_id
        return headers

    def send_rag_query_event(
        self,
        *,
        user_id: str,
        correlation_id: str,
        metadata: dict[str, Any],
        tenant_id: str | None = None,
    ) -> bool:
        if not self.enabled or not self.control_plane_url:
            return False

        payload = {
            "actor": user_id,
            "action": "rag.query_answered",
            "target_type": "rag_query",
            "target_id": correlation_id,
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
            logger.warning("control-plane RAG audit delivery failed", extra={"error": str(exc)})
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
