import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    @classmethod
    def from_env(cls) -> "InferenceSettings":
        return cls(
            model_uri=os.getenv("CLAIMS_RISK_MODEL_URI") or os.getenv("CLAIMS_RISK_MODEL_PATH"),
            model_metadata_path=os.getenv("CLAIMS_RISK_MODEL_METADATA_PATH"),
            feature_version=os.getenv("CLAIMS_RISK_FEATURE_VERSION", "claims-risk-features-v1"),
            max_feature_age_minutes=int(os.getenv("CLAIMS_RISK_MAX_FEATURE_AGE_MINUTES", "1440")),
            control_plane_url=os.getenv("CONTROL_PLANE_API_URL"),
            audit_enabled=os.getenv("INFERENCE_AUDIT_ENABLED", "true").lower() == "true",
        )


@dataclass
class LoadedModel:
    model: Any
    source: str
    metadata: dict[str, Any]


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
        )

    def _load_model(self, model_uri: str) -> Any:
        path = Path(model_uri)
        if "://" not in model_uri and path.suffix in {".joblib", ".pkl"}:
            return joblib.load(path)
        return mlflow.sklearn.load_model(model_uri)

    def _load_metadata(self) -> dict[str, Any]:
        if self.settings.model_metadata_path:
            metadata_path = Path(self.settings.model_metadata_path)
            if metadata_path.exists():
                return json.loads(metadata_path.read_text())
        return {"name": "claims-risk", "version": "unknown"}
