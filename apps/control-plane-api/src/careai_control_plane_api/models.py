from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class DatasetAssetORM(Base):
    __tablename__ = "dataset_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    owner: Mapped[str] = mapped_column(String(160))
    schema_uri: Mapped[str] = mapped_column(String(512))
    storage_uri: Mapped[str] = mapped_column(String(512))
    pii_classification: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelArtifactORM(Base):
    __tablename__ = "model_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    framework: Mapped[str] = mapped_column(String(120))
    artifact_uri: Mapped[str] = mapped_column(String(512))
    training_dataset_id: Mapped[str] = mapped_column(String(36), index=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    lineage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    stage: Mapped[str] = mapped_column(String(40), default="dev", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelCardORM(Base):
    __tablename__ = "model_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_id: Mapped[str] = mapped_column(String(36), index=True)
    intended_use: Mapped[str] = mapped_column(Text)
    prohibited_use: Mapped[str] = mapped_column(Text)
    training_data_summary: Mapped[str] = mapped_column(Text)
    metrics_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    fairness_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    explainability_summary: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(160))
    reviewer: Mapped[str] = mapped_column(String(160))
    approval_status: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class DeploymentORM(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_id: Mapped[str] = mapped_column(String(36), index=True)
    champion_model_id: Mapped[str] = mapped_column(String(36), index=True)
    challenger_model_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    environment: Mapped[str] = mapped_column(String(80), index=True)
    deployment_type: Mapped[str] = mapped_column(String(80))
    endpoint_url: Mapped[str] = mapped_column(String(512))
    traffic_percent: Mapped[int] = mapped_column(Integer, default=0)
    traffic_split_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rollback_model_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    health_status: Mapped[str] = mapped_column(String(80), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PromptTemplateORM(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    template_text: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(160))
    safety_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PromptCardORM(Base):
    __tablename__ = "prompt_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    prompt_id: Mapped[str] = mapped_column(String(36), index=True)
    intended_use: Mapped[str] = mapped_column(Text)
    data_sources: Mapped[list] = mapped_column(JSON, default=list)
    safety_constraints: Mapped[list] = mapped_column(JSON, default=list)
    known_failure_modes: Mapped[list] = mapped_column(JSON, default=list)
    evaluation_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    owner: Mapped[str] = mapped_column(String(160))
    approval_status: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class EvaluationRunORM(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    report_uri: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApprovalORM(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    approver: Mapped[str] = mapped_column(String(160))
    decision: Mapped[str] = mapped_column(String(80), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEventORM(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(160), index=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    correlation_id: Mapped[str] = mapped_column(String(120), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PredictionEventORM(Base):
    __tablename__ = "prediction_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_name: Mapped[str] = mapped_column(String(160), index=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    request_features_json: Mapped[dict] = mapped_column(JSON, default=dict)
    prediction_score: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(40), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelErrorEventORM(Base):
    __tablename__ = "model_error_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_name: Mapped[str] = mapped_column(String(160), index=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    error_type: Mapped[str] = mapped_column(String(120), index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int] = mapped_column(Integer, default=500)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DriftSnapshotORM(Base):
    __tablename__ = "drift_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_name: Mapped[str] = mapped_column(String(160), index=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    drift_status: Mapped[str] = mapped_column(String(40), index=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_count: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
