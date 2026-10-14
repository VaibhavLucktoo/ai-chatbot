"""Persist content-free chat and per-call metrics.

Revision ID: e74b53fcc6ae
Revises: d63a42fbb5fd
"""
from alembic import op
import sqlalchemy as sa

revision = "e74b53fcc6ae"
down_revision = "d63a42fbb5fd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("chat_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoint", sa.String(32), nullable=False),
        sa.Column("workflow_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(16), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("intent", sa.String(24), nullable=True),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("graph_ms", sa.Float(), nullable=True),
        sa.Column("retrieval_performed", sa.Boolean(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("stage_timings_ms", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chat_metrics"),
    )
    op.create_index("ix_chat_metrics_started_at", "chat_metrics", ["started_at"])
    op.create_table("model_call_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("provider", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("provider_requested", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("queue_ms", sa.Float(), nullable=True),
        sa.Column("provider_ms", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 10), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["chat_metrics.id"], name="fk_model_call_metrics_request_id_chat_metrics", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_model_call_metrics"),
    )
    op.create_index("ix_model_call_metrics_request_id", "model_call_metrics", ["request_id"])


def downgrade():
    op.drop_table("model_call_metrics")
    op.drop_table("chat_metrics")
