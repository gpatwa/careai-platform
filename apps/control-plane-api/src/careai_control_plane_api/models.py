from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
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


class DeploymentORM(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_id: Mapped[str] = mapped_column(String(36), index=True)
    environment: Mapped[str] = mapped_column(String(80), index=True)
    deployment_type: Mapped[str] = mapped_column(String(80))
    endpoint_url: Mapped[str] = mapped_column(String(512))
    traffic_percent: Mapped[int] = mapped_column(Integer, default=0)
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

