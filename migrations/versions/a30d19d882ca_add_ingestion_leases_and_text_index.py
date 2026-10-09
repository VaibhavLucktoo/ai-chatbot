"""Add recoverable ingestion ownership and English full-text index."""

from alembic import op
import sqlalchemy as sa

revision = "a30d19d882ca"
down_revision = "7f7483ec3680"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("attempt_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_document_chunks_content_english", "document_chunks",
                    [sa.text("to_tsvector('english'::regconfig, content)")], postgresql_using="gin")


def downgrade():
    op.drop_index("ix_document_chunks_content_english", table_name="document_chunks")
    op.drop_column("documents", "lease_expires_at")
    op.drop_column("documents", "attempt_id")
