"""Add review workflow fields on sources and segments.

Revision ID: 007
Revises: 006
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    review_status = sa.Enum("todo", "done", "validated", name="reviewstatus")
    review_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "sources",
        sa.Column(
            "review_status",
            review_status,
            nullable=False,
            server_default="todo",
        ),
    )
    op.add_column("sources", sa.Column("reviewed_by", sa.String(length=256), nullable=True))
    op.add_column("sources", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("sources", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("segments", sa.Column("review_comment", sa.Text(), nullable=True))
    op.add_column(
        "segments",
        sa.Column("review_comment_by", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("segments", "review_comment_by")
    op.drop_column("segments", "review_comment")
    op.drop_column("sources", "review_note")
    op.drop_column("sources", "reviewed_at")
    op.drop_column("sources", "reviewed_by")
    op.drop_column("sources", "review_status")
    sa.Enum(name="reviewstatus").drop(op.get_bind(), checkfirst=True)
