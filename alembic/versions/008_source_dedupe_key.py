"""Add unique source dedupe_key for YouTube IDs and upload hashes.

Revision ID: 008
Revises: 007
Create Date: 2026-09-03
"""

import re
from typing import Sequence, Union
from urllib.parse import parse_qs, urlparse

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _youtube_key(url: str) -> str | None:
    raw = url.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    video: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/", 1)[0]
        video = candidate if _YT_ID.match(candidate) else None
    elif "youtube" in host:
        video = parse_qs(parsed.query).get("v", [""])[0]
        if not _YT_ID.match(video or ""):
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
                video = parts[1] if _YT_ID.match(parts[1]) else None
            else:
                video = None
    return f"yt:{video}" if video else None


def upgrade() -> None:
    op.add_column("sources", sa.Column("dedupe_key", sa.String(length=80), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, source_type, source_url FROM sources")).fetchall()
    seen: set[str] = set()
    for row in rows:
        if str(row.source_type).split(".")[-1] != "youtube" or not row.source_url:
            continue
        key = _youtube_key(row.source_url)
        if not key or key in seen:
            continue
        seen.add(key)
        conn.execute(
            sa.text("UPDATE sources SET dedupe_key = :key WHERE id = :id"),
            {"key": key, "id": row.id},
        )
    op.create_index("uq_sources_dedupe_key", "sources", ["dedupe_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_sources_dedupe_key", table_name="sources")
    op.drop_column("sources", "dedupe_key")
