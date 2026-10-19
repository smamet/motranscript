import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from apps.annotator.api.services import SPEAKER_COLORS, get_current_model_name
from apps.annotator.api.source_pipeline import CancelledError
from apps.annotator.config import get_settings
from apps.annotator.db.models import (
    Job,
    JobStatus,
    JobType,
    Segment,
    SegmentLang,
    SegmentStatus,
    Source,
    SourceStatus,
    Speaker,
)
from apps.annotator.pipeline.audio_ingestor import AudioIngestor
from apps.annotator.pipeline.inference import get_inference_backend
from apps.annotator.pipeline.lang_detector import classify_word, resolve_segment_lang
from apps.annotator.pipeline.segment_merger import MergedSegment, SegmentMerger
from apps.annotator.worker.heartbeat import touch_heartbeat

log = logging.getLogger(__name__)


def recover_stale_jobs(db: Session) -> int:
    """Reset jobs stuck in 'running' after worker/API restart."""
    stale = db.query(Job).filter(Job.status == JobStatus.running).all()
    for job in stale:
        job.status = JobStatus.pending
        job.progress = 0.0
        job.started_at = None
        job.phase = "Resuming after worker restart"
    if stale:
        db.commit()
    return len(stale)


class TranscriptionJob:
    """Orchestrates ingest → diarize → ASR → align → merge → persist."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.ingestor = AudioIngestor()
        self.merger = SegmentMerger()

    def _next_pending_job(self) -> Job | None:
        """Ingest first so a full download batch can finish before any ASR."""
        ingest = (
            self.db.query(Job)
            .filter(Job.status == JobStatus.pending, Job.job_type == JobType.ingest)
            .order_by(Job.id)
            .first()
        )
        if ingest:
            return ingest
        if not self.settings.transcribe_enabled:
            return None
        return (
            self.db.query(Job)
            .filter(Job.status == JobStatus.pending, Job.job_type == JobType.transcribe)
            .order_by(Job.id)
            .first()
        )

    def run_pending_jobs(self) -> bool:
        job = self._next_pending_job()
        if not job:
            return False

        source = self.db.get(Source, job.source_id)
        if not source or source.status == SourceStatus.cancelled:
            job.status = JobStatus.cancelled
            job.phase = "Cancelled"
            self.db.commit()
            return True

        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        if not job.phase or job.phase.startswith("Resuming"):
            job.phase = "Starting…"
        self.db.commit()

        try:
            self._ensure_not_cancelled(job.source_id)
            if job.job_type == JobType.ingest:
                self._run_ingest(job)
            elif job.job_type == JobType.transcribe:
                self._run_transcribe(job)
            job.status = JobStatus.completed
            job.progress = 1.0
            job.phase = "Done"
            job.finished_at = datetime.now(timezone.utc)
            self._update_source_status(job.source_id)
        except CancelledError:
            job.status = JobStatus.cancelled
            job.phase = "Cancelled by user"
            job.finished_at = datetime.now(timezone.utc)
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.failed
            job.error = str(exc)
            job.phase = "Failed"
            job.finished_at = datetime.now(timezone.utc)
            source = self.db.get(Source, job.source_id)
            if source:
                source.status = SourceStatus.failed
                source.error = str(exc)
        self.db.commit()
        return True

    def _ensure_not_cancelled(self, source_id: int) -> None:
        source = self.db.get(Source, source_id)
        if source and source.status == SourceStatus.cancelled:
            raise CancelledError()

    def _set_job(self, job: Job, progress: float, phase: str) -> None:
        job.progress = progress
        job.phase = phase
        self.db.commit()
        touch_heartbeat()
        self._ensure_not_cancelled(job.source_id)

    def _run_ingest(self, job: Job) -> None:
        source = self.db.get(Source, job.source_id)
        if not source:
            raise ValueError(f"Source {job.source_id} not found")
        source.status = SourceStatus.processing
        self.db.commit()

        if source.source_type.value == "youtube":
            if not source.source_url:
                raise ValueError("YouTube source missing URL")
            self._set_job(job, 0.05, "Downloading from YouTube…")
            result = self.ingestor.ingest_youtube(
                source.source_url, source.id, on_phase=self._ingest_phase(job)
            )
        else:
            if not source.audio_path:
                raise ValueError("Upload source missing audio path")
            self._set_job(job, 0.2, "Reading uploaded file…")
            result = self.ingestor.normalize_upload(Path(source.audio_path), source.id)

        self._set_job(job, 0.85, "Converting to 16 kHz mono WAV…")
        source.audio_path = str(result.audio_path)
        source.duration_sec = result.duration_sec
        self._set_job(job, 1.0, "Audio ready")

    def _ingest_phase(self, job: Job):
        def callback(progress: float, phase: str) -> None:
            self._set_job(job, progress, phase)

        return callback

    def _run_transcribe(self, job: Job) -> None:
        source = self.db.get(Source, job.source_id)
        if not source or not source.audio_path:
            raise ValueError("Source not ready for transcription")

        ingest_job = (
            self.db.query(Job)
            .filter(Job.source_id == source.id, Job.job_type == JobType.ingest)
            .first()
        )
        if ingest_job and ingest_job.status != JobStatus.completed:
            raise RuntimeError("Ingest job not completed yet")

        source.status = SourceStatus.processing
        source.pipeline_meta = None
        self.db.commit()

        model_name = get_current_model_name(self.db)
        audio_path = Path(source.audio_path)
        default_lang = source.default_lang or SegmentLang.mix

        def on_phase(progress: float, phase: str) -> None:
            self._set_job(job, progress, phase)

        backend = get_inference_backend()
        result = backend.transcribe(
            audio_path,
            model_name=model_name,
            default_lang=default_lang,
            source_id=source.id,
            on_phase=on_phase,
        )
        merged = result.segments
        pipeline_meta = result.pipeline_meta
        model_name = result.model_name

        if pipeline_meta.get("diarization_status") == "failed" and pipeline_meta.get(
            "diarization_error"
        ):
            job.error = (
                "Diarization failed (single-speaker fallback): "
                f"{pipeline_meta['diarization_error']}"
            )

        self._set_job(job, 0.92, "Saving segments & audio clips…")
        self._persist_segments(source, merged, model_name, default_lang)
        pipeline_meta["speaker_count"] = len({m.speaker for m in merged}) or 1
        source.pipeline_meta = pipeline_meta
        source.status = SourceStatus.ready
        if pipeline_meta.get("diarization_status") == "ok":
            job.error = None
            source.error = None
        elif pipeline_meta.get("diarization_error"):
            source.error = None
        self._set_job(job, 1.0, "Ready for editing")

    @staticmethod
    def _resolve_segment_lang(default_lang: SegmentLang, detected: str) -> SegmentLang:
        """Map merger output to SegmentLang; use source default as tie-breaker."""
        detected_norm = (detected or "").lower()
        if detected_norm in {"fr", "en", "kreol"}:
            return SegmentLang(detected_norm)
        if detected_norm == "mix":
            if default_lang in (SegmentLang.kreol, SegmentLang.fr, SegmentLang.en):
                return SegmentLang.mix
            return SegmentLang.mix
        return default_lang

    @staticmethod
    def _score_segment_lang(
        words: list[str],
        default_lang: SegmentLang,
        merger_lang: str,
    ) -> SegmentLang:
        """Re-score language; Kreol sources override French-only Whisper artifacts."""
        fallback = default_lang.value
        scored = resolve_segment_lang(words, fallback=fallback)
        if default_lang == SegmentLang.kreol and scored == "fr":
            has_kreol = any(classify_word(w) == "kreol" for w in words)
            if not has_kreol:
                scored = "kreol"
        if scored == "mix" and default_lang == SegmentLang.kreol and merger_lang == "kreol":
            scored = "kreol"
        return TranscriptionJob._resolve_segment_lang(default_lang, scored)

    def _persist_segments(
        self,
        source: Source,
        merged: list[MergedSegment],
        model_name: str,
        default_lang: SegmentLang,
    ) -> None:
        self.db.query(Segment).filter(Segment.source_id == source.id).delete()
        self.db.query(Speaker).filter(Speaker.source_id == source.id).delete()
        self.db.flush()

        speaker_map: dict[str, Speaker] = {}
        for idx, item in enumerate(merged):
            if item.speaker not in speaker_map:
                speaker = Speaker(
                    source_id=source.id,
                    label=item.speaker,
                    display_name=item.speaker,
                    color=SPEAKER_COLORS[len(speaker_map) % len(SPEAKER_COLORS)],
                )
                self.db.add(speaker)
                self.db.flush()
                speaker_map[item.speaker] = speaker

            seg_dir = self.settings.segments_dir / str(source.id)
            seg_dir.mkdir(parents=True, exist_ok=True)
            seg_path = seg_dir / f"segment_{idx:04d}.wav"
            SegmentMerger.cut_segment_wav(
                source.audio_path,
                str(seg_path),
                item.start,
                item.end,
            )
            # Re-score from text with source default as fallback
            words = (item.text or "").split()
            lang = self._score_segment_lang(words, default_lang, item.lang)

            self.db.add(
                Segment(
                    source_id=source.id,
                    speaker_id=speaker_map[item.speaker].id,
                    start_sec=item.start,
                    end_sec=item.end,
                    audio_path=str(seg_path),
                    text_raw=item.text,
                    text_corrected=item.text,
                    lang=lang,
                    status=SegmentStatus.raw,
                    model_version_used=model_name,
                )
            )

    def _update_source_status(self, source_id: int) -> None:
        source = self.db.get(Source, source_id)
        if not source:
            return
        # Session uses autoflush=False — flush job status changes before counting.
        self.db.flush()
        pending = (
            self.db.query(Job)
            .filter(
                Job.source_id == source_id,
                Job.status.in_([JobStatus.pending, JobStatus.running]),
            )
            .count()
        )
        failed = (
            self.db.query(Job)
            .filter(Job.source_id == source_id, Job.status == JobStatus.failed)
            .count()
        )
        if failed:
            source.status = SourceStatus.failed
        elif pending == 0 and source.audio_path:
            transcribe_done = (
                self.db.query(Job)
                .filter(
                    Job.source_id == source_id,
                    Job.job_type == JobType.transcribe,
                    Job.status == JobStatus.completed,
                )
                .count()
                > 0
            )
            if transcribe_done:
                source.status = SourceStatus.ready
            else:
                # Ingest finished; wait in catalog until admin promotes to ASR
                source.status = SourceStatus.downloaded
                source.error = None
        self.db.commit()
