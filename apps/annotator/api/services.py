import json
import shutil
import wave
from pathlib import Path
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from apps.annotator.api.source_pipeline import build_pipeline_status
from apps.annotator.api.system_health import collect_source_alerts
from apps.annotator.config import get_settings
from apps.annotator.db.models import (
    Job,
    JobStatus,
    JobType,
    ModelVersion,
    Segment,
    SegmentLang,
    SegmentSplit,
    SegmentStatus,
    Source,
    SourceStatus,
    SourceType,
    Speaker,
)


from apps.annotator.api.dedupe import (
    DuplicateSourceError,
    find_duplicate,
    require_new_key,
    upload_dedupe_key,
    youtube_dedupe_key,
)
from apps.annotator.pipeline.youtube_metadata import fetch_youtube_metadata

SPEAKER_COLORS = ["#6366f1", "#22c55e", "#f97316", "#ec4899", "#14b8a6", "#eab308"]


def seed_default_model(db: Session) -> None:
    settings = get_settings()
    existing = db.query(ModelVersion).filter(ModelVersion.is_current.is_(True)).first()
    if existing:
        return
    db.add(
        ModelVersion(
            name=settings.whisper_model,
            hf_repo=settings.whisper_model,
            is_current=True,
            metrics_json={"seed": True},
        )
    )
    db.commit()


def get_current_model_name(db: Session) -> str:
    model = db.query(ModelVersion).filter(ModelVersion.is_current.is_(True)).first()
    if model:
        return model.hf_repo or model.name
    return get_settings().whisper_model


def create_source_from_youtube(
    db: Session,
    youtube_url: str,
    title: str | None,
    license_notes: str | None,
    default_lang: SegmentLang = SegmentLang.mix,
    category_id: int | None = None,
) -> Source:
    key = youtube_dedupe_key(youtube_url)
    require_new_key(db, key)
    meta = fetch_youtube_metadata(youtube_url)
    source = Source(
        source_type=SourceType.youtube,
        source_url=youtube_url,
        dedupe_key=key,
        title=title or meta.title or youtube_url,
        license_notes=license_notes,
        category_id=category_id,
        duration_sec=meta.duration_sec,
        default_lang=default_lang,
        status=SourceStatus.pending,
        error=meta.error,
    )
    db.add(source)
    db.flush()
    _enqueue_pipeline_jobs(db, source)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _reraise_duplicate(db, key, exc)
    db.refresh(source)
    return source


def create_source_from_upload(
    db: Session,
    filename: str,
    upload_path: Path,
    title: str | None,
    license_notes: str | None,
    default_lang: SegmentLang = SegmentLang.mix,
    category_id: int | None = None,
) -> Source:
    settings = get_settings()
    key = upload_dedupe_key(upload_path)
    try:
        require_new_key(db, key)
    except DuplicateSourceError:
        upload_path.unlink(missing_ok=True)
        raise
    dest = settings.uploads_dir / f"{Path(filename).stem}_{upload_path.stat().st_mtime_ns}{Path(filename).suffix}"
    shutil.move(str(upload_path), dest)
    source = Source(
        source_type=SourceType.upload,
        original_filename=filename,
        dedupe_key=key,
        title=title or filename,
        license_notes=license_notes,
        category_id=category_id,
        default_lang=default_lang,
        status=SourceStatus.pending,
    )
    db.add(source)
    db.flush()
    # Store raw upload path on source until ingest normalizes it
    source.audio_path = str(dest)
    _enqueue_pipeline_jobs(db, source, skip_ingest=False)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        dest.unlink(missing_ok=True)
        _reraise_duplicate(db, key, exc)
    db.refresh(source)
    return source


def _reraise_duplicate(db: Session, key: str, exc: IntegrityError) -> NoReturn:
    existing = find_duplicate(db, key)
    if existing:
        raise DuplicateSourceError(existing) from exc
    raise exc


def _enqueue_pipeline_jobs(db: Session, source: Source, skip_ingest: bool = False) -> None:
    """Enqueue ingest only — ASR starts after admin promote to To do."""
    if not skip_ingest:
        db.add(
            Job(
                source_id=source.id,
                job_type=JobType.ingest,
                status=JobStatus.pending,
            )
        )


def bulk_update_segment_lang(
    db: Session,
    source_id: int,
    segment_ids: list[int],
    lang: SegmentLang,
) -> list[Segment]:
    segments = (
        db.query(Segment)
        .filter(Segment.source_id == source_id, Segment.id.in_(segment_ids))
        .all()
    )
    if len(segments) != len(segment_ids):
        raise ValueError("One or more segments not found for this source")
    for segment in segments:
        segment.lang = lang
    db.commit()
    for segment in segments:
        db.refresh(segment)
    return segments


def get_source_detail(db: Session, source_id: int) -> Source | None:
    return (
        db.query(Source)
        .options(
            joinedload(Source.jobs),
            joinedload(Source.category),
            joinedload(Source.assignee),
        )
        .filter(Source.id == source_id)
        .first()
    )


def get_editor_session(db: Session, source_id: int) -> dict | None:
    source = get_source_detail(db, source_id)
    if not source:
        return None
    jobs = sorted(
        db.query(Job).filter(Job.source_id == source_id).all(),
        key=lambda j: j.id,
    )
    speakers = db.query(Speaker).filter(Speaker.source_id == source_id).order_by(Speaker.id).all()
    segments = (
        db.query(Segment)
        .filter(Segment.source_id == source_id)
        .order_by(Segment.start_sec)
        .all()
    )
    src = db.get(Source, source_id)
    pipeline = build_pipeline_status(src, jobs) if src else {}
    return {
        "source": source,
        "speakers": speakers,
        "segments": segments,
        "audio_url": f"/api/sources/{source_id}/audio",
        "pipeline_meta": src.pipeline_meta if src else None,
        "alerts": collect_source_alerts(src, jobs, pipeline) if src else [],
    }


def _segment_export_record(
    seg: Segment,
    speaker: Speaker | None,
    source_id: int,
    audio_path: str,
) -> dict:
    text = seg.text_corrected or seg.text_raw or ""
    return {
        "audio_path": audio_path,
        "text": text,
        "lang": seg.lang.value,
        "speaker": speaker.display_name or speaker.label if speaker else "unknown",
        "duration": round(seg.end_sec - seg.start_sec, 3),
        "source_id": source_id,
        "segment_id": seg.id,
        "split": seg.split.value,
        "model_version_used": seg.model_version_used,
        "annotator": seg.annotator,
    }


def mark_source_as_frozen_test(db: Session, source_id: int) -> int:
    """Mark every segment on a source as frozen test split."""
    source = db.get(Source, source_id)
    if not source:
        raise ValueError("Source not found")
    segments = db.query(Segment).filter(Segment.source_id == source_id).all()
    for seg in segments:
        seg.split = SegmentSplit.test
    db.commit()
    return len(segments)


def export_validated_segments(db: Session, source_id: int) -> tuple[Path, int]:
    settings = get_settings()
    segments = (
        db.query(Segment)
        .join(Speaker)
        .filter(Segment.source_id == source_id, Segment.status == SegmentStatus.validated)
        .order_by(Segment.start_sec)
        .all()
    )
    export_dir = settings.exports_dir / f"source_{source_id}"
    export_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = export_dir / "dataset.jsonl"
    wav_count = 0
    with jsonl_path.open("w", encoding="utf-8") as f:
        for seg in segments:
            speaker = db.get(Speaker, seg.speaker_id)
            wav_name = f"segment_{seg.id}.wav"
            if seg.audio_path and Path(seg.audio_path).exists():
                dest = export_dir / wav_name
                shutil.copy2(seg.audio_path, dest)
                wav_count += 1
                audio_path = wav_name
            else:
                audio_path = seg.audio_path or ""
            record = _segment_export_record(seg, speaker, source_id, audio_path)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonl_path, wav_count


def export_all_validated_segments(db: Session) -> tuple[Path, int, int]:
    """Export all validated segments across sources into one training folder."""
    settings = get_settings()
    segments = (
        db.query(Segment)
        .join(Speaker)
        .filter(Segment.status == SegmentStatus.validated)
        .order_by(Segment.source_id, Segment.start_sec)
        .all()
    )
    export_dir = settings.exports_dir / "all_validated"
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = export_dir / "dataset.jsonl"
    wav_count = 0
    with jsonl_path.open("w", encoding="utf-8") as f:
        for seg in segments:
            speaker = db.get(Speaker, seg.speaker_id)
            wav_name = f"source_{seg.source_id}_segment_{seg.id}.wav"
            if seg.audio_path and Path(seg.audio_path).exists():
                dest = export_dir / wav_name
                shutil.copy2(seg.audio_path, dest)
                wav_count += 1
                audio_path = wav_name
            else:
                audio_path = seg.audio_path or ""
            record = _segment_export_record(seg, speaker, seg.source_id, audio_path)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonl_path, wav_count, len(segments)


def register_model_version(
    db: Session,
    *,
    name: str,
    hf_repo: str,
    metrics_json: dict | None = None,
    make_current: bool = False,
) -> ModelVersion:
    existing = db.query(ModelVersion).filter(ModelVersion.name == name).first()
    if existing:
        existing.hf_repo = hf_repo
        if metrics_json is not None:
            existing.metrics_json = metrics_json
        model = existing
    else:
        model = ModelVersion(
            name=name,
            hf_repo=hf_repo,
            is_current=False,
            metrics_json=metrics_json,
        )
        db.add(model)
        db.flush()
    if make_current:
        db.query(ModelVersion).update({ModelVersion.is_current: False})
        model.is_current = True
    db.commit()
    db.refresh(model)
    return model


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())
