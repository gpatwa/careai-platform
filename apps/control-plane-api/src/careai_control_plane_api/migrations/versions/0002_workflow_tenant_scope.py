from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op

revision = "0002_workflow_tenant_scope"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def has_column(table_name: str, column_name: str) -> bool:
    return column_name in {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def create_table_if_missing(table_name: str, *columns: sa.Column) -> None:
    if not has_table(table_name):
        op.create_table(table_name, *columns)


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if has_table(table_name) and not has_column(table_name, column.name):
        op.add_column(table_name, column)


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


def updated_at() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)


def tenant_id_column() -> sa.Column:
    return sa.Column(
        "tenant_id",
        sa.String(length=80),
        nullable=False,
        server_default="default",
    )


def upgrade() -> None:
    scoped_tables = [
        "dataset_assets",
        "model_artifacts",
        "model_cards",
        "deployments",
        "prompt_templates",
        "prompt_cards",
        "evaluation_runs",
        "approvals",
        "audit_events",
        "prediction_events",
        "model_error_events",
        "drift_snapshots",
    ]
    for table_name in scoped_tables:
        add_column_if_missing(table_name, tenant_id_column())
        create_indexes(table_name, ["tenant_id"])

    create_table_if_missing(
        "workflow_runs",
        standard_id(),
        tenant_id_column(),
        sa.Column("workflow_type", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("current_step", sa.String(length=120), nullable=False),
        sa.Column("requested_by", sa.String(length=160), nullable=False),
        sa.Column("assigned_reviewer", sa.String(length=160), nullable=True),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("autonomous_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("steps_json", sa.JSON(), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("planner_state_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_planner_run_at", sa.DateTime(timezone=True), nullable=True),
        created_at(),
        updated_at(),
    )
    for column in [
        sa.Column("autonomous_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("planner_state_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_planner_run_at", sa.DateTime(timezone=True), nullable=True),
    ]:
        add_column_if_missing("workflow_runs", column)
    create_indexes(
        "workflow_runs",
        [
            "tenant_id",
            "workflow_type",
            "target_type",
            "target_id",
            "status",
            "current_step",
            "autonomous_mode",
            "next_run_at",
        ],
    )

    create_table_if_missing(
        "review_queue_items",
        standard_id(),
        tenant_id_column(),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=True),
        sa.Column("queue_name", sa.String(length=120), nullable=False),
        sa.Column("review_type", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("assigned_to", sa.String(length=160), nullable=True),
        sa.Column("decision", sa.String(length=80), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        created_at(),
        updated_at(),
    )
    create_indexes(
        "review_queue_items",
        [
            "tenant_id",
            "workflow_run_id",
            "case_id",
            "queue_name",
            "review_type",
            "priority",
            "status",
            "assigned_to",
            "decision",
        ],
    )

    create_table_if_missing(
        "payment_integrity_cases",
        standard_id(),
        tenant_id_column(),
        sa.Column("claim_id_synthetic", sa.String(length=120), nullable=False),
        sa.Column("member_id_synthetic", sa.String(length=120), nullable=False),
        sa.Column("provider_id_synthetic", sa.String(length=120), nullable=False),
        sa.Column("policy_doc_id", sa.String(length=160), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("queue_status", sa.String(length=80), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("risk_band", sa.String(length=40), nullable=True),
        sa.Column("automation_decision", sa.String(length=120), nullable=False),
        sa.Column("final_decision", sa.String(length=120), nullable=True),
        sa.Column("assigned_reviewer", sa.String(length=160), nullable=True),
        sa.Column("findings_json", sa.JSON(), nullable=False),
        sa.Column("source_ids_json", sa.JSON(), nullable=False),
        sa.Column("last_action", sa.String(length=160), nullable=False),
        created_at(),
        updated_at(),
    )
    create_indexes(
        "payment_integrity_cases",
        [
            "tenant_id",
            "claim_id_synthetic",
            "member_id_synthetic",
            "provider_id_synthetic",
            "policy_doc_id",
            "workflow_run_id",
            "status",
            "queue_status",
            "risk_band",
            "automation_decision",
            "final_decision",
        ],
    )


def downgrade() -> None:
    for table_name in [
        "payment_integrity_cases",
        "review_queue_items",
        "workflow_runs",
    ]:
        if has_table(table_name):
            op.drop_table(table_name)
