"""Add categories and downloaded source status for catalog→ASR promote flow.

Revision ID: 009
Revises: 008
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LICENSE_TO_SLUG = {
    "Lir Ekril Kreol Morisien": "lir-ekril",
    "Komiko": "komiko",
    "Tempo La So": "tempo-la-so",
}


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.bulk_insert(
        sa.table(
            "categories",
            sa.column("slug", sa.String),
            sa.column("label", sa.String),
        ),
        [
            {"slug": "lir-ekril", "label": "Lir Ekril"},
            {"slug": "komiko", "label": "Komiko"},
            {"slug": "tempo-la-so", "label": "Tempo La So"},
        ],
    )

    op.add_column("sources", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_sources_category_id",
        "sources",
        "categories",
        ["category_id"],
        ["id"],
    )

    # Extend MySQL ENUM sourcestatus with downloaded
    op.execute(
        "ALTER TABLE sources MODIFY COLUMN status "
        "ENUM('pending','processing','ready','failed','cancelled','downloaded') "
        "NOT NULL"
    )

    conn = op.get_bind()
    cats = {
        row.slug: row.id
        for row in conn.execute(sa.text("SELECT id, slug FROM categories")).fetchall()
    }
    for notes, slug in _LICENSE_TO_SLUG.items():
        cat_id = cats.get(slug)
        if not cat_id:
            continue
        conn.execute(
            sa.text(
                "UPDATE sources SET category_id = :cid WHERE license_notes = :notes"
            ),
            {"cid": cat_id, "notes": notes},
        )

    # Sources with audio but no completed ASR → catalog (downloaded)
    completed_asr = {
        row.source_id
        for row in conn.execute(
            sa.text(
                "SELECT DISTINCT source_id FROM jobs "
                "WHERE job_type = 'transcribe' AND status = 'completed'"
            )
        ).fetchall()
    }
    catalog_ids: list[int] = []
    for row in conn.execute(
        sa.text(
            "SELECT id, audio_path, status FROM sources "
            "WHERE audio_path IS NOT NULL AND audio_path != ''"
        )
    ).fetchall():
        if row.id in completed_asr:
            continue
        if str(row.status).split(".")[-1] == "ready":
            continue
        catalog_ids.append(int(row.id))

    if catalog_ids:
        # Cancel leftover transcribe jobs for catalog sources
        conn.execute(
            sa.text(
                "UPDATE jobs SET status = 'cancelled', "
                "phase = 'Cancelled — awaiting promote to To do' "
                "WHERE job_type = 'transcribe' "
                "AND status IN ('pending', 'failed', 'running') "
                "AND source_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": catalog_ids},
        )
        conn.execute(
            sa.text(
                "UPDATE sources SET status = 'downloaded' WHERE id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": catalog_ids},
        )


def downgrade() -> None:
    op.execute(
        "UPDATE sources SET status = 'pending' WHERE status = 'downloaded'"
    )
    op.execute(
        "ALTER TABLE sources MODIFY COLUMN status "
        "ENUM('pending','processing','ready','failed','cancelled') "
        "NOT NULL"
    )
    op.drop_constraint("fk_sources_category_id", "sources", type_="foreignkey")
    op.drop_column("sources", "category_id")
    op.drop_table("categories")
