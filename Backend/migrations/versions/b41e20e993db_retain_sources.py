"""Retain source PDFs and processing provenance for recovery and reindexing."""
from alembic import op
import sqlalchemy as sa

revision = "b41e20e993db"
down_revision = "a30d19d882ca"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("original_pdf", sa.LargeBinary(), nullable=True))
    op.add_column("documents", sa.Column("processing_metadata", sa.JSON(), nullable=True))
    op.add_column("documents", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("documents", "active")
    op.drop_column("documents", "processing_metadata")
    op.drop_column("documents", "original_pdf")
