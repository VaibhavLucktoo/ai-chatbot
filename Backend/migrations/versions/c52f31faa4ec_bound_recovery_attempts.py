"""Bound automatic recovery of repeatedly interrupted jobs."""
from alembic import op
import sqlalchemy as sa

revision = "c52f31faa4ec"
down_revision = "b41e20e993db"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("ingestion_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("documents", "ingestion_attempts")
