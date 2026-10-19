import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from apps.annotator.api.catalog_sample import CatalogCandidate, sample_catalog
from apps.annotator.api.review import (
    can_mark_done,
    comment_count,
    is_partial,
    reset_review_on_retranscribe,
    source_progress,
)
from apps.annotator.api.source_pipeline import build_pipeline_status
from apps.annotator.api.system_health import collect_source_alerts
from apps.annotator.config import get_settings
from apps.annotator.db.models import (
    Category,
    Job,
    JobStatus,
    JobType,
    Segment,
    SegmentStatus,
    Source,
    SourceStatus,
    Speaker,
    User,
    UserRole,
)


def _pending_job_order(db: Session) -> list[int]:
    """Source IDs in FIFO worker order (pending jobs only)."""
    pending = (
        db.query(Job)
        .filter(Job.status == JobStatus.pending)
        .order_by(Job.id)
        .all()
    )
    seen: list[int] = []
    for job in pending:
        if job.source_id not in seen:
            seen.append(job.source_id)
    return seen


def _category_payload(source: Source) -> dict | None:
    if not source.category:
        return None
    return {
        "id": source.category.id,
        "slug": source.category.slug,
        "label": source.category.label,
    }


def _net_audio_by_source(db: Session, source_ids: list[int]) -> dict[int, float]:
    if not source_ids:
        return {}
    rows = (
        db.query(Segment)
        .filter(Segment.source_id.in_(source_ids))
        .with_entities(
            Segment.source_id,
            Segment.start_sec,
            Segment.end_sec,
            Segment.status,
            Segment.text_raw,
            Segment.text_corrected,
        )
        .all()
    )
    totals: dict[int, float] = {sid: 0.0 for sid in source_ids}
    for source_id, start, end, status, text_raw, text_corrected in rows:
        if status == SegmentStatus.ignored:
            continue
        text = (text_corrected or text_raw or "").strip()
        if not text:
            continue
        totals[source_id] = totals.get(source_id, 0.0) + max(0.0, float(end) - float(start))
    return totals


def _source_list_item(
    source: Source,
    queue: list[int],
    db: Session,
    *,
    net_sec: float | None = None,
) -> dict:
    jobs = sorted(source.jobs, key=lambda j: j.id)
    queue_position = None
    if source.id in queue:
        queue_position = queue.index(source.id) + 1
    pipeline = build_pipeline_status(source, jobs, queue_position=queue_position)
    touched, ready_count, total = source_progress(db, source.id)
    return {
        "id": source.id,
        "source_type": source.source_type.value,
        "title": source.title,
        "original_filename": source.original_filename,
        "duration_sec": source.duration_sec,
        "net_audio_sec": net_sec if net_sec is not None else 0.0,
        "status": source.status.value,
        "error": source.error,
        "created_at": source.created_at,
        "pipeline": pipeline,
        "pipeline_meta": source.pipeline_meta,
        "alerts": collect_source_alerts(source, jobs, pipeline),
        "review_status": source.review_status.value,
        "review_note": source.review_note,
        "reviewed_by": source.reviewed_by,
        "reviewed_at": source.reviewed_at,
        "partial": is_partial(source, touched, total, ready_count),
        "touched_count": touched,
        "segment_count": total,
        "comment_count": comment_count(db, source.id),
        "can_mark_done": can_mark_done(source, ready_count, total),
        "category": _category_payload(source),
        "source_url": source.source_url,
        "assigned_to_user_id": source.assigned_to_user_id,
        "assigned_to_email": source.assignee.email if source.assignee else None,
    }


def list_sources_with_pipeline(
    db: Session,
    *,
    user: User | None = None,
    assigned_to: str | None = None,
) -> list[dict]:
    query = (
        db.query(Source)
        .options(
            joinedload(Source.jobs),
            joinedload(Source.category),
            joinedload(Source.assignee),
        )
        .order_by(Source.created_at.desc())
    )
    if user is not None and user.role != UserRole.admin:
        query = query.filter(
            (Source.assigned_to_user_id == user.id) | (Source.assigned_to_user_id.is_(None))
        )
    elif user is not None and user.role == UserRole.admin and assigned_to:
        if assigned_to == "unassigned":
            query = query.filter(Source.assigned_to_user_id.is_(None))
        else:
            try:
                uid = int(assigned_to)
            except ValueError as exc:
                raise ValueError("assigned_to must be a user id or 'unassigned'") from exc
            query = query.filter(Source.assigned_to_user_id == uid)

    sources = query.all()
    queue = _pending_job_order(db)
    net_by_id = _net_audio_by_source(db, [s.id for s in sources])
    return [
        _source_list_item(source, queue, db, net_sec=net_by_id.get(source.id, 0.0))
        for source in sources
    ]


def aggregate_catalog_hours(db: Session) -> tuple[float, dict[str, float]]:
    """Return (total_downloaded_seconds, {slug: seconds})."""
    rows = (
        db.query(
            Category.slug,
            func.coalesce(func.sum(Source.duration_sec), 0.0),
        )
        .select_from(Source)
        .outerjoin(Category, Source.category_id == Category.id)
        .filter(Source.status == SourceStatus.downloaded)
        .group_by(Category.slug)
        .all()
    )
    by_cat: dict[str, float] = {}
    total = 0.0
    for slug, sec in rows:
        key = slug or "uncategorized"
        val = float(sec or 0.0)
        by_cat[key] = val
        total += val
    return total, by_cat


def cancel_source(db: Session, source_id: int) -> Source | None:
    source = db.get(Source, source_id)
    if not source:
        return None
    if source.status not in (SourceStatus.pending, SourceStatus.processing):
        return source

    now = datetime.now(timezone.utc)
    for job in db.query(Job).filter(Job.source_id == source_id).all():
        if job.status in (JobStatus.pending, JobStatus.running):
            job.status = JobStatus.cancelled
            job.phase = "Cancelled by user"
            job.finished_at = now

    source.status = SourceStatus.cancelled
    source.error = None
    db.commit()
    db.refresh(source)
    return source


def resume_source(db: Session, source_id: int) -> Source | None:
    """Resume ingest for failed/cancelled downloads. Does not start ASR."""
    source = db.get(Source, source_id)
    if not source:
        return None
    if source.status == SourceStatus.processing:
        raise ValueError("Source is still processing")
    if source.status not in (SourceStatus.cancelled, SourceStatus.failed):
        raise ValueError("Source cannot be resumed from its current state")

    if source.audio_path:
        raise ValueError("Audio already exists — use Re-transcribe or Send to To do")

    jobs = {j.job_type: j for j in db.query(Job).filter(Job.source_id == source_id).all()}
    ingest = jobs.get(JobType.ingest)

    if ingest and ingest.status != JobStatus.completed:
        ingest.status = JobStatus.pending
        ingest.progress = 0.0
        ingest.phase = "Queued for resume"
        ingest.error = None
        ingest.started_at = None
        ingest.finished_at = None
    elif not ingest:
        db.add(Job(source_id=source_id, job_type=JobType.ingest, status=JobStatus.pending))

    source.status = SourceStatus.pending
    source.error = None
    source.pipeline_meta = None
    db.commit()
    db.refresh(source)
    return source


def promote_sources(db: Session, source_ids: list[int]) -> list[Source]:
    """Move catalog sources into the ASR queue (admin Send to To do)."""
    if not source_ids:
        return []
    sources = db.query(Source).filter(Source.id.in_(source_ids)).all()
    by_id = {s.id: s for s in sources}
    promoted: list[Source] = []
    for sid in source_ids:
        source = by_id.get(sid)
        if not source:
            raise ValueError(f"Source #{sid} not found")
        if not source.audio_path:
            raise ValueError(f'"{source.title or sid}" has no audio yet')
        ingest = (
            db.query(Job)
            .filter(Job.source_id == sid, Job.job_type == JobType.ingest)
            .first()
        )
        if ingest and ingest.status != JobStatus.completed:
            raise ValueError(f'"{source.title or sid}" ingest is not complete')
        if source.status not in (
            SourceStatus.downloaded,
            SourceStatus.failed,
            SourceStatus.cancelled,
        ):
            raise ValueError(
                f'"{source.title or sid}" cannot be promoted from status={source.status.value}'
            )

        transcribe_job = (
            db.query(Job)
            .filter(Job.source_id == sid, Job.job_type == JobType.transcribe)
            .first()
        )
        if transcribe_job:
            if transcribe_job.status == JobStatus.completed:
                raise ValueError(f'"{source.title or sid}" is already transcribed')
            transcribe_job.status = JobStatus.pending
            transcribe_job.progress = 0.0
            transcribe_job.phase = "Queued for transcription"
            transcribe_job.error = None
            transcribe_job.started_at = None
            transcribe_job.finished_at = None
        else:
            db.add(
                Job(
                    source_id=sid,
                    job_type=JobType.transcribe,
                    status=JobStatus.pending,
                    phase="Queued for transcription",
                )
            )

        source.status = SourceStatus.pending
        source.error = None
        source.pipeline_meta = None
        promoted.append(source)

    db.commit()
    for source in promoted:
        db.refresh(source)
    return promoted


def set_source_category(db: Session, source_id: int, category_id: int | None) -> Source | None:
    source = db.get(Source, source_id)
    if not source:
        return None
    if category_id is not None and db.get(Category, category_id) is None:
        raise ValueError("Category not found")
    source.category_id = category_id
    db.commit()
    db.refresh(source)
    return source


def catalog_sample_for_sources(
    db: Session,
    *,
    target_hours: float,
    weights: dict[str, float],
    source_ids: list[int] | None = None,
) -> dict:
    q = (
        db.query(Source)
        .options(joinedload(Source.category))
        .filter(Source.status == SourceStatus.downloaded, Source.audio_path.isnot(None))
    )
    if source_ids is not None:
        if not source_ids:
            return {"source_ids": [], "seconds_by_category": {}, "total_seconds": 0.0}
        q = q.filter(Source.id.in_(source_ids))
    sources = q.all()
    candidates = [
        CatalogCandidate(
            source_id=s.id,
            category_slug=(s.category.slug if s.category else "uncategorized"),
            duration_sec=float(s.duration_sec or 0.0),
        )
        for s in sources
    ]
    return sample_catalog(candidates, target_hours=target_hours, weights=weights)


def retranscribe_source(db: Session, source_id: int) -> Source | None:
    """Re-run transcription; keeps source audio, replaces segments/speakers."""
    source = db.get(Source, source_id)
    if not source:
        return None
    if not source.audio_path:
        raise ValueError("Source has no audio yet — use Resume to restart ingest")
    if source.status == SourceStatus.processing:
        raise ValueError("Source is still processing")
    if source.status == SourceStatus.downloaded:
        raise ValueError("Source is in Downloaded catalog — use Send to To do")

    settings = get_settings()
    _remove_path(settings.segments_dir / str(source_id))

    db.query(Segment).filter(Segment.source_id == source_id).delete()
    db.query(Speaker).filter(Speaker.source_id == source_id).delete()
    transcribe_job = (
        db.query(Job)
        .filter(Job.source_id == source_id, Job.job_type == JobType.transcribe)
        .first()
    )
    if transcribe_job:
        transcribe_job.status = JobStatus.pending
        transcribe_job.progress = 0.0
        transcribe_job.phase = "Queued for re-transcription"
        transcribe_job.error = None
        transcribe_job.started_at = None
        transcribe_job.finished_at = None
    else:
        db.add(Job(source_id=source_id, job_type=JobType.transcribe, status=JobStatus.pending))

    source.status = SourceStatus.pending
    source.error = None
    source.pipeline_meta = None
    reset_review_on_retranscribe(db, source)
    db.commit()
    db.refresh(source)
    return source


def delete_source(db: Session, source_id: int) -> bool:
    source = db.get(Source, source_id)
    if not source:
        return False

    settings = get_settings()
    _remove_path(settings.sources_dir / str(source_id))
    _remove_path(settings.segments_dir / str(source_id))
    if source.audio_path:
        upload_path = Path(source.audio_path)
        if upload_path.is_file() and "uploads" in upload_path.parts:
            upload_path.unlink(missing_ok=True)

    db.delete(source)
    db.commit()
    return True


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        path.unlink(missing_ok=True)
