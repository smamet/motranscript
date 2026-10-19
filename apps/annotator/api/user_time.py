"""Audio-hours ledger for transcription payroll (Done vs Validated, net time)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from apps.annotator.db.models import (
    PaymentPeriod,
    ReviewStatus,
    Segment,
    SegmentStatus,
    Source,
    SourceStatus,
    User,
    UserTimeBucket,
    UserTimeEvent,
    UserTimeEventKind,
)


class UserTimeError(ValueError):
    """Invalid time ledger transition."""


def segment_export_text(segment: Segment) -> str:
    return (segment.text_corrected or segment.text_raw or "").strip()


def is_net_segment(segment: Segment) -> bool:
    return segment.status != SegmentStatus.ignored and bool(segment_export_text(segment))


def source_net_audio_sec(db: Session, source: Source) -> float:
    segments = db.query(Segment).filter(Segment.source_id == source.id).all()
    return float(
        sum(max(0.0, s.end_sec - s.start_sec) for s in segments if is_net_segment(s))
    )


# Backward-compatible alias used by older call sites / tests helpers
def source_audio_sec(db: Session, source: Source) -> float:
    return source_net_audio_sec(db, source)


def mur_for_sec(user: User, sec: float) -> float:
    rate = float(user.hourly_rate_mur or 0)
    amount = Decimal(str(sec / 3600.0)) * Decimal(str(rate))
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def owed_mur(user: User, validated_sec: float) -> float:
    return mur_for_sec(user, validated_sec)


def _events_for_user(db: Session, user_id: int) -> list[UserTimeEvent]:
    return (
        db.query(UserTimeEvent)
        .filter(UserTimeEvent.user_id == user_id)
        .order_by(UserTimeEvent.created_at.asc(), UserTimeEvent.id.asc())
        .all()
    )


def _period_start_index(events: list[UserTimeEvent]) -> tuple[int, float]:
    """Return (index of first event in current validated period, base_sec from rollback)."""
    period_events = [
        (i, e)
        for i, e in enumerate(events)
        if e.kind in (UserTimeEventKind.reset, UserTimeEventKind.rollback)
    ]
    if not period_events:
        return 0, 0.0
    _i, latest = period_events[-1]
    if latest.kind == UserTimeEventKind.rollback:
        start = _i + 1
        return start, float(latest.audio_sec)
    return _i + 1, 0.0


def can_rollback(db: Session, user_id: int) -> bool:
    events = _events_for_user(db, user_id)
    period = [
        e
        for e in events
        if e.kind in (UserTimeEventKind.reset, UserTimeEventKind.rollback)
    ]
    return bool(period) and period[-1].kind == UserTimeEventKind.reset


def last_period_event(db: Session, user_id: int) -> UserTimeEvent | None:
    events = _events_for_user(db, user_id)
    period = [
        e
        for e in events
        if e.kind in (UserTimeEventKind.reset, UserTimeEventKind.rollback)
    ]
    return period[-1] if period else None


def done_audio_sec(db: Session, user_id: int) -> float:
    events = _events_for_user(db, user_id)
    total = 0.0
    for e in events:
        if e.bucket != UserTimeBucket.done:
            continue
        if e.kind == UserTimeEventKind.credit:
            total += float(e.audio_sec)
        elif e.kind == UserTimeEventKind.reverse:
            total -= float(e.audio_sec)
    return max(0.0, total)


def validated_audio_sec(db: Session, user_id: int) -> float:
    events = _events_for_user(db, user_id)
    start_idx, base = _period_start_index(events)
    total = base
    for e in events[start_idx:]:
        if e.bucket != UserTimeBucket.validated:
            continue
        if e.kind == UserTimeEventKind.credit:
            total += float(e.audio_sec)
        elif e.kind == UserTimeEventKind.reverse:
            total -= float(e.audio_sec)
    return max(0.0, total)


def in_progress_audio_sec(db: Session, user_id: int) -> float:
    """Net seconds on ready+todo sources assigned to this user (corrected/validated segs)."""
    rows = (
        db.query(Segment)
        .join(Source, Segment.source_id == Source.id)
        .filter(
            Source.assigned_to_user_id == user_id,
            Source.status == SourceStatus.ready,
            Source.review_status == ReviewStatus.todo,
            Segment.status.in_([SegmentStatus.corrected, SegmentStatus.validated]),
        )
        .all()
    )
    return float(
        sum(max(0.0, s.end_sec - s.start_sec) for s in rows if is_net_segment(s))
    )


def _unmatched_credit(
    events: list[UserTimeEvent],
    *,
    bucket: UserTimeBucket,
    source_id: int,
    start_idx: int = 0,
) -> UserTimeEvent | None:
    """Latest credit for source/bucket after start_idx with no reverse after it."""
    credits: list[UserTimeEvent] = []
    for e in events[start_idx:]:
        if e.source_id != source_id or e.bucket != bucket:
            continue
        if e.kind == UserTimeEventKind.credit:
            credits.append(e)
        elif e.kind == UserTimeEventKind.reverse and credits:
            credits.pop()
    return credits[-1] if credits else None


def _unmatched_credit_any_period(
    db: Session,
    *,
    source_id: int,
    bucket: UserTimeBucket,
) -> UserTimeEvent | None:
    """Find unmatched credit for a source across all users/periods."""
    events = (
        db.query(UserTimeEvent)
        .filter(
            UserTimeEvent.source_id == source_id,
            UserTimeEvent.bucket == bucket,
            UserTimeEvent.kind.in_(
                [UserTimeEventKind.credit, UserTimeEventKind.reverse]
            ),
        )
        .order_by(UserTimeEvent.created_at.asc(), UserTimeEvent.id.asc())
        .all()
    )
    stack: list[UserTimeEvent] = []
    for e in events:
        if e.kind == UserTimeEventKind.credit:
            stack.append(e)
        elif e.kind == UserTimeEventKind.reverse and stack:
            stack.pop()
    return stack[-1] if stack else None


def credit_done(
    db: Session,
    *,
    user: User,
    source: Source,
    created_by: User,
) -> UserTimeEvent | None:
    events = _events_for_user(db, user.id)
    if _unmatched_credit(events, bucket=UserTimeBucket.done, source_id=source.id):
        return None
    audio = source_net_audio_sec(db, source)
    if audio <= 0:
        return None
    event = UserTimeEvent(
        user_id=user.id,
        kind=UserTimeEventKind.credit,
        bucket=UserTimeBucket.done,
        audio_sec=audio,
        source_id=source.id,
        created_by_user_id=created_by.id,
    )
    db.add(event)
    db.flush()
    return event


def reverse_done_for_source(
    db: Session, *, source: Source, created_by: User | None = None
) -> UserTimeEvent | None:
    credit = _unmatched_credit_any_period(
        db, source_id=source.id, bucket=UserTimeBucket.done
    )
    if not credit:
        return None
    event = UserTimeEvent(
        user_id=credit.user_id,
        kind=UserTimeEventKind.reverse,
        bucket=UserTimeBucket.done,
        audio_sec=float(credit.audio_sec),
        source_id=source.id,
        related_event_id=credit.id,
        created_by_user_id=created_by.id if created_by else credit.created_by_user_id,
    )
    db.add(event)
    db.flush()
    return event


def move_done_to_validated(
    db: Session,
    *,
    source: Source,
    created_by: User,
) -> UserTimeEvent | None:
    """Reverse Done credit and credit Validated with net recalculated at validation."""
    ever = _unmatched_credit_any_period(
        db, source_id=source.id, bucket=UserTimeBucket.validated
    )
    if ever:
        reverse_done_for_source(db, source=source, created_by=created_by)
        return None

    done_credit = _unmatched_credit_any_period(
        db, source_id=source.id, bucket=UserTimeBucket.done
    )
    if not done_credit:
        return None

    operator_id = done_credit.user_id
    done_audio = float(done_credit.audio_sec)

    db.add(
        UserTimeEvent(
            user_id=operator_id,
            kind=UserTimeEventKind.reverse,
            bucket=UserTimeBucket.done,
            audio_sec=done_audio,
            source_id=source.id,
            related_event_id=done_credit.id,
            created_by_user_id=created_by.id,
        )
    )
    db.flush()

    net = source_net_audio_sec(db, source)
    if net <= 0:
        return None

    events = _events_for_user(db, operator_id)
    start_idx, _base = _period_start_index(events)
    if _unmatched_credit(
        events, bucket=UserTimeBucket.validated, source_id=source.id, start_idx=start_idx
    ):
        return None

    validated = UserTimeEvent(
        user_id=operator_id,
        kind=UserTimeEventKind.credit,
        bucket=UserTimeBucket.validated,
        audio_sec=net,
        source_id=source.id,
        created_by_user_id=created_by.id,
    )
    db.add(validated)
    db.flush()
    return validated


def reverse_validated_for_source(
    db: Session, *, source: Source, created_by: User | None = None
) -> UserTimeEvent | None:
    """Reverse validated credit only if it sits in the current payable period."""
    credit = _unmatched_credit_any_period(
        db, source_id=source.id, bucket=UserTimeBucket.validated
    )
    if not credit:
        return None
    events = _events_for_user(db, credit.user_id)
    start_idx, _base = _period_start_index(events)
    period_ids = {e.id for e in events[start_idx:]}
    if credit.id not in period_ids:
        return None
    if not _unmatched_credit(
        events,
        bucket=UserTimeBucket.validated,
        source_id=source.id,
        start_idx=start_idx,
    ):
        return None
    event = UserTimeEvent(
        user_id=credit.user_id,
        kind=UserTimeEventKind.reverse,
        bucket=UserTimeBucket.validated,
        audio_sec=float(credit.audio_sec),
        source_id=source.id,
        related_event_id=credit.id,
        created_by_user_id=created_by.id if created_by else credit.created_by_user_id,
    )
    db.add(event)
    db.flush()
    return event


def _period_started_at(db: Session, user_id: int) -> datetime | None:
    events = _events_for_user(db, user_id)
    start_idx, _base = _period_start_index(events)
    for e in events[start_idx:]:
        if e.bucket == UserTimeBucket.validated and e.kind == UserTimeEventKind.credit:
            return e.created_at
    last = last_period_event(db, user_id)
    return last.created_at if last else None


def reset_validated(
    db: Session,
    *,
    user: User,
    created_by: User,
    note: str | None = None,
) -> tuple[UserTimeEvent, PaymentPeriod]:
    current = validated_audio_sec(db, user.id)
    rate = float(user.hourly_rate_mur or 0)
    amount = mur_for_sec(user, current)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    started = _period_started_at(db, user.id)

    event = UserTimeEvent(
        user_id=user.id,
        kind=UserTimeEventKind.reset,
        bucket=None,
        audio_sec=current,
        source_id=None,
        created_by_user_id=created_by.id,
    )
    db.add(event)
    db.flush()

    period = PaymentPeriod(
        user_id=user.id,
        reset_event_id=event.id,
        audio_sec=current,
        hourly_rate_mur=rate,
        amount_mur=amount,
        period_started_at=started,
        closed_at=now,
        created_by_user_id=created_by.id,
        note=(note or "").strip() or None,
    )
    db.add(period)
    db.flush()
    return event, period


def rollback_reset(db: Session, *, user: User, created_by: User) -> UserTimeEvent:
    if not can_rollback(db, user.id):
        raise UserTimeError("Nothing to roll back — latest period event is not a reset")
    reset_event = last_period_event(db, user.id)
    assert reset_event is not None

    period = (
        db.query(PaymentPeriod)
        .filter(
            PaymentPeriod.reset_event_id == reset_event.id,
            PaymentPeriod.rolled_back_at.is_(None),
        )
        .first()
    )
    if period:
        period.rolled_back_at = datetime.now(timezone.utc).replace(tzinfo=None)

    event = UserTimeEvent(
        user_id=user.id,
        kind=UserTimeEventKind.rollback,
        bucket=None,
        audio_sec=float(reset_event.audio_sec),
        source_id=None,
        related_event_id=reset_event.id,
        created_by_user_id=created_by.id,
    )
    db.add(event)
    db.flush()
    return event


def user_time_summary(db: Session, user: User) -> dict:
    done_sec = done_audio_sec(db, user.id)
    val_sec = validated_audio_sec(db, user.id)
    in_prog = in_progress_audio_sec(db, user.id)
    last = last_period_event(db, user.id)
    last_any = (
        db.query(UserTimeEvent)
        .filter(UserTimeEvent.user_id == user.id)
        .order_by(UserTimeEvent.created_at.desc(), UserTimeEvent.id.desc())
        .first()
    )
    return {
        "hourly_rate_mur": float(user.hourly_rate_mur or 0),
        "in_progress_audio_sec": in_prog,
        "in_progress_hours": in_prog / 3600.0,
        "in_progress_mur": mur_for_sec(user, in_prog),
        "done_audio_sec": done_sec,
        "done_hours": done_sec / 3600.0,
        "done_mur": mur_for_sec(user, done_sec),
        "validated_audio_sec": val_sec,
        "validated_hours": val_sec / 3600.0,
        "owed_mur": mur_for_sec(user, val_sec),
        "can_rollback": can_rollback(db, user.id),
        "last_event_kind": last_any.kind.value if last_any else None,
        "last_event_at": last_any.created_at if last_any else None,
        "last_period_kind": last.kind.value if last else None,
        "last_period_at": last.created_at if last else None,
    }


def list_time_events(db: Session, user_id: int) -> list[UserTimeEvent]:
    return (
        db.query(UserTimeEvent)
        .filter(UserTimeEvent.user_id == user_id)
        .order_by(UserTimeEvent.created_at.desc(), UserTimeEvent.id.desc())
        .all()
    )


def list_payment_periods(db: Session, user_id: int) -> list[PaymentPeriod]:
    return (
        db.query(PaymentPeriod)
        .filter(PaymentPeriod.user_id == user_id)
        .order_by(PaymentPeriod.closed_at.desc(), PaymentPeriod.id.desc())
        .all()
    )
