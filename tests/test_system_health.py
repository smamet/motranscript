from apps.annotator.api.system_health import collect_global_alerts, collect_source_alerts
from apps.annotator.db.models import Job, JobStatus, JobType, Source, SourceStatus


def test_global_alerts_hf_token_missing(monkeypatch):
    from apps.annotator.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_diarization", True)
    monkeypatch.setattr(settings, "hf_token", "")

    alerts = collect_global_alerts(worker_alive=True)
    ids = {a["id"] for a in alerts}
    assert "hf_token_missing" in ids


def test_global_alerts_transcribe_paused(monkeypatch):
    from apps.annotator.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "transcribe_enabled", False)
    alerts = collect_global_alerts(worker_alive=True)
    assert any(a["id"] == "transcribe_paused" for a in alerts)
    source = Source(id=1, status=SourceStatus.ready, pipeline_meta={"diarization_status": "failed", "diarization_error": "boom"})
    alerts = collect_source_alerts(source, [], {})
    assert any(a["id"] == "diarization_failed" for a in alerts)


def test_source_alerts_skip_cascade_transcribe_error():
    source = Source(id=1, status=SourceStatus.failed, error="Source not ready for transcription")
    ingest = Job(
        source_id=1,
        job_type=JobType.ingest,
        status=JobStatus.failed,
        error="YouTube download failed: This video is not available",
    )
    transcribe = Job(
        source_id=1,
        job_type=JobType.transcribe,
        status=JobStatus.failed,
        error="Source not ready for transcription",
    )
    alerts = collect_source_alerts(source, [ingest, transcribe], {})
    ids = {a["id"] for a in alerts}
    assert "job_ingest_failed" in ids
    assert "job_transcribe_failed" not in ids
    assert "source_error" not in ids
