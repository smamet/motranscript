"""Add ignored to segment status enum.

Revision ID: 010
Revises: 009
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE segments MODIFY COLUMN status "
        "ENUM('raw','corrected','validated','ignored') "
        "NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE segments SET status = 'raw' WHERE status = 'ignored'"
    )
    op.execute(
        "ALTER TABLE segments MODIFY COLUMN status "
        "ENUM('raw','corrected','validated') "
        "NOT NULL"
    )
