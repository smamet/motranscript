"""Add job.phase and cancelled statuses."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("phase", sa.String(length=256), nullable=True))
    op.execute(
        "ALTER TABLE jobs MODIFY status "
        "ENUM('pending', 'running', 'completed', 'failed', 'cancelled') NOT NULL"
    )
    op.execute(
        "ALTER TABLE sources MODIFY status "
        "ENUM('pending', 'processing', 'ready', 'failed', 'cancelled') NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("jobs", "phase")
    op.execute(
        "ALTER TABLE jobs MODIFY status "
        "ENUM('pending', 'running', 'completed', 'failed') NOT NULL"
    )
    op.execute(
        "ALTER TABLE sources MODIFY status "
        "ENUM('pending', 'processing', 'ready', 'failed') NOT NULL"
    )
