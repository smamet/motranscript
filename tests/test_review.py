"""Review workflow transitions and helpers."""

import pytest

from apps.annotator.api.review import (
    ReviewError,
    _admin_transition_ok,
    _operator_transition_ok,
    is_partial,
    is_segment_touched,
)
from apps.annotator.db.models import (
    ReviewStatus,
    Segment,
    SegmentStatus,
    Source,
    SourceStatus,
    SourceType,
)


def test_operator_transitions():
    assert _operator_transition_ok(ReviewStatus.todo, ReviewStatus.done)
    assert _operator_transition_ok(ReviewStatus.done, ReviewStatus.todo)
    assert not _operator_transition_ok(ReviewStatus.done, ReviewStatus.validated)
    assert not _operator_transition_ok(ReviewStatus.todo, ReviewStatus.validated)


def test_admin_transitions():
    assert _admin_transition_ok(ReviewStatus.done, ReviewStatus.validated)
    assert _admin_transition_ok(ReviewStatus.validated, ReviewStatus.todo)
    assert _admin_transition_ok(ReviewStatus.done, ReviewStatus.todo)
    assert not _admin_transition_ok(ReviewStatus.todo, ReviewStatus.validated)


def test_is_segment_touched():
    raw = Segment(
        source_id=1,
        speaker_id=1,
        start_sec=0,
        end_sec=1,
        status=SegmentStatus.raw,
        annotator=None,
    )
    assert not is_segment_touched(raw)
    raw.annotator = "op@example.com"
    assert is_segment_touched(raw)
    raw.annotator = None
    raw.status = SegmentStatus.corrected
    assert is_segment_touched(raw)


def test_is_partial():
    source = Source(
        source_type=SourceType.upload,
        status=SourceStatus.ready,
        review_status=ReviewStatus.todo,
    )
    assert is_partial(source, touched=3, total=10)
    assert is_partial(source, touched=3, total=10, ready_count=3)
    assert not is_partial(source, touched=0, total=10)
    assert not is_partial(source, touched=10, total=10, ready_count=10)
    source.review_status = ReviewStatus.done
    assert not is_partial(source, touched=3, total=10)


def test_can_mark_done_requires_all_corrected_or_validated():
    from apps.annotator.api.review import can_mark_done, is_segment_ready_for_done

    source = Source(
        source_type=SourceType.upload,
        status=SourceStatus.ready,
        review_status=ReviewStatus.todo,
        assigned_to_user_id=1,
    )
    assert not can_mark_done(source, ready_count=3, total=10)
    assert can_mark_done(source, ready_count=10, total=10)
    assert not can_mark_done(source, ready_count=0, total=0)
    source.assigned_to_user_id = None
    assert not can_mark_done(source, ready_count=10, total=10)

    raw = Segment(
        source_id=1,
        speaker_id=1,
        start_sec=0,
        end_sec=1,
        status=SegmentStatus.raw,
    )
    assert not is_segment_ready_for_done(raw)
    raw.status = SegmentStatus.corrected
    assert is_segment_ready_for_done(raw)
    raw.status = SegmentStatus.validated
    assert is_segment_ready_for_done(raw)
    raw.status = SegmentStatus.ignored
    assert is_segment_ready_for_done(raw)


def test_ignored_counts_as_touched_and_ready():
    from apps.annotator.api.review import can_validate_segment, is_segment_ready_for_done

    ignored = Segment(
        source_id=1,
        speaker_id=1,
        start_sec=0,
        end_sec=1,
        status=SegmentStatus.ignored,
        text_raw="",
        text_corrected=None,
    )
    assert is_segment_touched(ignored)
    assert is_segment_ready_for_done(ignored)
    assert not can_validate_segment(ignored)
    ignored.text_raw = "bonjour"
    assert can_validate_segment(ignored)


def test_review_error_type():
    with pytest.raises(ReviewError):
        raise ReviewError("boom")
