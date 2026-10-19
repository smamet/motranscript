"""Correct source assignment from payroll ledger (not reviewed_by admin).

Revision ID: 014
Revises: 013
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _unmatched_credit_user(conn, source_id: int) -> int | None:
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


def upgrade() -> None:
    conn = op.get_bind()
    users = {
        row.email.lower(): row.id
        for row in conn.execute(sa.text("SELECT id, email FROM users")).fetchall()
    }
    rows = conn.execute(
        sa.text(
            "SELECT id, reviewed_by, review_status, assigned_to_user_id FROM sources "
            "WHERE review_status IN ('done', 'validated')"
        )
    ).fetchall()
    for row in rows:
        uid = _unmatched_credit_user(conn, row.id)
        if uid is None:
            # Keep existing assign if set; else reviewed_by only for done (operator click)
            if row.assigned_to_user_id:
                continue
            if row.review_status == "done":
                email = (row.reviewed_by or "").strip().lower()
                uid = users.get(email)
        if uid and uid != row.assigned_to_user_id:
            conn.execute(
                sa.text(
                    "UPDATE sources SET assigned_to_user_id = :uid WHERE id = :sid"
                ),
                {"uid": uid, "sid": row.id},
            )


def downgrade() -> None:
    # Irreversible data correction
    pass
