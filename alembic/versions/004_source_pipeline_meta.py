"""Add pipeline_meta JSON on sources for diarization diagnostics."""

from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("pipeline_meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "pipeline_meta")
