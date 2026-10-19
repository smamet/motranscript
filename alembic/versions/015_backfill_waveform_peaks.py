"""Backfill peaks.json next to existing source WAVs for WaveSurfer.

Revision ID: 015
Revises: 014
Create Date: 2026-09-09
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    from apps.annotator.pipeline.waveform_peaks import ensure_waveform_peaks

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, audio_path FROM sources WHERE audio_path IS NOT NULL")
    ).fetchall()
    for row in rows:
        wav = Path(row.audio_path)
        try:
            result = ensure_waveform_peaks(wav)
            if result is None:
                logger.warning("peaks backfill skip source=%s missing wav=%s", row.id, wav)
            else:
                logger.info("peaks backfill ok source=%s path=%s", row.id, result)
        except Exception as exc:  # noqa: BLE001 — do not fail deploy on one bad file
            logger.warning("peaks backfill failed source=%s path=%s: %s", row.id, wav, exc)


def downgrade() -> None:
    # Keep peaks.json files; safe to leave on disk
    pass
