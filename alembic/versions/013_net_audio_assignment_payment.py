"""Net audio payroll, source assignment, payment_periods.

Revision ID: 013
Revises: 012
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_sources_assigned_to_user_id", "sources", ["assigned_to_user_id"]
    )
    op.create_foreign_key(
        "fk_sources_assigned_to_user_id",
        "sources",
        "users",
        ["assigned_to_user_id"],
        ["id"],
    )

    op.create_table(
        "payment_periods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reset_event_id", sa.Integer(), nullable=False),
        sa.Column("audio_sec", sa.Float(), nullable=False),
        sa.Column("hourly_rate_mur", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_mur", sa.Numeric(12, 2), nullable=False),
        sa.Column("period_started_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reset_event_id"], ["user_time_events.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reset_event_id"),
    )
    op.create_index("ix_payment_periods_user_id", "payment_periods", ["user_id"])

    conn = op.get_bind()

    # Backfill assignment from unmatched Done/Validated ledger credit (not reviewed_by —
    # that is often the validating admin). Fall back to reviewed_by only if no credit.
    users = {
        row.email.lower(): row.id
        for row in conn.execute(sa.text("SELECT id, email FROM users")).fetchall()
    }

    def _unmatched_credit_user(source_id: int) -> int | None:
        events = conn.execute(
            sa.text(
                "SELECT user_id, kind, bucket FROM user_time_events "
                "WHERE source_id = :sid AND kind IN ('credit', 'reverse') "
                "AND bucket IN ('done', 'validated') "
                "ORDER BY created_at ASC, id ASC"
            ),
            {"sid": source_id},
        ).fetchall()
        stacks: dict[str, list[int]] = {"done": [], "validated": []}
        for e in events:
            bucket = e.bucket
            if e.kind == "credit":
                stacks[bucket].append(e.user_id)
            elif e.kind == "reverse" and stacks[bucket]:
                stacks[bucket].pop()
        if stacks["validated"]:
            return stacks["validated"][-1]
        if stacks["done"]:
            return stacks["done"][-1]
        return None

    rows = conn.execute(
        sa.text(
            "SELECT id, reviewed_by, review_status FROM sources "
            "WHERE review_status IN ('done', 'validated')"
        )
    ).fetchall()
    for row in rows:
        uid = _unmatched_credit_user(row.id)
        if uid is None:
            email = (row.reviewed_by or "").strip().lower()
            uid = users.get(email)
        if uid:
            conn.execute(
                sa.text(
                    "UPDATE sources SET assigned_to_user_id = :uid WHERE id = :sid"
                ),
                {"uid": uid, "sid": row.id},
            )

    # Recalculate credit/reverse audio_sec to net (non-ignored with text)
    events = conn.execute(
        sa.text(
            "SELECT id, source_id FROM user_time_events "
            "WHERE kind IN ('credit', 'reverse') AND source_id IS NOT NULL"
        )
    ).fetchall()
    for ev in events:
        net = conn.execute(
            sa.text(
                "SELECT COALESCE(SUM(end_sec - start_sec), 0) FROM segments "
                "WHERE source_id = :sid "
                "AND status != 'ignored' "
                "AND TRIM(COALESCE(text_corrected, text_raw, '')) != ''"
            ),
            {"sid": ev.source_id},
        ).scalar()
        conn.execute(
            sa.text("UPDATE user_time_events SET audio_sec = :sec WHERE id = :eid"),
            {"sec": float(net or 0.0), "eid": ev.id},
        )

    # Backfill PaymentPeriod for historical resets (rate = current user rate)
    resets = conn.execute(
        sa.text(
            "SELECT e.id, e.user_id, e.audio_sec, e.created_at, e.created_by_user_id, "
            "u.hourly_rate_mur "
            "FROM user_time_events e "
            "JOIN users u ON u.id = e.user_id "
            "WHERE e.kind = 'reset' "
            "ORDER BY e.created_at ASC, e.id ASC"
        )
    ).fetchall()
    for r in resets:
        rate = float(r.hourly_rate_mur or 0)
        sec = float(r.audio_sec or 0)
        amount = round(sec / 3600.0 * rate, 2)
        conn.execute(
            sa.text(
                "INSERT INTO payment_periods "
                "(user_id, reset_event_id, audio_sec, hourly_rate_mur, amount_mur, "
                "period_started_at, closed_at, created_by_user_id, note) "
                "VALUES (:uid, :eid, :sec, :rate, :amount, NULL, :closed, :by, 'backfill')"
            ),
            {
                "uid": r.user_id,
                "eid": r.id,
                "sec": sec,
                "rate": rate,
                "amount": amount,
                "closed": r.created_at,
                "by": r.created_by_user_id,
            },
        )

    # Mark periods whose reset was later rolled back
    rollbacks = conn.execute(
        sa.text(
            "SELECT related_event_id, created_at FROM user_time_events "
            "WHERE kind = 'rollback' AND related_event_id IS NOT NULL"
        )
    ).fetchall()
    for rb in rollbacks:
        conn.execute(
            sa.text(
                "UPDATE payment_periods SET rolled_back_at = :at "
                "WHERE reset_event_id = :eid AND rolled_back_at IS NULL"
            ),
            {"at": rb.created_at, "eid": rb.related_event_id},
        )


def downgrade() -> None:
    op.drop_index("ix_payment_periods_user_id", table_name="payment_periods")
    op.drop_table("payment_periods")
    op.drop_constraint("fk_sources_assigned_to_user_id", "sources", type_="foreignkey")
    op.drop_index("ix_sources_assigned_to_user_id", table_name="sources")
    op.drop_column("sources", "assigned_to_user_id")
