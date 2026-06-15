from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_control_plane_schema"
down_revision = None
branch_labels = None
depends_on = None


def has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def create_table_if_missing(table_name: str, *columns: sa.Column) -> None:
    if not has_table(table_name):
        op.create_table(table_name, *columns)


def create_indexes(table_name: str, column_names: Iterable[str]) -> None:
    existing_indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }
    for column_name in column_names:
        index_name = f"ix_{table_name}_{column_name}"
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, [column_name])


def standard_id() -> sa.Column:
    return sa.Column("id", sa.String(length=36), primary_key=True)


def created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    create_table_if_missing(
        "dataset_assets",
        standard_id(),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("owner", sa.String(length=160), nullable=False),
        sa.Column("schema_uri", sa.String(length=512), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("pii_classification", sa.String(length=80), nullable=False),
        created_at(),
    )
    create_indexes("dataset_assets", ["name", "version"])

    create_table_if_missing(
        "model_artifacts",
        standard_id(),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("framework", sa.String(length=120), nullable=False),
        sa.Column("artifact_uri", sa.String(length=512), nullable=False),
        sa.Column("training_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("lineage_json", sa.JSON(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        created_at(),
    )
    create_indexes(
        "model_artifacts",
        ["name", "version", "training_dataset_id", "stage"],
    )

    create_table_if_missing(
        "deployments",
        standard_id(),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=80), nullable=False),
        sa.Column("deployment_type", sa.String(length=80), nullable=False),
        sa.Column("endpoint_url", sa.String(length=512), nullable=False),
        sa.Column("traffic_percent", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        created_at(),
    )
    create_indexes("deployments", ["model_id", "environment", "status"])

    create_table_if_missing(
        "prompt_templates",
        standard_id(),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=160), nullable=False),
        sa.Column("safety_notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        created_at(),
    )
    create_indexes("prompt_templates", ["name", "version", "status"])

    create_table_if_missing(
        "evaluation_runs",
        standard_id(),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("report_uri", sa.String(length=512), nullable=False),
        created_at(),
    )
    create_indexes("evaluation_runs", ["target_type", "target_id"])

    create_table_if_missing(
        "approvals",
        standard_id(),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("approver", sa.String(length=160), nullable=False),
        sa.Column("decision", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        created_at(),
    )
    create_indexes("approvals", ["target_type", "target_id", "decision"])

    create_table_if_missing(
        "audit_events",
        standard_id(),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        created_at(),
    )
    create_indexes(
        "audit_events",
        ["actor", "action", "target_type", "target_id", "correlation_id"],
    )

    create_table_if_missing(
        "prediction_events",
        standard_id(),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("request_features_json", sa.JSON(), nullable=False),
        sa.Column("prediction_score", sa.Float(), nullable=False),
        sa.Column("risk_band", sa.String(length=40), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        created_at(),
    )
    create_indexes(
        "prediction_events",
        ["model_name", "model_version", "risk_band", "correlation_id"],
    )

    create_table_if_missing(
        "model_error_events",
        standard_id(),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("error_type", sa.String(length=120), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        created_at(),
    )
    create_indexes(
        "model_error_events",
        ["model_name", "model_version", "error_type", "correlation_id"],
    )

    create_table_if_missing(
        "drift_snapshots",
        standard_id(),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("drift_status", sa.String(length=40), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("baseline_count", sa.Integer(), nullable=False),
        sa.Column("recent_count", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        created_at(),
    )
    create_indexes(
        "drift_snapshots",
        ["model_name", "model_version", "drift_status", "correlation_id"],
    )


def downgrade() -> None:
    for table_name in [
        "drift_snapshots",
        "model_error_events",
        "prediction_events",
        "audit_events",
        "approvals",
        "evaluation_runs",
        "prompt_templates",
        "deployments",
        "model_artifacts",
        "dataset_assets",
    ]:
        if has_table(table_name):
            op.drop_table(table_name)
