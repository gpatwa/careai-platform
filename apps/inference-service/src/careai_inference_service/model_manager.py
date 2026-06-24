import json
import logging
import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import joblib
import mlflow.sklearn
import pandas as pd

from careai_inference_service.schemas import (
    FEATURE_COLUMNS,
    ActiveModelResponse,
    ClaimsRiskFeatures,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InferenceSettings:
    model_uri: str | None
    model_metadata_path: str | None
    feature_version: str
    max_feature_age_minutes: int
    control_plane_url: str | None
    audit_enabled: bool
    monitoring_enabled: bool = True
    traffic_split_json: dict[str, int] | None = None
    champion_model_name: str | None = None
    champion_model_version: str | None = None
    challenger_model_name: str | None = None
    challenger_model_version: str | None = None

    @classmethod
    def from_env(cls) -> "InferenceSettings":
        traffic_split_json = parse_traffic_split(os.getenv("CLAIMS_RISK_TRAFFIC_SPLIT_JSON"))
        return cls(
            model_uri=os.getenv("CLAIMS_RISK_MODEL_URI") or os.getenv("CLAIMS_RISK_MODEL_PATH"),
            model_metadata_path=os.getenv("CLAIMS_RISK_MODEL_METADATA_PATH"),
            feature_version=os.getenv("CLAIMS_RISK_FEATURE_VERSION", "claims-risk-features-v1"),
            max_feature_age_minutes=int(os.getenv("CLAIMS_RISK_MAX_FEATURE_AGE_MINUTES", "1440")),
            control_plane_url=os.getenv("CONTROL_PLANE_API_URL"),
            audit_enabled=os.getenv("INFERENCE_AUDIT_ENABLED", "true").lower() == "true",
            monitoring_enabled=os.getenv("INFERENCE_MONITORING_ENABLED", "true").lower() == "true",
            traffic_split_json=traffic_split_json,
            champion_model_name=os.getenv("CLAIMS_RISK_CHAMPION_MODEL_NAME"),
            champion_model_version=os.getenv("CLAIMS_RISK_CHAMPION_MODEL_VERSION"),
            challenger_model_name=os.getenv("CLAIMS_RISK_CHALLENGER_MODEL_NAME"),
            challenger_model_version=os.getenv("CLAIMS_RISK_CHALLENGER_MODEL_VERSION"),
        )


@dataclass
class LoadedModel:
    model: Any
    source: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ModelSelection:
    role: str
    model_name: str
    model_version: str
    traffic_split_json: dict[str, int]


class ModelManager:
    def __init__(self, settings: InferenceSettings) -> None:
        self.settings = settings
        self.loaded_model: LoadedModel | None = None
        self.load_error: str | None = None

    def load(self) -> bool:
        if not self.settings.model_uri:
            self.loaded_model = None
            self.load_error = "CLAIMS_RISK_MODEL_URI is not configured"
            logger.warning("claims-risk model not configured; fallback scoring enabled")
            return False

        try:
            model = self._load_model(self.settings.model_uri)
            metadata = self._load_metadata()
            self.loaded_model = LoadedModel(
                model=model,
                source=self.settings.model_uri,
                metadata=metadata,
            )
            self.load_error = None
            logger.info(
                "claims-risk model loaded",
                extra={
                    "model_name": metadata.get("name", "claims-risk"),
                    "model_version": metadata.get("version", "unknown"),
                },
            )
            return True
        except Exception as exc:
            self.loaded_model = None
            self.load_error = str(exc)
            logger.exception("claims-risk model load failed; fallback scoring enabled")
            return False

    def predict_score(self, features: ClaimsRiskFeatures) -> float | None:
        if self.loaded_model is None:
            return None

        frame = pd.DataFrame([{column: getattr(features, column) for column in FEATURE_COLUMNS}])
        probabilities = self.loaded_model.model.predict_proba(frame)
        return round(float(probabilities[0][1]), 6)

    def active_model(self) -> ActiveModelResponse:
        metadata = self.loaded_model.metadata if self.loaded_model else {}
        return ActiveModelResponse(
            model_name=str(metadata.get("name", "claims-risk-rules-fallback")),
            model_version=str(metadata.get("version", "fallback")),
            model_source=self.loaded_model.source if self.loaded_model else self.settings.model_uri,
            model_loaded=self.loaded_model is not None,
            fallback_mode=self.loaded_model is None,
            feature_version=self.settings.feature_version,
            warning=self.load_error,
            traffic_split_json=self.settings.traffic_split_json or {},
        )

    def select_model(self, routing_key: str) -> ModelSelection:
        active_model = self.active_model()
        split = normalized_traffic_split(self.settings.traffic_split_json)
        role = select_traffic_role(split, routing_key)
        if role == "challenger":
            return ModelSelection(
                role=role,
                model_name=self.settings.challenger_model_name or active_model.model_name,
                model_version=(
                    self.settings.challenger_model_version
                    or f"{active_model.model_version}-challenger"
                ),
                traffic_split_json=split,
            )
        return ModelSelection(
            role="champion",
            model_name=self.settings.champion_model_name or active_model.model_name,
            model_version=self.settings.champion_model_version or active_model.model_version,
            traffic_split_json=split,
        )

    def _load_model(self, model_uri: str) -> Any:
        if self._is_blob_url(model_uri):
            return self._load_joblib_from_blob_url(model_uri)

        path = Path(model_uri)
        if "://" not in model_uri and path.suffix in {".joblib", ".pkl"}:
            return joblib.load(path)
        return mlflow.sklearn.load_model(model_uri)

    def _load_metadata(self) -> dict[str, Any]:
        if self.settings.model_metadata_path:
            if self._is_blob_url(self.settings.model_metadata_path):
                return json.loads(self._read_text_from_blob_url(self.settings.model_metadata_path))
            metadata_path = Path(self.settings.model_metadata_path)
            if metadata_path.exists():
                return json.loads(metadata_path.read_text())
        return {"name": "claims-risk", "version": "unknown"}

    def _is_blob_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and parsed.netloc.endswith(
            ".blob.core.windows.net"
        )

    def _load_joblib_from_blob_url(self, blob_url: str) -> Any:
        blob_bytes = self._download_blob_bytes(blob_url)
        suffix = Path(urlparse(blob_url).path).suffix or ".joblib"
        with tempfile.NamedTemporaryFile(suffix=suffix) as temp_file:
            temp_file.write(blob_bytes)
            temp_file.flush()
            return joblib.load(temp_file.name)

    def _read_text_from_blob_url(self, blob_url: str) -> str:
        return self._download_blob_bytes(blob_url).decode("utf-8")

    def _download_blob_bytes(self, blob_url: str) -> bytes:
        try:
            from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
            from azure.storage.blob import BlobClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-storage-blob and azure-identity are required for Azure Blob model loading"
            ) from exc

        client_id = os.getenv("AZURE_MANAGED_IDENTITY_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID")
        credential = (
            ManagedIdentityCredential(client_id=client_id)
            if client_id
            else DefaultAzureCredential()
        )
        blob_client = BlobClient.from_blob_url(blob_url, credential=credential)
        return blob_client.download_blob().readall()


def parse_traffic_split(raw_value: str | None) -> dict[str, int] | None:
    if not raw_value:
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        logger.warning("invalid CLAIMS_RISK_TRAFFIC_SPLIT_JSON; using champion-only routing")
        return None
    if not isinstance(parsed, dict):
        logger.warning("CLAIMS_RISK_TRAFFIC_SPLIT_JSON must be a JSON object")
        return None
    normalized: dict[str, int] = {}
    for key, value in parsed.items():
        if key not in {"champion", "challenger"}:
            continue
        try:
            percent = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= percent <= 100:
            normalized[key] = percent
    if sum(normalized.values()) != 100:
        logger.warning("CLAIMS_RISK_TRAFFIC_SPLIT_JSON percentages must sum to 100")
        return None
    return normalized


def normalized_traffic_split(split: dict[str, int] | None) -> dict[str, int]:
    if not split:
        return {"champion": 100}
    normalized = {
        role: percent
        for role, percent in split.items()
        if role in {"champion", "challenger"} and 0 <= percent <= 100
    }
    if sum(normalized.values()) != 100:
        return {"champion": 100}
    return normalized


def select_traffic_role(split: dict[str, int], routing_key: str) -> str:
    bucket = int(sha256(routing_key.encode("utf-8")).hexdigest(), 16) % 100
    cumulative = 0
    for role in ("champion", "challenger"):
        cumulative += split.get(role, 0)
        if bucket < cumulative:
            return role
    return "champion"
