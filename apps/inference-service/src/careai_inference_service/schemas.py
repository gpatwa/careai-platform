from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AgeBucket = Literal["18-34", "35-49", "50-64", "65+"]
PlanType = Literal["bronze", "silver", "gold", "platinum", "medicare_advantage"]
RiskBand = Literal["low", "medium", "high"]

FEATURE_COLUMNS = [
    "age_bucket",
    "plan_type",
    "prior_claim_count",
    "recent_visit_count",
    "medication_count",
    "chronic_condition_count",
    "region_code",
]


class ClaimsRiskFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_bucket: AgeBucket
    plan_type: PlanType
    prior_claim_count: int = Field(..., ge=0, le=100)
    recent_visit_count: int = Field(..., ge=0, le=100)
    medication_count: int = Field(..., ge=0, le=100)
    chronic_condition_count: int = Field(..., ge=0, le=20)
    region_code: str = Field(..., pattern=r"^R\d{2}$")
    feature_timestamp: datetime | None = Field(
        default=None,
        description="Optional timestamp when features were computed.",
    )

    def feature_frame_record(self) -> dict[str, Any]:
        return {column: getattr(self, column) for column in FEATURE_COLUMNS}


class ClaimsRiskPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    features: ClaimsRiskFeatures
    request_id: str | None = Field(default=None, description="Synthetic request identifier.")


class ActiveModelResponse(BaseModel):
    model_name: str
    model_version: str
    model_source: str | None
    model_loaded: bool
    fallback_mode: bool
    feature_version: str
    warning: str | None = None


class ClaimsRiskPredictionResponse(BaseModel):
    prediction_score: float = Field(..., ge=0, le=1)
    risk_band: RiskBand
    model_name: str
    model_version: str
    feature_version: str
    decision_reason_codes: list[str]
    correlation_id: str
    warnings: list[str] = Field(default_factory=list)
    fallback_mode: bool = False


class ReloadModelResponse(BaseModel):
    reloaded: bool
    active_model: ActiveModelResponse

