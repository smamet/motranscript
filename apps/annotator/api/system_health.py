"""Global and per-source system health alerts for the UI."""

from __future__ import annotations

from typing import Literal

from apps.annotator.config import get_settings
from apps.annotator.db.models import Job, JobStatus, JobType, Source, SourceStatus

Severity = Literal["error", "warning", "info"]


def _alert(alert_id: str, severity: Severity, message: str, hint: str | None = None) -> dict:
    return {"id": alert_id, "severity": severity, "message": message, "hint": hint}


def pyannote_import_error() -> str | None:
    try:
        import pyannote.audio  # noqa: F401
    except ImportError:
        return "pyannote not installed — run: uv sync --extra pipeline"
    return None


def ytdlp_node_error() -> str | None:
    from apps.annotator.pipeline.yt_dlp_args import resolve_node_executable

    if resolve_node_executable() is None:
        return (
            "Node.js not found — YouTube downloads will fail for many videos. "
            "Install node or set YT_DLP_NODE_PATH."
        )
    return None


def normalizer_load_error(db=None) -> str | None:
    try:
        from apps.annotator.api.lexicon import get_lexicon

        lexicon = get_lexicon(db)
        if not lexicon.official_words():
            return "Kreol lexicon is empty"
    except Exception as exc:  # noqa: BLE001
        return f"Normalizer lexicon failed to load: {exc}"
    return None


def collect_global_alerts(
    *,
    worker_alive: bool,
    needs_worker: bool = False,
) -> list[dict]:
    settings = get_settings()
    alerts: list[dict] = []

    if needs_worker and not worker_alive:
        alerts.append(
            _alert(
                "worker_down",
                "error",
                "Worker not running — pending jobs will not process.",
                "Run: uv run python -m apps.annotator.worker",
            )
        )
    elif not worker_alive:
        alerts.append(
            _alert(
                "worker_down",
                "warning",
                "Worker not running.",
                "Run: uv run python -m apps.annotator.worker",
            )
        )

    backend = (settings.inference_backend or "local").lower().strip()

    if backend == "runpod":
        if not settings.runpod_api_key or not settings.runpod_endpoint_id:
            alerts.append(
                _alert(
                    "runpod_not_configured",
                    "warning",
                    "RunPod Serverless not configured — transcription jobs will fail.",
                    "Set RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID in .env (ASR runs on GPU, not this VPS).",
                )
            )
        if not settings.public_base_url:
            alerts.append(
                _alert(
                    "public_base_url_missing",
                    "warning",
                    "PUBLIC_BASE_URL not set — RunPod cannot download audio from this server.",
                )
            )
        # pyannote lives on the RunPod worker image, not on this CPU VPS — do not warn.
    else:
        if settings.enable_diarization and not settings.hf_token:
            alerts.append(
                _alert(
                    "hf_token_missing",
                    "warning",
                    "HF_TOKEN not set — speaker diarization disabled (single speaker).",
                    "Add HF_TOKEN to .env and accept pyannote licenses on HuggingFace.",
                )
            )

        if settings.enable_diarization and settings.hf_token:
            pyannote_err = pyannote_import_error()
            if pyannote_err:
                alerts.append(_alert("pyannote_missing", "warning", pyannote_err))

    if not settings.transcribe_enabled:
        alerts.append(
            _alert(
                "transcribe_paused",
                "info",
                "Transcription paused — downloads continue, ASR waits.",
                "Set TRANSCRIBE_ENABLED=true and restart the worker when ready to resume.",
            )
        )

    if not settings.enable_diarization:
        alerts.append(
            _alert(
                "diarization_disabled",
                "info",
                "Diarization disabled (ENABLE_DIARIZATION=false) — all speech assigned to one speaker.",
            )
        )

    norm_err = normalizer_load_error()
    if norm_err:
        alerts.append(_alert("normalizer_unavailable", "error", norm_err))

    ytdlp_err = ytdlp_node_error()
    if ytdlp_err:
        alerts.append(_alert("ytdlp_node_missing", "warning", ytdlp_err))

    return alerts


def _is_cascade_transcribe_error(message: str) -> bool:
    return "source not ready for transcription" in message.lower()


def collect_source_alerts(source: Source, jobs: list[Job], pipeline: dict | None = None) -> list[dict]:
    pipeline = pipeline or {}
    alerts: list[dict] = []
    meta = source.pipeline_meta or {}

    ingest_failed = next(
        (j for j in jobs if j.job_type == JobType.ingest and j.status == JobStatus.failed and j.error),
        None,
    )
    job_messages: list[str] = []

    diar_status = meta.get("diarization_status") or pipeline.get("diarization_status")
    diar_error = meta.get("diarization_error") or pipeline.get("diarization_error")

    if source.status == SourceStatus.ready:
        if diar_status == "failed":
            alerts.append(
                _alert(
                    "diarization_failed",
                    "warning",
                    "Diarization failed — single speaker fallback.",
                    diar_error,
                )
            )
        elif diar_status == "skipped":
            alerts.append(
                _alert(
                    "diarization_skipped",
                    "warning",
                    "Diarization skipped — single speaker.",
                    diar_error,
                )
            )

    for job in jobs:
        if job.status == JobStatus.failed and job.error:
            if (
                job.job_type == JobType.transcribe
                and ingest_failed
                and _is_cascade_transcribe_error(job.error)
            ):
                continue
            job_messages.append(job.error)
            alerts.append(
                _alert(
                    f"job_{job.job_type.value}_failed",
                    "error",
                    job.error,
                )
            )
        elif job.status == JobStatus.completed and job.error:
            if diar_status in {"failed", "skipped"}:
                continue
            alerts.append(
                _alert(
                    f"job_{job.job_type.value}_warning",
                    "warning",
                    job.error,
                )
            )

    if source.error and source.error not in job_messages:
        if not (ingest_failed and _is_cascade_transcribe_error(source.error)):
            alerts.insert(0, _alert("source_error", "error", source.error))

    return alerts
