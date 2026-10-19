from apps.annotator.api.lexicon import get_lexicon
from apps.annotator.config import get_settings
from apps.annotator.db.models import Segment, SegmentStatus
from normalizer import LortografNormalizer
from normalizer.normalizer import NormalizeResult
from sqlalchemy.orm import Session


def _get_normalizer(db: Session | None = None) -> LortografNormalizer:
    settings = get_settings()
    return LortografNormalizer(
        lexicon=get_lexicon(db),
        use_llm=settings.lortograf_use_llm,
    )


def _result_to_preview(segment_id: int, result: NormalizeResult) -> dict:
    return {
        "segment_id": segment_id,
        "original": result.original,
        "proposed": result.normalized,
        "changed": result.changed,
        "changes": [
            {
                "original": c.original,
                "normalized": c.normalized,
                "start": c.start,
                "end": c.end,
            }
            for c in result.changes
        ],
        "unknown_tokens": result.unknown_tokens,
    }


def normalize_segment(
    db: Session,
    segment_id: int,
    apply: bool = False,
    text: str | None = None,
) -> dict | None:
    segment = db.get(Segment, segment_id)
    if not segment:
        return None
    if segment.status == SegmentStatus.ignored:
        base = segment.text_corrected or segment.text_raw or ""
        draft = text if text is not None else base
        return _result_to_preview(
            segment_id,
            NormalizeResult(original=draft, normalized=draft),
        )

    if text is not None:
        if apply:
            raise ValueError("Cannot apply normalization with draft text; save first or omit text")
        draft = text
    else:
        draft = segment.text_corrected or segment.text_raw or ""

    normalizer = _get_normalizer(db)
    result = normalizer.normalize_text(draft, lang=segment.lang.value)

    if apply and result.changed:
        segment.text_corrected = result.normalized
        if segment.status == SegmentStatus.raw:
            segment.status = SegmentStatus.corrected
        db.commit()
        db.refresh(segment)

    return _result_to_preview(segment_id, result)


def normalize_source(db: Session, source_id: int, apply: bool = False) -> dict:
    segments = (
        db.query(Segment)
        .filter(Segment.source_id == source_id)
        .order_by(Segment.start_sec)
        .all()
    )
    normalizer = _get_normalizer(db)
    previews = []
    applied = 0

    for segment in segments:
        if segment.status == SegmentStatus.ignored:
            continue
        if not normalizer.should_normalize_lang(segment.lang.value):
            continue
        text = segment.text_corrected or segment.text_raw or ""
        result = normalizer.normalize_text(text, lang=segment.lang.value)
        previews.append(_result_to_preview(segment.id, result))
        if apply and result.changed:
            segment.text_corrected = result.normalized
            if segment.status == SegmentStatus.raw:
                segment.status = SegmentStatus.corrected
            applied += 1

    if apply and applied:
        db.commit()

    return {"previews": previews, "applied_count": applied}


def export_normalization_check(db: Session, source_id: int) -> dict:
    segments = (
        db.query(Segment)
        .filter(
            Segment.source_id == source_id,
            Segment.status == SegmentStatus.validated,
        )
        .order_by(Segment.start_sec)
        .all()
    )
    normalizer = _get_normalizer(db)
    needs: list[int] = []

    for segment in segments:
        if not normalizer.should_normalize_lang(segment.lang.value):
            continue
        text = segment.text_corrected or segment.text_raw or ""
        result = normalizer.normalize_text(text, lang=segment.lang.value)
        if result.changed:
            needs.append(segment.id)

    return {
        "validated_count": len(segments),
        "needs_normalization_count": len(needs),
        "segment_ids": needs,
    }


def normalization_warnings(db: Session, source_id: int) -> list[str]:
    check = export_normalization_check(db, source_id)
    if check["needs_normalization_count"] == 0:
        return []
    return [
        f"{check['needs_normalization_count']} validated Kreol/mix segment(s) "
        "still have non-Lortograf spelling"
    ]
