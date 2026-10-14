"""Add provider connections, assistants, document scope and conversation namespace."""

from alembic import op
import sqlalchemy as sa

revision = "f85d64add7bf"
down_revision = "e74b53fcc6ae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("provider IN ('groq', 'gemini')", name=op.f("ck_provider_connections_supported_provider")),
        sa.CheckConstraint("revision > 0", name=op.f("ck_provider_connections_positive_revision")),
        sa.PrimaryKeyConstraint("id", name="pk_provider_connections"),
    )
    op.create_table(
        "assistants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), server_default="", nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), server_default="2048", nullable=False),
        sa.Column("context_window_tokens", sa.Integer(), server_default="32768", nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0", nullable=False),
        sa.Column("timeout_seconds", sa.Float(), server_default="120", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["provider_connections.id"], ondelete="RESTRICT",
                                name="fk_assistants_connection_id_provider_connections"),
        sa.CheckConstraint("revision > 0", name=op.f("ck_assistants_positive_revision")),
        sa.CheckConstraint("max_output_tokens BETWEEN 64 AND 8192", name=op.f("ck_assistants_output_limit")),
        sa.CheckConstraint("context_window_tokens BETWEEN 4096 AND 1048576", name=op.f("ck_assistants_context_limit")),
        sa.CheckConstraint("context_window_tokens > max_output_tokens * 5 + 4560", name=op.f("ck_assistants_usable_context")),
        sa.CheckConstraint("temperature BETWEEN 0 AND 2", name=op.f("ck_assistants_temperature_limit")),
        sa.CheckConstraint("timeout_seconds > 0 AND timeout_seconds <= 600", name=op.f("ck_assistants_timeout_limit")),
        sa.PrimaryKeyConstraint("id", name="pk_assistants"),
    )
    op.create_index("ix_assistants_connection_id", "assistants", ["connection_id"])
    op.create_table(
        "assistant_documents",
        sa.Column("assistant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["assistant_id"], ["assistants.id"], ondelete="CASCADE",
                                name="fk_assistant_documents_assistant_id_assistants"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE",
                                name="fk_assistant_documents_document_id_documents"),
        sa.PrimaryKeyConstraint("assistant_id", "document_id", name="pk_assistant_documents"),
    )
    op.create_index("ix_assistant_documents_document_id", "assistant_documents", ["document_id"])
    op.add_column("chat_conversations", sa.Column("assistant_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_conversations", "assistant_id")
    op.drop_table("assistant_documents")
    op.drop_table("assistants")
    op.drop_table("provider_connections")
