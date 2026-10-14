"""Per-assistant website widgets and private visitor sessions."""
from alembic import op
import sqlalchemy as sa

revision = "b07e75bee9d1"
down_revision = "a96c75bee8c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("website_widgets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assistant_id", sa.Uuid(), sa.ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("title", sa.String(100), nullable=False), sa.Column("greeting", sa.String(500), nullable=False),
        sa.Column("color", sa.String(7), nullable=False), sa.Column("position", sa.String(5), nullable=False),
        sa.Column("allowed_origins", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("requests_per_day", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("usage", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("assistant_id"), sa.CheckConstraint("revision > 0", name="positive_revision"),
        sa.CheckConstraint("requests_per_minute BETWEEN 1 AND 120", name="minute_limit"),
        sa.CheckConstraint("requests_per_day BETWEEN 1 AND 10000", name="day_limit"))
    op.create_table("widget_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("widget_id", sa.Uuid(), sa.ForeignKey("website_widgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("widget_revision", sa.Integer(), nullable=False), sa.Column("parent_origin", sa.String(300), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("allowed_chunks", sa.JSON(), nullable=False, server_default="[]"))
    op.create_index("ix_widget_sessions_expires_at", "widget_sessions", ["expires_at"])
    op.create_index("ix_widget_sessions_widget_id", "widget_sessions", ["widget_id"])


def downgrade():
    op.drop_table("widget_sessions")
    op.drop_table("website_widgets")
