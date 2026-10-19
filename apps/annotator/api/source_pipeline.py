"""Pipeline phase labels and progress computation for the sources UI."""

from __future__ import annotations

from typing import Literal

from apps.annotator.db.models import Job, JobStatus, JobType, Source, SourceStatus, SourceType

PhaseStatus = Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]


class CancelledError(Exception):
    """Raised when a source was cancelled mid-job."""


def _job_by_type(jobs: list[Job], job_type: JobType) -> Job | None:
    return next((j for j in jobs if j.job_type == job_type), None)


def _phase_status_from_job(job: Job | None, *, skipped: bool = False) -> PhaseStatus:
    if skipped:
        return "skipped"
    if not job:
        return "pending"
    if job.status == JobStatus.completed:
        return "completed"
    if job.status == JobStatus.failed:
        return "failed"
    if job.status == JobStatus.cancelled:
        return "cancelled"
    if job.status == JobStatus.running:
        return "running"
    return "pending"


def build_pipeline_status(source: Source, jobs: list[Job], *, queue_position: int | None = None) -> dict:
    ingest = _job_by_type(jobs, JobType.ingest)
    transcribe = _job_by_type(jobs, JobType.transcribe)
    is_youtube = source.source_type == SourceType.youtube

    if source.status == SourceStatus.cancelled:
        return _pipeline(
            source,
            _cancelled_phases(is_youtube, ingest, transcribe),
            "Cancelled",
            0.0,
            queue_position=queue_position,
        )

    if source.status == SourceStatus.downloaded:
        phases = _ready_phases(is_youtube)
        # Mark ASR steps as skipped until promote
        for phase in phases:
            if phase["id"] in {"asr", "diarize", "segments"}:
                phase["status"] = "skipped"
                phase["detail"] = "Waiting in Downloaded — promote to To do to run ASR"
        return _pipeline(
            source,
            phases,
            "Downloaded — ready to promote",
            20.0 if is_youtube else 20.0,
            queue_position=None,
        )

    if source.status == SourceStatus.ready:
        phases = _ready_phases(is_youtube)
        return _pipeline(source, phases, "Ready for editing", 100.0, queue_position=None)

    if source.status == SourceStatus.failed:
        phases = _failed_phases(is_youtube, ingest, transcribe, source.error)
        progress = _estimate_progress(is_youtube, ingest, transcribe)
        label = transcribe.phase if transcribe and transcribe.phase else (ingest.phase if ingest else "Failed")
        return _pipeline(source, phases, label or "Failed", progress, source.error, queue_position)

    phases = _active_phases(is_youtube, ingest, transcribe)
    # Ingest-only (not yet promoted): hide ASR steps
    if not _transcribe_active(transcribe):
        for phase in phases:
            if phase["id"] in {"asr", "diarize", "segments"}:
                phase["status"] = "skipped"
                phase["detail"] = "ASR after promote to To do"
    progress = _estimate_progress(is_youtube, ingest, transcribe)
    label = _current_label(is_youtube, ingest, transcribe, queue_position)
    if not _transcribe_active(transcribe) and ingest and ingest.status == JobStatus.running:
        label = ingest.phase or "Downloading…"
    elif not _transcribe_active(transcribe) and ingest and ingest.status == JobStatus.completed:
        # Ingest finished; ASR waits for promote (even if status briefly stuck on processing)
        label = "Downloaded — ready to promote"
        progress = 20.0
    return _pipeline(source, phases, label, progress, source.error, queue_position)


def _transcribe_active(transcribe: Job | None) -> bool:
    if not transcribe:
        return False
    return transcribe.status in (
        JobStatus.pending,
        JobStatus.running,
        JobStatus.completed,
        JobStatus.failed,
    )


def _pipeline(
    source: Source,
    phases: list[dict],
    current_label: str,
    overall_progress: float,
    error: str | None = None,
    queue_position: int | None = None,
) -> dict:
    can_cancel = source.status in (SourceStatus.pending, SourceStatus.processing)
    meta = source.pipeline_meta or {}
    return {
        "overall_progress": round(min(100.0, max(0.0, overall_progress)), 1),
        "current_label": current_label,
        "phases": phases,
        "can_cancel": can_cancel,
        "can_delete": True,
        "error": error,
        "queue_position": queue_position,
        "restart_note": (
            "If the worker stops, pending steps resume automatically when you restart it. "
            "A step that was running may restart from the beginning."
        ),
        "diarization_status": meta.get("diarization_status"),
        "diarization_error": meta.get("diarization_error"),
        "speaker_count": meta.get("speaker_count"),
    }


def _current_label(
    is_youtube: bool,
    ingest: Job | None,
    transcribe: Job | None,
    queue_position: int | None,
) -> str:
    if queue_position is not None and queue_position >= 1:
        if transcribe and transcribe.status == JobStatus.pending and ingest and ingest.status == JobStatus.completed:
            return f"Waiting for worker — transcription queued (#{queue_position} in line)"
        if ingest and ingest.status == JobStatus.pending:
            return f"Waiting for worker — queued (#{queue_position} in line)"
    if transcribe and transcribe.status == JobStatus.running and transcribe.phase:
        return transcribe.phase
    if transcribe and transcribe.status == JobStatus.pending and ingest and ingest.status == JobStatus.completed:
        return "Queued for transcription"
    if ingest and ingest.status == JobStatus.running and ingest.phase:
        return ingest.phase
    if ingest and ingest.status == JobStatus.pending:
        return "Queued — waiting for worker"
    if ingest and ingest.status == JobStatus.completed and transcribe and transcribe.status == JobStatus.pending:
        return "Audio ready — queued for transcription"
    return "Processing…"


def _estimate_progress(is_youtube: bool, ingest: Job | None, transcribe: Job | None) -> float:
    """Ingest ≈ 20%, transcribe ≈ 80% of total pipeline."""
    ingest_weight = 20.0
    transcribe_weight = 80.0

    ingest_done = ingest and ingest.status == JobStatus.completed
    ingest_prog = 0.0
    if ingest:
        if ingest.status == JobStatus.completed:
            ingest_prog = 1.0
        elif ingest.status == JobStatus.running:
            ingest_prog = max(0.05, ingest.progress)

    transcribe_prog = 0.0
    if transcribe:
        if transcribe.status == JobStatus.completed:
            transcribe_prog = 1.0
        elif transcribe.status == JobStatus.running:
            transcribe_prog = max(0.05, transcribe.progress)

    if ingest_done:
        ingest_prog = 1.0

    return ingest_prog * ingest_weight + transcribe_prog * transcribe_weight


def _active_phases(is_youtube: bool, ingest: Job | None, transcribe: Job | None) -> list[dict]:
    phases: list[dict] = []

    if is_youtube:
        phases.append(_step("download", "Download from YouTube", ingest, sub_progress=(0.0, 0.5)))
        phases.append(_step("convert", "Convert to 16 kHz WAV", ingest, sub_progress=(0.5, 1.0)))
    else:
        phases.append(_step("upload", "Upload received", ingest, sub_progress=(0.0, 0.3)))
        phases.append(_step("convert", "Convert to 16 kHz WAV", ingest, sub_progress=(0.3, 1.0)))

    phases.extend(
        [
            _transcribe_substep("asr", "Load ASR model & transcribe", transcribe, 0.0, 0.5),
            _transcribe_substep("diarize", "Diarize & align (optional)", transcribe, 0.5, 0.85),
            _transcribe_substep("segments", "Build segments", transcribe, 0.85, 1.0),
        ]
    )
    return phases


def _step(
    step_id: str,
    label: str,
    job: Job | None,
    *,
    sub_progress: tuple[float, float],
) -> dict:
    lo, hi = sub_progress
    status = _phase_status_from_job(job)
    detail = None
    progress = None

    if job and job.status == JobStatus.running:
        p = job.progress
        if lo <= p <= hi or (p > 0 and status == "running"):
            # Map job progress into this sub-step when ingest is running
            span = hi - lo
            if span > 0 and p >= lo:
                progress = min(1.0, (p - lo) / span)
            status = "running"
            detail = job.phase
        elif p >= hi:
            status = "completed"
        elif p < lo and job.status == JobStatus.completed:
            status = "completed"
    elif job and job.status == JobStatus.completed:
        status = "completed"

    return {"id": step_id, "label": label, "status": status, "progress": progress, "detail": detail}


def _transcribe_substep(
    step_id: str,
    label: str,
    job: Job | None,
    lo: float,
    hi: float,
) -> dict:
    if not job:
        return {"id": step_id, "label": label, "status": "pending", "progress": None, "detail": None}

    ingest_pending = job.status == JobStatus.pending
    if ingest_pending:
        return {"id": step_id, "label": label, "status": "pending", "progress": None, "detail": None}

    if job.status == JobStatus.failed:
        return {"id": step_id, "label": label, "status": "failed", "progress": None, "detail": job.error}

    if job.status == JobStatus.cancelled:
        return {"id": step_id, "label": label, "status": "cancelled", "progress": None, "detail": None}

    if job.status == JobStatus.completed:
        return {"id": step_id, "label": label, "status": "completed", "progress": 1.0, "detail": None}

    p = job.progress
    status: PhaseStatus = "pending"
    progress = None
    detail = job.phase

    if job.status == JobStatus.running:
        if p >= hi:
            status = "completed"
            progress = 1.0
        elif p >= lo:
            status = "running"
            progress = (p - lo) / (hi - lo) if hi > lo else p
        elif p > 0 and step_id == "asr":
            status = "running"
            progress = p / lo if lo else p

    return {"id": step_id, "label": label, "status": status, "progress": progress, "detail": detail}


def _ready_phases(is_youtube: bool) -> list[dict]:
    base = ["download", "convert"] if is_youtube else ["upload", "convert"]
    return [
        {"id": s, "label": _label_for(s), "status": "completed", "progress": 1.0, "detail": None}
        for s in base
    ] + [
        {"id": s, "label": _label_for(s), "status": "completed", "progress": 1.0, "detail": None}
        for s in ("asr", "diarize", "segments")
    ]


def _cancelled_phases(is_youtube: bool, ingest: Job | None, transcribe: Job | None) -> list[dict]:
    phases = _active_phases(is_youtube, ingest, transcribe)
    cancelled_seen = False
    for phase in phases:
        if phase["status"] == "running" or (phase["status"] == "pending" and not cancelled_seen):
            if not cancelled_seen and phase["status"] != "completed":
                phase["status"] = "cancelled"
                cancelled_seen = True
    return phases


def _failed_phases(
    is_youtube: bool,
    ingest: Job | None,
    transcribe: Job | None,
    error: str | None,
) -> list[dict]:
    phases = _active_phases(is_youtube, ingest, transcribe)
    failed_set = False
    for phase in phases:
        if not failed_set and phase["status"] in ("running", "pending"):
            phase["status"] = "failed"
            phase["detail"] = error
            failed_set = True
    return phases


def _label_for(step_id: str) -> str:
    return {
        "download": "Download from YouTube",
        "upload": "Upload received",
        "convert": "Convert to 16 kHz WAV",
        "asr": "Load ASR model & transcribe",
        "diarize": "Diarize & align (optional)",
        "segments": "Build segments",
    }.get(step_id, step_id)
