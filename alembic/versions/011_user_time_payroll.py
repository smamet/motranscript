"""Add hourly_rate_mur and user_time_events ledger; backfill Done/Validated credits.

Revision ID: 011
Revises: 010
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "hourly_rate_mur",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
    )

    kind = sa.Enum("credit", "reverse", "reset", "rollback", name="usertimeeventkind")
    bucket = sa.Enum("done", "validated", name="usertimebucket")
    kind.create(op.get_bind(), checkfirst=True)
    bucket.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_time_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", kind, nullable=False),
        sa.Column("bucket", bucket, nullable=True),
        sa.Column("audio_sec", sa.Float(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("related_event_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["related_event_id"], ["user_time_events.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_time_events_user_id", "user_time_events", ["user_id"])
    op.create_index("ix_user_time_events_source_id", "user_time_events", ["source_id"])

    # Backfill: done → Done credit; validated → Validated credit (match reviewed_by email)
    conn = op.get_bind()
    users = {
        row.email.lower(): row.id
        for row in conn.execute(sa.text("SELECT id, email FROM users")).fetchall()
    }
    rows = conn.execute(
        sa.text(
            "SELECT id, duration_sec, review_status, reviewed_by "
            "FROM sources WHERE review_status IN ('done', 'validated') "
            "AND reviewed_by IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        email = (row.reviewed_by or "").strip().lower()
        user_id = users.get(email)
        if not user_id:
            continue
        duration = float(row.duration_sec or 0.0)
        if duration <= 0:
            continue
        bucket_val = "done" if row.review_status == "done" else "validated"
        conn.execute(
            sa.text(
                "INSERT INTO user_time_events "
                "(user_id, kind, bucket, audio_sec, source_id, created_by_user_id) "
                "VALUES (:user_id, 'credit', :bucket, :audio_sec, :source_id, :user_id)"
            ),
            {
                "user_id": user_id,
                "bucket": bucket_val,
                "audio_sec": duration,
                "source_id": row.id,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_user_time_events_source_id", table_name="user_time_events")
    op.drop_index("ix_user_time_events_user_id", table_name="user_time_events")
    op.drop_table("user_time_events")
    sa.Enum(name="usertimeeventkind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="usertimebucket").drop(op.get_bind(), checkfirst=True)
    op.drop_column("users", "hourly_rate_mur")
