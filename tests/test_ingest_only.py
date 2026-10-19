"""Tests for ingest-only enqueue and downloaded status transitions."""

from apps.annotator.api.services import _enqueue_pipeline_jobs
from apps.annotator.db.models import Job, JobType, Source, SourceStatus, SourceType


class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def test_enqueue_pipeline_jobs_ingest_only():
    db = _FakeDB()
    source = Source(id=1, source_type=SourceType.youtube, status=SourceStatus.pending)
    source.id = 42
    _enqueue_pipeline_jobs(db, source)
    assert len(db.added) == 1
    job = db.added[0]
    assert isinstance(job, Job)
    assert job.job_type == JobType.ingest
    assert job.source_id == 42
