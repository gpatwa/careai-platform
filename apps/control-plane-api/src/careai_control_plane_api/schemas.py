from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ModelStage = Literal["dev", "candidate", "staging", "approved", "production", "deprecated"]


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

