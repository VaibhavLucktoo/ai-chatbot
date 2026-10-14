"""Assistant configuration snapshots in telemetry.

Revision ID: a96c75bee8c0
Revises: f85d64add7bf
"""
from alembic import op
import sqlalchemy as sa

revision = "a96c75bee8c0"
down_revision = "f85d64add7bf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, type_ in (
        ("assistant_id", sa.Uuid()), ("assistant_name", sa.String(100)),
        ("assistant_revision", sa.Integer()), ("connection_id", sa.Uuid()),
        ("connection_revision", sa.Integer()), ("configured_provider", sa.String(16)),
        ("configured_model", sa.String(200)),
    ):
        op.add_column("chat_metrics", sa.Column(name, type_, nullable=True))
    op.create_index("ix_chat_metrics_assistant_started_at", "chat_metrics", ["assistant_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_metrics_assistant_started_at", table_name="chat_metrics")
    for name in ("configured_model", "configured_provider", "connection_revision", "connection_id",
                 "assistant_revision", "assistant_name", "assistant_id"):
        op.drop_column("chat_metrics", name)
