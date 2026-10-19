"""Cleanup audit / search-replace tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.annotator.api.cleanup import (
    SearchSpec,
    SegmentFilter,
    audit_find,
    bulk_ignore_segments,
    keep_segments,
    replace_apply,
    replace_preview,
    rollback_batch,
    search_segments,
    unkeep_segments,
)
from apps.annotator.db.models import (
    Base,
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
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed(db: Session) -> tuple[User, Source, list[Segment]]:
    user = User(
        email="admin@test.com",
        password_hash="x",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(user)
    db.flush()
    source = Source(
        source_type=SourceType.upload,
        title="Test",
        status=SourceStatus.ready,
        review_status=ReviewStatus.todo,
        duration_sec=10,
    )
    db.add(source)
    db.flush()
    speaker = Speaker(source_id=source.id, label="S1", color="#000")
    db.add(speaker)
    db.flush()
    segs = [
        Segment(
            source_id=source.id,
            speaker_id=speaker.id,
            start_sec=0.0,
            end_sec=0.5,
            text_raw="wi",
            text_corrected="wi",
            lang=SegmentLang.kreol,
            status=SegmentStatus.corrected,
        ),
        Segment(
            source_id=source.id,
            speaker_id=speaker.id,
            start_sec=1.0,
            end_sec=3.0,
            text_raw="mwen manje",
            text_corrected="mwen manje",
            lang=SegmentLang.kreol,
            status=SegmentStatus.corrected,
        ),
        Segment(
            source_id=source.id,
            speaker_id=speaker.id,
            start_sec=3.0,
            end_sec=3.4,
            text_raw="non",
            text_corrected="non",
            lang=SegmentLang.kreol,
            status=SegmentStatus.raw,
        ),
    ]
    db.add_all(segs)
    db.commit()
    for s in segs:
        db.refresh(s)
    db.refresh(user)
    db.refresh(source)
    return user, source, segs


def test_short_segment_rule_and_keep(db: Session) -> None:
    user, _source, segs = _seed(db)
    filt = SegmentFilter(include_validated_sources=True)
    rows = audit_find(
        db, rule_id="short_segment", filt=filt, params={"max_sec": 1.0}
    )
    ids = {r["segment_id"] for r in rows}
    assert segs[0].id in ids
    assert segs[2].id in ids
    assert segs[1].id not in ids

    keep_segments(db, rule_id="short_segment", segment_ids=[segs[0].id], user=user)
    rows2 = audit_find(
        db, rule_id="short_segment", filt=filt, params={"max_sec": 1.0}
    )
    assert segs[0].id not in {r["segment_id"] for r in rows2}

    rows3 = audit_find(
        db,
        rule_id="short_segment",
        filt=filt,
        params={"max_sec": 1.0},
        include_kept=True,
    )
    kept = next(r for r in rows3 if r["segment_id"] == segs[0].id)
    assert kept["kept"] is True

    unkeep_segments(db, rule_id="short_segment", segment_ids=[segs[0].id])
    rows4 = audit_find(
        db, rule_id="short_segment", filt=filt, params={"max_sec": 1.0}
    )
    assert segs[0].id in {r["segment_id"] for r in rows4}


def test_dense_text_rule(db: Session) -> None:
    user, source, segs = _seed(db)
    # Make first short segment densly hallucinated
    segs[0].text_corrected = "x" * 50  # 0.5s → 100 chars/s
    # Longer segment with lots of text should be excluded by max_sec
    segs[1].text_corrected = "y" * 200
    db.commit()

    filt = SegmentFilter(include_validated_sources=True)
    rows = audit_find(
        db,
        rule_id="dense_text",
        filt=filt,
        params={"max_sec": 2.0, "min_chars_per_sec": 40},
    )
    ids = {r["segment_id"] for r in rows}
    assert segs[0].id in ids
    assert segs[1].id not in ids  # 2s duration, max_sec=2 means < 2
    assert segs[2].id not in ids  # "non" is low density
    dense = next(r for r in rows if r["segment_id"] == segs[0].id)
    assert dense["chars_per_sec"] == 100.0
    assert dense["char_count"] == 50

    keep_segments(db, rule_id="dense_text", segment_ids=[segs[0].id], user=user)
    rows2 = audit_find(
        db,
        rule_id="dense_text",
        filt=filt,
        params={"max_sec": 2.0, "min_chars_per_sec": 40},
    )
    assert segs[0].id not in {r["segment_id"] for r in rows2}


def test_bulk_ignore(db: Session) -> None:
    user, _source, segs = _seed(db)
    n = bulk_ignore_segments(db, segment_ids=[segs[0].id], user=user)
    assert n == 1
    db.refresh(segs[0])
    assert segs[0].status == SegmentStatus.ignored


def test_search_and_replace_rollback(db: Session) -> None:
    user, _source, segs = _seed(db)
    filt = SegmentFilter(include_validated_sources=True)
    spec = SearchSpec(query="mwen", mode="word")
    hits = search_segments(db, spec=spec, filt=filt)
    assert any(h["segment_id"] == segs[1].id for h in hits)

    previews = replace_preview(db, spec=spec, replacement="mo", filt=filt)
    target = next(p for p in previews if p["segment_id"] == segs[1].id)
    assert "mo manje" in target["text_after"]

    result = replace_apply(
        db,
        spec=spec,
        replacement="mo",
        items=[
            {
                "segment_id": segs[1].id,
                "text_before": target["text_before"],
            }
        ],
        user=user,
    )
    assert result["applied"] == 1
    db.refresh(segs[1])
    assert segs[1].text_corrected == "mo manje"

    # Skip when text changed since preview
    result2 = replace_apply(
        db,
        spec=spec,
        replacement="mo",
        items=[
            {
                "segment_id": segs[1].id,
                "text_before": "mwen manje",  # stale
            }
        ],
        user=user,
    )
    assert result2["applied"] == 0
    assert result2["skipped"][0]["reason"] == "text_changed"

    rb = rollback_batch(db, batch_id=result["batch_id"], user=user)
    assert rb["restored"] == 1
    db.refresh(segs[1])
    assert segs[1].text_corrected == "mwen manje"
