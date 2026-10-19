"""Payroll audio-hours ledger: net time, assignment, payment snapshots."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.annotator.api.assignment import AssignmentError, set_source_assignment
from apps.annotator.api.user_time import (
    UserTimeError,
    credit_done,
    done_audio_sec,
    in_progress_audio_sec,
    list_payment_periods,
    move_done_to_validated,
    mur_for_sec,
    owed_mur,
    reset_validated,
    reverse_done_for_source,
    reverse_validated_for_source,
    rollback_reset,
    source_net_audio_sec,
    validated_audio_sec,
)
from apps.annotator.db.models import (
    Base,
    PaymentPeriod,
    ReviewStatus,
    Segment,
    SegmentLang,
    SegmentStatus,
    Source,
    SourceStatus,
    SourceType,
    Speaker,
    User,
    UserRole,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db: Session, email: str = "op@example.com") -> User:
    u = User(
        email=email,
        password_hash="x",
        role=UserRole.operator,
        is_active=True,
        hourly_rate_mur=100,
    )
    db.add(u)
    db.flush()
    return u


def _admin(db: Session) -> User:
    u = User(
        email="admin@example.com",
        password_hash="x",
        role=UserRole.admin,
        is_active=True,
        hourly_rate_mur=0,
    )
    db.add(u)
    db.flush()
    return u


def _source(
    db: Session,
    *,
    duration: float = 3600.0,
    assigned: User | None = None,
    review: ReviewStatus = ReviewStatus.todo,
) -> Source:
    s = Source(
        source_type=SourceType.upload,
        status=SourceStatus.ready,
        duration_sec=duration,
        title="t",
        review_status=review,
        assigned_to_user_id=assigned.id if assigned else None,
    )
    db.add(s)
    db.flush()
    return s


def _seg(
    db: Session,
    source: Source,
    *,
    start: float,
    end: float,
    text: str = "hello",
    status: SegmentStatus = SegmentStatus.corrected,
) -> Segment:
    sp = (
        db.query(Speaker).filter(Speaker.source_id == source.id).first()
    )
    if not sp:
        sp = Speaker(source_id=source.id, label="S1", color="#000")
        db.add(sp)
        db.flush()
    seg = Segment(
        source_id=source.id,
        speaker_id=sp.id,
        start_sec=start,
        end_sec=end,
        text_raw=text,
        text_corrected=text,
        lang=SegmentLang.mix,
        status=status,
    )
    db.add(seg)
    db.flush()
    return seg


def test_net_excludes_ignored_and_empty(db: Session):
    op = _user(db)
    source = _source(db, assigned=op)
    _seg(db, source, start=0, end=100, text="ok")
    _seg(db, source, start=100, end=200, text="x", status=SegmentStatus.ignored)
    _seg(db, source, start=200, end=350, text="", status=SegmentStatus.corrected)
    assert source_net_audio_sec(db, source) == 100


def test_credit_done_and_validate_moves_buckets(db: Session):
    op = _user(db)
    admin = _admin(db)
    source = _source(db, assigned=op)
    _seg(db, source, start=0, end=1800)

    credit_done(db, user=op, source=source, created_by=op)
    db.flush()
    assert done_audio_sec(db, op.id) == 1800
    assert validated_audio_sec(db, op.id) == 0

    move_done_to_validated(db, source=source, created_by=admin)
    db.flush()
    assert done_audio_sec(db, op.id) == 0
    assert validated_audio_sec(db, op.id) == 1800
    assert owed_mur(op, 1800) == 50.0


def test_validate_recalculates_net_after_ignore(db: Session):
    op = _user(db)
    admin = _admin(db)
    source = _source(db, assigned=op)
    a = _seg(db, source, start=0, end=600)
    _seg(db, source, start=600, end=1000)

    credit_done(db, user=op, source=source, created_by=op)
    db.flush()
    assert done_audio_sec(db, op.id) == 1000

    a.status = SegmentStatus.ignored
    db.flush()
    move_done_to_validated(db, source=source, created_by=admin)
    db.flush()
    assert validated_audio_sec(db, op.id) == 400


def test_in_progress_assigned_todo_only(db: Session):
    op = _user(db)
    other = _user(db, "other@example.com")
    mine = _source(db, assigned=op)
    theirs = _source(db, assigned=other)
    _seg(db, mine, start=0, end=120, status=SegmentStatus.corrected)
    _seg(db, theirs, start=0, end=999, status=SegmentStatus.corrected)
    assert in_progress_audio_sec(db, op.id) == 120


def test_reopen_done_reverses(db: Session):
    op = _user(db)
    source = _source(db, assigned=op)
    _seg(db, source, start=0, end=600)
    credit_done(db, user=op, source=source, created_by=op)
    db.flush()
    reverse_done_for_source(db, source=source, created_by=op)
    db.flush()
    assert done_audio_sec(db, op.id) == 0


def test_no_double_credit_while_done(db: Session):
    op = _user(db)
    source = _source(db, assigned=op)
    _seg(db, source, start=0, end=100)
    assert credit_done(db, user=op, source=source, created_by=op) is not None
    assert credit_done(db, user=op, source=source, created_by=op) is None
    db.flush()
    assert done_audio_sec(db, op.id) == 100


def test_reset_creates_payment_period(db: Session):
    op = _user(db)
    admin = _admin(db)
    s = _source(db, assigned=op)
    _seg(db, s, start=0, end=3600)
    credit_done(db, user=op, source=s, created_by=op)
    move_done_to_validated(db, source=s, created_by=admin)
    db.flush()

    _event, period = reset_validated(db, user=op, created_by=admin, note="March pay")
    db.flush()
    assert validated_audio_sec(db, op.id) == 0
    assert float(period.audio_sec) == 3600
    assert float(period.hourly_rate_mur) == 100
    assert float(period.amount_mur) == 100.0
    assert period.note == "March pay"
    assert list_payment_periods(db, op.id)[0].id == period.id


def test_rollback_marks_period(db: Session):
    op = _user(db)
    admin = _admin(db)
    s = _source(db, assigned=op)
    _seg(db, s, start=0, end=7200)
    credit_done(db, user=op, source=s, created_by=op)
    move_done_to_validated(db, source=s, created_by=admin)
    db.flush()
    reset_validated(db, user=op, created_by=admin)
    db.flush()
    assert validated_audio_sec(db, op.id) == 0

    rollback_reset(db, user=op, created_by=admin)
    db.flush()
    assert validated_audio_sec(db, op.id) == 7200
    period = db.query(PaymentPeriod).one()
    assert period.rolled_back_at is not None

    with pytest.raises(UserTimeError):
        rollback_reset(db, user=op, created_by=admin)


def test_reopen_validated_in_period_reverses(db: Session):
    op = _user(db)
    admin = _admin(db)
    s = _source(db, assigned=op)
    _seg(db, s, start=0, end=300)
    credit_done(db, user=op, source=s, created_by=op)
    move_done_to_validated(db, source=s, created_by=admin)
    db.flush()
    reverse_validated_for_source(db, source=s, created_by=admin)
    db.flush()
    assert validated_audio_sec(db, op.id) == 0


def test_paid_validated_not_reversed_after_reset(db: Session):
    op = _user(db)
    admin = _admin(db)
    s = _source(db, assigned=op)
    _seg(db, s, start=0, end=400)
    credit_done(db, user=op, source=s, created_by=op)
    move_done_to_validated(db, source=s, created_by=admin)
    reset_validated(db, user=op, created_by=admin)
    db.flush()
    assert reverse_validated_for_source(db, source=s, created_by=admin) is None
    assert validated_audio_sec(db, op.id) == 0
    credit_done(db, user=op, source=s, created_by=op)
    move_done_to_validated(db, source=s, created_by=admin)
    db.flush()
    assert validated_audio_sec(db, op.id) == 0
    assert done_audio_sec(db, op.id) == 0


def test_claim_operator(db: Session):
    op = _user(db)
    admin = _admin(db)
    source = _source(db)
    set_source_assignment(db, source, assigned_to_user_id=op.id, actor=op)
    assert source.assigned_to_user_id == op.id

    other = _user(db, "o2@example.com")
    with pytest.raises(AssignmentError):
        set_source_assignment(db, source, assigned_to_user_id=other.id, actor=other)


def test_assign_blocked_when_done(db: Session):
    op = _user(db)
    admin = _admin(db)
    source = _source(db, assigned=op, review=ReviewStatus.done)
    with pytest.raises(AssignmentError):
        set_source_assignment(db, source, assigned_to_user_id=None, actor=admin)


def test_mur_for_sec(db: Session):
    op = _user(db)
    assert mur_for_sec(op, 1800) == 50.0
