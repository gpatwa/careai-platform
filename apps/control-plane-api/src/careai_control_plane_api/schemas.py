from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ModelStage = Literal["dev", "candidate", "staging", "approved", "production", "deprecated"]
RiskBand = Literal["low", "medium", "high"]
DriftStatus = Literal["green", "yellow", "red"]
SloStatus = Literal["healthy", "breached", "unknown"]
CardApprovalStatus = Literal["draft", "in_review", "approved", "rejected"]


class DatasetAssetCreate(BaseModel):
    name: str = Field(..., description="Dataset display name.")
    version: str = Field(..., description="Dataset semantic or build version.")
    owner: str = Field(..., description="Responsible owner or team.")
    schema_uri: str = Field(..., description="URI for the dataset schema contract.")
    storage_uri: str = Field(..., description="URI for synthetic dataset storage.")
    pii_classification: str = Field(
        default="synthetic-no-phi",
        description="Synthetic data classification. Do not use real PHI/PII.",
    )


class DatasetAssetRead(DatasetAssetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class ModelArtifactCreate(BaseModel):
    name: str = Field(..., description="Model display name.")
    version: str = Field(..., description="Model artifact version.")
    framework: str = Field(..., description="Training or serving framework.")
    artifact_uri: str = Field(..., description="URI for the stored model artifact.")
    training_dataset_id: str = Field(..., description="Dataset asset used for training.")
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    lineage_json: dict[str, Any] = Field(default_factory=dict)
    stage: ModelStage = Field(default="dev", description="Current model lifecycle stage.")


class ModelArtifactRead(ModelArtifactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class ModelCardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(..., description="Model artifact identifier covered by this card.")
    intended_use: str = Field(..., description="Approved use cases for this synthetic model.")
    prohibited_use: str = Field(..., description="Uses that are not allowed.")
    training_data_summary: str = Field(..., description="Synthetic training data summary.")
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    fairness_summary: dict[str, Any] = Field(default_factory=dict)
    explainability_summary: str = Field(..., description="Explainability and reason-code summary.")
    owner: str = Field(..., description="Responsible owner or team.")
    reviewer: str = Field(..., description="Responsible AI or model-risk reviewer.")
    approval_status: CardApprovalStatus = Field(default="draft")


class ModelCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intended_use: str
    prohibited_use: str
    training_data_summary: str
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    fairness_summary: dict[str, Any] = Field(default_factory=dict)
    explainability_summary: str
    owner: str
    reviewer: str
    approval_status: CardApprovalStatus


class ModelCardRead(ModelCardCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class PromoteModelRequest(BaseModel):
    stage: ModelStage = Field(..., description="Target stage for model promotion.")
    actor: str | None = Field(default=None, description="Optional actor override for audit.")
    notes: str = Field(default="", description="Promotion rationale or governance note.")


class DeploymentCreate(BaseModel):
    model_id: str = Field(..., description="Model artifact to deploy.")
    environment: str = Field(..., description="Target environment such as dev or prod.")
    deployment_type: str = Field(..., description="Deployment strategy such as canary.")
    endpoint_url: str = Field(..., description="Serving endpoint URL.")
    traffic_percent: int = Field(default=0, ge=0, le=100)
    status: str = Field(default="pending", description="Deployment status.")


class DeploymentRead(DeploymentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class PromptTemplateCreate(BaseModel):
    name: str = Field(..., description="Prompt template name.")
    version: str = Field(..., description="Prompt template version.")
    template_text: str = Field(..., description="Template body. Use synthetic examples only.")
    owner: str = Field(..., description="Responsible owner or team.")
    safety_notes: str = Field(default="", description="Responsible AI and safety notes.")
    status: str = Field(default="draft", description="Prompt lifecycle status.")


class PromptTemplateRead(PromptTemplateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class PromptCardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(..., description="Prompt template identifier covered by this card.")
    intended_use: str = Field(..., description="Approved use cases for this prompt.")
    data_sources: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    evaluation_summary: dict[str, Any] = Field(default_factory=dict)
    owner: str = Field(..., description="Responsible owner or team.")
    approval_status: CardApprovalStatus = Field(default="draft")


class PromptCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intended_use: str
    data_sources: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    evaluation_summary: dict[str, Any] = Field(default_factory=dict)
    owner: str
    approval_status: CardApprovalStatus


class PromptCardRead(PromptCardCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class EvaluationRunCreate(BaseModel):
    target_type: str = Field(..., description="Evaluated target type, such as model or prompt.")
    target_id: str = Field(..., description="Evaluated target identifier.")
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    passed: bool = Field(default=False)
    report_uri: str = Field(..., description="URI for evaluation report artifact.")


class EvaluationRunRead(EvaluationRunCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class ApprovalCreate(BaseModel):
    target_type: str = Field(..., description="Approval target type.")
    target_id: str = Field(..., description="Approval target identifier.")
    approver: str = Field(..., description="Synthetic approver identifier or team alias.")
    decision: str = Field(..., description="Approval decision.")
    notes: str = Field(default="", description="Approval notes.")


class ApprovalRead(ApprovalCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor: str
    action: str
    target_type: str
    target_id: str
    correlation_id: str
    metadata_json: dict[str, Any]
    created_at: datetime


class AuditEventCreate(BaseModel):
    actor: str = Field(..., description="Synthetic actor or service identifier.")
    action: str = Field(..., description="Action name for the audit event.")
    target_type: str = Field(..., description="Target resource type.")
    target_id: str = Field(..., description="Target resource identifier.")
    correlation_id: str = Field(..., description="Correlation ID from the originating request.")
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., description="Served model name.")
    model_version: str = Field(..., description="Served model version.")
    request_features_json: dict[str, Any] = Field(
        default_factory=dict,
        description="Synthetic aggregate feature values used for monitoring.",
    )
    prediction_score: float = Field(..., ge=0, le=1)
    risk_band: RiskBand
    latency_ms: int = Field(..., ge=0)
    correlation_id: str = Field(..., description="Request correlation ID.")


class PredictionEventRead(PredictionEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class ModelErrorEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., description="Served model name.")
    model_version: str = Field(..., description="Served model version.")
    error_type: str = Field(..., description="Safe error category without PHI/PII.")
    error_message: str = Field(
        default="",
        description="Safe operational error summary. Do not include raw PHI/PII-like values.",
    )
    status_code: int = Field(default=500, ge=100, le=599)
    latency_ms: int = Field(..., ge=0)
    correlation_id: str = Field(..., description="Request correlation ID.")


class ModelErrorEventRead(ModelErrorEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class DriftCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_features_json: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional synthetic baseline feature records.",
    )
    baseline_distribution_json: dict[str, dict[str, float]] | None = Field(
        default=None,
        description="Optional precomputed baseline feature distributions.",
    )
    lookback_hours: int = Field(default=24, ge=1, le=24 * 30)
    minimum_events: int = Field(default=1, ge=1)
    yellow_threshold: float = Field(default=0.10, ge=0)
    red_threshold: float = Field(default=0.25, ge=0)


class DriftFeatureMetric(BaseModel):
    feature_name: str
    metric_name: str
    value: float
    status: DriftStatus
    baseline_distribution: dict[str, float]
    recent_distribution: dict[str, float]


class DriftCheckResponse(BaseModel):
    model_name: str
    model_version: str
    drift_status: DriftStatus
    baseline_count: int
    recent_count: int
    feature_metrics: list[DriftFeatureMetric]
    rollback_recommended: bool
    snapshot_id: str
    created_at: datetime
    dashboard_contract: dict[str, Any]


class MonitoringSummaryResponse(BaseModel):
    model_name: str
    event_count: int
    error_count: int
    model_versions: list[str]
    avg_latency_ms: float | None
    p95_latency_ms: int | None
    avg_prediction_score: float | None
    risk_band_counts: dict[str, int]
    high_risk_rate: float | None
    error_rate: float
    latency_slo_ms: int
    error_rate_slo: float
    slo_status: SloStatus
    latest_drift_status: DriftStatus | None
    latest_drift_snapshot_id: str | None
    dashboard_contract: dict[str, Any]
