"""Add bounded, capability-protected conversation memory.

Revision ID: d63a42fbb5fd
Revises: c52f31faa4ec
"""
from alembic import op
import sqlalchemy as sa

revision = "d63a42fbb5fd"
down_revision = "c52f31faa4ec"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_key_hash", sa.String(64), nullable=False),
        sa.Column("history", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_chat_conversations"),
    )
    op.create_index("ix_chat_conversations_expires_at", "chat_conversations", ["expires_at"])


def downgrade():
    op.drop_index("ix_chat_conversations_expires_at", table_name="chat_conversations")
    op.drop_table("chat_conversations")
