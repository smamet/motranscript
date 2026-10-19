"""Cleanup tables + seed lexicon_entries from file lexicon.

Revision ID: 016
Revises: 015
Create Date: 2026-09-10
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop leftovers from a failed partial run (MySQL DDL auto-commits).
    op.execute(sa.text("DROP TABLE IF EXISTS lexicon_entries"))
    op.execute(sa.text("DROP TABLE IF EXISTS text_revisions"))
    op.execute(sa.text("DROP TABLE IF EXISTS segment_audit_dismissals"))

    lexicon_kind = sa.Enum("official", "alias", "skip", name="lexiconkind")
    lexicon_origin = sa.Enum("pdf", "manual", "corpus", name="lexiconorigin")
    revision_kind = sa.Enum("replace", "rollback", name="textrevisionkind")
    lexicon_kind.create(op.get_bind(), checkfirst=True)
    lexicon_origin.create(op.get_bind(), checkfirst=True)
    revision_kind.create(op.get_bind(), checkfirst=True)

    # Reuse existing segmentstatus enum for status_before
    segment_status = sa.Enum(
        "raw",
        "corrected",
        "validated",
        "ignored",
        name="segmentstatus",
        create_type=False,
    )

    op.create_table(
        "segment_audit_dismissals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("segment_id", "rule_id", name="uq_segment_audit_dismissal"),
    )
    op.create_index(
        "ix_segment_audit_dismissals_segment_id",
        "segment_audit_dismissals",
        ["segment_id"],
    )

    op.create_table(
        "text_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("text_before", sa.Text(), nullable=False),
        sa.Column("text_after", sa.Text(), nullable=False),
        sa.Column("status_before", segment_status, nullable=False),
        sa.Column("kind", revision_kind, nullable=False),
        sa.Column("query", sa.String(length=512), nullable=True),
        sa.Column("replacement", sa.String(length=512), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_text_revisions_batch_id", "text_revisions", ["batch_id"])
    op.create_index("ix_text_revisions_segment_id", "text_revisions", ["segment_id"])

    op.create_table(
        "lexicon_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("word", sa.String(length=128), nullable=False),
        sa.Column("kind", lexicon_kind, nullable=False),
        sa.Column("canonical", sa.String(length=128), nullable=True),
        sa.Column("origin", lexicon_origin, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word"),
    )
    op.create_index("ix_lexicon_entries_word", "lexicon_entries", ["word"])

    _seed_lexicon()


def _seed_lexicon() -> None:
    from normalizer.lexicon import DEFAULT_SKIP_WORDS, LEXICON_DIR, parse_aliases_text, parse_words_text
    from normalizer.phonetic import strip_accents

    conn = op.get_bind()
    rows: list[dict] = []
    seen: set[str] = set()

    def add(word: str, kind: str, canonical: str | None, origin: str) -> None:
        # MySQL utf8mb4_unicode_ci treats accented/unaccented forms as equal.
        key = strip_accents(word.lower())
        if not key or key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "word": key,
                "kind": kind,
                "canonical": strip_accents(canonical.lower()) if canonical else None,
                "origin": origin,
                "note": None,
            }
        )

    words_file = LEXICON_DIR / "words.txt"
    if words_file.exists():
        for word in sorted(parse_words_text(words_file.read_text(encoding="utf-8"))):
            add(word, "official", None, "pdf")

    aliases_file = LEXICON_DIR / "asr_aliases.txt"
    if aliases_file.exists():
        for src, dst in parse_aliases_text(aliases_file.read_text(encoding="utf-8")).items():
            add(dst, "official", None, "manual")
            add(src, "alias", dst, "manual")

    for word in sorted(DEFAULT_SKIP_WORDS):
        add(word, "skip", None, "manual")

    if not rows:
        return

    insert = sa.text(
        "INSERT INTO lexicon_entries (word, kind, canonical, origin, note) "
        "VALUES (:word, :kind, :canonical, :origin, :note)"
    )
    chunk = 500
    for i in range(0, len(rows), chunk):
        conn.execute(insert, rows[i : i + chunk])


def downgrade() -> None:
    op.drop_index("ix_lexicon_entries_word", table_name="lexicon_entries")
    op.drop_table("lexicon_entries")
    op.drop_index("ix_text_revisions_segment_id", table_name="text_revisions")
    op.drop_index("ix_text_revisions_batch_id", table_name="text_revisions")
    op.drop_table("text_revisions")
    op.drop_index(
        "ix_segment_audit_dismissals_segment_id",
        table_name="segment_audit_dismissals",
    )
    op.drop_table("segment_audit_dismissals")

    sa.Enum(name="lexiconkind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="lexiconorigin").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="textrevisionkind").drop(op.get_bind(), checkfirst=True)
