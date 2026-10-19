"""Review workflow: todo / done / validated + segment comments."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.annotator.api.user_time import (
    credit_done,
    move_done_to_validated,
    reverse_done_for_source,
    reverse_validated_for_source,
    segment_export_text,
)
from apps.annotator.db.models import (
    ReviewStatus,
    Segment,
    SegmentStatus,
    Source,
    SourceStatus,
    User,
    UserRole,
)


class ReviewError(ValueError):
    """Invalid review transition or comment update."""


def clear_review_feedback(db: Session, source_id: int) -> None:
    """Clear source note and all segment comments for a source."""
    source = db.get(Source, source_id)
    if source:
        source.review_note = None
    db.query(Segment).filter(Segment.source_id == source_id).update(
        {Segment.review_comment: None, Segment.review_comment_by: None},
        synchronize_session=False,
    )


def reset_review_on_retranscribe(db: Session, source: Source) -> None:
    """Reset review to todo and reverse any open Done/Validated payroll credit."""
    if source.review_status == ReviewStatus.done:
        reverse_done_for_source(db, source=source)
    elif source.review_status == ReviewStatus.validated:
        reverse_validated_for_source(db, source=source)
    source.review_status = ReviewStatus.todo
    source.reviewed_by = None
    source.reviewed_at = None
    source.review_note = None
    # Keep assigned_to_user_id


def is_segment_touched(segment: Segment) -> bool:
    return segment.status != SegmentStatus.raw or bool(segment.annotator)


def is_segment_ready_for_done(segment: Segment) -> bool:
    return segment.status in (
        SegmentStatus.corrected,
        SegmentStatus.validated,
        SegmentStatus.ignored,
    )


def can_validate_segment(segment: Segment) -> bool:
    return bool(segment_export_text(segment))


def source_progress(db: Session, source_id: int) -> tuple[int, int, int]:
    """Return (touched_count, ready_for_done_count, total)."""
    segments = db.query(Segment).filter(Segment.source_id == source_id).all()
    total = len(segments)
    touched = sum(1 for s in segments if is_segment_touched(s))
    ready = sum(1 for s in segments if is_segment_ready_for_done(s))
    return touched, ready, total


def can_mark_done(source: Source, ready_count: int, total: int) -> bool:
    return (
        source.status == SourceStatus.ready
        and source.review_status == ReviewStatus.todo
        and total > 0
        and ready_count == total
        and source.assigned_to_user_id is not None
    )


def is_partial(source: Source, touched: int, total: int, ready_count: int | None = None) -> bool:
    if total <= 0 or touched <= 0:
        return False
    if ready_count is not None and ready_count >= total:
        return False
    return (
        source.status == SourceStatus.ready
        and source.review_status == ReviewStatus.todo
    )


def comment_count(db: Session, source_id: int) -> int:
    return (
        db.query(Segment)
        .filter(
            Segment.source_id == source_id,
            Segment.review_comment.isnot(None),
            Segment.review_comment != "",
        )
        .count()
    )


def aggregate_review_hours(db: Session) -> dict[str, float]:
    """Sum duration_sec of ready sources per review_status (seconds) — gross load."""
    rows = (
        db.query(Source.review_status, func.coalesce(func.sum(Source.duration_sec), 0.0))
        .filter(Source.status == SourceStatus.ready)
        .group_by(Source.review_status)
        .all()
    )
    hours = {"todo": 0.0, "done": 0.0, "validated": 0.0}
    for status, total in rows:
        key = status.value if isinstance(status, ReviewStatus) else str(status)
        hours[key] = float(total or 0.0)
    return hours


def _admin_transition_ok(current: ReviewStatus, new: ReviewStatus) -> bool:
    return (current, new) in {
        (ReviewStatus.todo, ReviewStatus.done),
        (ReviewStatus.done, ReviewStatus.todo),
        (ReviewStatus.done, ReviewStatus.validated),
        (ReviewStatus.validated, ReviewStatus.todo),
    }


def _operator_transition_ok(current: ReviewStatus, new: ReviewStatus) -> bool:
    return (current, new) in {
        (ReviewStatus.todo, ReviewStatus.done),
        (ReviewStatus.done, ReviewStatus.todo),
    }


def set_review_status(
    db: Session,
    source: Source,
    new_status: ReviewStatus,
    user: User,
    note: str | None = None,
) -> Source:
    if source.status != SourceStatus.ready:
        raise ReviewError("Source must be ready before changing review status")

    current = source.review_status
    is_admin = user.role == UserRole.admin
    note_text = (note or "").strip() or None

    if current == new_status:
        raise ReviewError("Already in that review status")

    if is_admin:
        if not _admin_transition_ok(current, new_status):
            raise ReviewError(f"Cannot move from {current.value} to {new_status.value}")
        if note_text and new_status != ReviewStatus.todo:
            raise ReviewError("Review note is only allowed when rejecting to todo")
    else:
        if not _operator_transition_ok(current, new_status):
            raise ReviewError("Operators can only mark sources done or reopen them")
        if note_text:
            raise ReviewError("Only admins can set a review note")
        if source.assigned_to_user_id != user.id:
            raise ReviewError("Source is not assigned to you")

    if new_status == ReviewStatus.todo and current in (
        ReviewStatus.done,
        ReviewStatus.validated,
    ):
        source.review_note = note_text if is_admin else None
        if current == ReviewStatus.done:
            reverse_done_for_source(db, source=source, created_by=user)
        else:
            reverse_validated_for_source(db, source=source, created_by=user)
    elif new_status == ReviewStatus.validated:
        clear_review_feedback(db, source.id)
        move_done_to_validated(db, source=source, created_by=user)
    elif new_status == ReviewStatus.done:
        if source.assigned_to_user_id is None:
            raise ReviewError("Source must be assigned before marking done")
        assignee = db.get(User, source.assigned_to_user_id)
        if not assignee:
            raise ReviewError("Assigned user not found")
        _touched, ready_count, total = source_progress(db, source.id)
        if not can_mark_done(source, ready_count, total):
            raise ReviewError(
                "All segments must be corrected, validated, or ignored before marking done"
            )
        credit_done(db, user=assignee, source=source, created_by=user)

    source.review_status = new_status
    source.reviewed_by = user.email
    source.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return source


def set_segment_review_comment(
    db: Session,
    segment: Segment,
    comment: str | None,
    user: User,
) -> Segment:
    if user.role != UserRole.admin:
        raise ReviewError("Only admins can set segment review comments")
    text = (comment or "").strip() or None
    segment.review_comment = text
    segment.review_comment_by = user.email if text else None
    db.commit()
    db.refresh(segment)
    return segment
