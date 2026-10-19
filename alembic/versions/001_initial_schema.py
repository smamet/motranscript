"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_type", sa.Enum("youtube", "upload", name="sourcetype"), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("original_filename", sa.String(length=512), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("license_notes", sa.Text(), nullable=True),
        sa.Column("audio_path", sa.String(length=1024), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "ready", "failed", name="sourcestatus"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("hf_repo", sa.String(length=512), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.Enum("ingest", "transcribe", name="jobtype"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="jobstatus"),
            nullable=False,
        ),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_source_id", "jobs", ["source_id"])
    op.create_table(
        "speakers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_speakers_source_id", "speakers", ["source_id"])
    op.create_table(
        "segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("audio_path", sa.String(length=1024), nullable=True),
        sa.Column("text_raw", sa.Text(), nullable=True),
        sa.Column("text_corrected", sa.Text(), nullable=True),
        sa.Column(
            "lang",
            sa.Enum("kreol", "fr", "en", "mix", name="segmentlang"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("raw", "corrected", "validated", name="segmentstatus"),
            nullable=False,
        ),
        sa.Column("model_version_used", sa.String(length=256), nullable=True),
        sa.Column("annotator", sa.String(length=128), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["speaker_id"], ["speakers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_segments_source_id", "segments", ["source_id"])
    op.create_index("ix_segments_speaker_id", "segments", ["speaker_id"])


def downgrade() -> None:
    op.drop_index("ix_segments_speaker_id", table_name="segments")
    op.drop_index("ix_segments_source_id", table_name="segments")
    op.drop_table("segments")
    op.drop_index("ix_speakers_source_id", table_name="speakers")
    op.drop_table("speakers")
    op.drop_index("ix_jobs_source_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("model_versions")
    op.drop_table("sources")
