"""Evidence-backed document metadata and semantic summaries."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

revision = "c18f86cff0e2"
down_revision = "b07e75bee9d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_metadata",
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(384), nullable=False),
        sa.Column("embedding_space", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.CheckConstraint("embedding_space = 'fastembed:bge-small-en-v1.5:384:l2:v1'", name="supported_embedding_space"),
    )


def downgrade():
    op.drop_table("document_metadata")
