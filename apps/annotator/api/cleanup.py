"""Data cleanup: audit rules, vocabulary stats, search/replace."""

from __future__ import annotations

import re
import time
import uuid
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.annotator.api.lexicon import get_lexicon
from apps.annotator.config import get_settings
from apps.annotator.db.models import (
    ReviewStatus,
    Segment,
    SegmentAuditDismissal,
    SegmentLang,
    SegmentSplit,
    SegmentStatus,
    Source,
    TextRevision,
    TextRevisionKind,
    User,
)
from normalizer.normalizer import tokenize_words
from normalizer.phonetic import phonetic_key, strip_accents
from sqlalchemy import func
from sqlalchemy.orm import Query, Session, joinedload

# ---------------------------------------------------------------------------
# Shared segment filter
# ---------------------------------------------------------------------------


@dataclass
class SegmentFilter:
    source_id: int | None = None
    category_id: int | None = None
    lang: list[str] | None = None
    status: list[str] | None = None
    review_status: list[str] | None = None
    split: list[str] | None = None
    include_validated_sources: bool = False


def apply_segment_filter(query: Query, f: SegmentFilter) -> Query:
    query = query.join(Source, Segment.source_id == Source.id)
    if f.source_id is not None:
        query = query.filter(Segment.source_id == f.source_id)
    if f.category_id is not None:
        query = query.filter(Source.category_id == f.category_id)
    if f.lang:
        query = query.filter(Segment.lang.in_([SegmentLang(x) for x in f.lang]))
    if f.status:
        query = query.filter(Segment.status.in_([SegmentStatus(x) for x in f.status]))
    if f.split:
        query = query.filter(Segment.split.in_([SegmentSplit(x) for x in f.split]))
    if f.review_status:
        query = query.filter(
            Source.review_status.in_([ReviewStatus(x) for x in f.review_status])
        )
    elif not f.include_validated_sources:
        query = query.filter(Source.review_status != ReviewStatus.validated)
    return query


def segment_text(seg: Segment) -> str:
    return seg.text_corrected if seg.text_corrected is not None else (seg.text_raw or "")


# ---------------------------------------------------------------------------
# Audit rules
# ---------------------------------------------------------------------------


class AuditRule(ABC):
    id: str
    label: str

    @abstractmethod
    def find(self, db: Session, filt: SegmentFilter, params: dict[str, Any]) -> Query: ...

    def accept(self, seg: Segment, params: dict[str, Any]) -> bool:
        """Optional post-filter after the SQL query (default: keep all)."""
        return True

    def row_extra(self, seg: Segment, params: dict[str, Any]) -> dict[str, Any]:
        return {}


class ShortSegmentRule(AuditRule):
    id = "short_segment"
    label = "Short segments"

    def find(self, db: Session, filt: SegmentFilter, params: dict[str, Any]) -> Query:
        max_sec = float(params.get("max_sec", 1.0))
        query = db.query(Segment).options(joinedload(Segment.source))
        query = apply_segment_filter(query, filt)
        query = query.filter(Segment.status != SegmentStatus.ignored)
        query = query.filter((Segment.end_sec - Segment.start_sec) < max_sec)
        return query.order_by(Segment.end_sec - Segment.start_sec)


class DenseTextRule(AuditRule):
    """Short clips with abnormally high chars/sec — typical Whisper hallucination."""

    id = "dense_text"
    label = "Dense text (likely noise)"

    def find(self, db: Session, filt: SegmentFilter, params: dict[str, Any]) -> Query:
        max_sec = float(params.get("max_sec", 2.0))
        query = db.query(Segment).options(joinedload(Segment.source))
        query = apply_segment_filter(query, filt)
        query = query.filter(Segment.status != SegmentStatus.ignored)
        query = query.filter((Segment.end_sec - Segment.start_sec) < max_sec)
        query = query.filter((Segment.end_sec - Segment.start_sec) > 0)
        return query.order_by(Segment.start_sec)

    def accept(self, seg: Segment, params: dict[str, Any]) -> bool:
        min_cps = float(params.get("min_chars_per_sec", 40.0))
        duration = seg.end_sec - seg.start_sec
        if duration <= 0:
            return False
        text = segment_text(seg).strip()
        if not text:
            return False
        return (len(text) / duration) >= min_cps

    def row_extra(self, seg: Segment, params: dict[str, Any]) -> dict[str, Any]:
        duration = max(seg.end_sec - seg.start_sec, 1e-6)
        text = segment_text(seg)
        cps = len(text) / duration
        return {
            "chars_per_sec": round(cps, 1),
            "char_count": len(text),
        }


AUDIT_RULES: dict[str, AuditRule] = {
    ShortSegmentRule.id: ShortSegmentRule(),
    DenseTextRule.id: DenseTextRule(),
}


def list_audit_rules() -> list[dict]:
    return [{"id": r.id, "label": r.label} for r in AUDIT_RULES.values()]


def audit_find(
    db: Session,
    *,
    rule_id: str,
    filt: SegmentFilter,
    params: dict[str, Any],
    include_kept: bool = False,
) -> list[dict]:
    rule = AUDIT_RULES.get(rule_id)
    if not rule:
        raise ValueError(f"Unknown rule: {rule_id}")

    segments = [s for s in rule.find(db, filt, params).all() if rule.accept(s, params)]
    # Dense text: highest chars/sec first
    if rule_id == "dense_text":
        segments.sort(
            key=lambda s: len(segment_text(s)) / max(s.end_sec - s.start_sec, 1e-6),
            reverse=True,
        )

    kept_ids: set[int] = set()
    if segments:
        kept_ids = {
            row.segment_id
            for row in db.query(SegmentAuditDismissal)
            .filter(
                SegmentAuditDismissal.rule_id == rule_id,
                SegmentAuditDismissal.segment_id.in_([s.id for s in segments]),
            )
            .all()
        }

    rows: list[dict] = []
    for seg in segments:
        kept = seg.id in kept_ids
        if kept and not include_kept:
            continue
        source = seg.source
        row = {
            "segment_id": seg.id,
            "source_id": seg.source_id,
            "source_title": source.title if source else None,
            "review_status": source.review_status.value if source else "todo",
            "status": seg.status.value,
            "lang": seg.lang.value,
            "start_sec": seg.start_sec,
            "end_sec": seg.end_sec,
            "duration_sec": seg.end_sec - seg.start_sec,
            "text": segment_text(seg),
            "kept": kept,
        }
        row.update(rule.row_extra(seg, params))
        rows.append(row)
    return rows


def keep_segments(
    db: Session,
    *,
    rule_id: str,
    segment_ids: list[int],
    user: User,
) -> int:
    if rule_id not in AUDIT_RULES:
        raise ValueError(f"Unknown rule: {rule_id}")
    added = 0
    for sid in segment_ids:
        existing = (
            db.query(SegmentAuditDismissal)
            .filter(
                SegmentAuditDismissal.segment_id == sid,
                SegmentAuditDismissal.rule_id == rule_id,
            )
            .one_or_none()
        )
        if existing:
            continue
        db.add(
            SegmentAuditDismissal(
                segment_id=sid,
                rule_id=rule_id,
                created_by_user_id=user.id,
            )
        )
        added += 1
    db.commit()
    return added


def unkeep_segments(db: Session, *, rule_id: str, segment_ids: list[int]) -> int:
    if rule_id not in AUDIT_RULES:
        raise ValueError(f"Unknown rule: {rule_id}")
    deleted = (
        db.query(SegmentAuditDismissal)
        .filter(
            SegmentAuditDismissal.rule_id == rule_id,
            SegmentAuditDismissal.segment_id.in_(segment_ids),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted)


def bulk_ignore_segments(db: Session, *, segment_ids: list[int], user: User) -> int:
    updated = 0
    for sid in segment_ids:
        seg = db.get(Segment, sid)
        if not seg:
            continue
        seg.status = SegmentStatus.ignored
        seg.annotator = user.email
        updated += 1
    db.commit()
    return updated


def ensure_segment_clip(db: Session, segment_id: int) -> Path | None:
    """Return path to a WAV clip for the segment (cached or cut on demand)."""
    from apps.annotator.pipeline.segment_merger import SegmentMerger

    seg = db.get(Segment, segment_id)
    if not seg:
        return None
    if seg.audio_path and Path(seg.audio_path).exists():
        return Path(seg.audio_path)

    source = db.get(Source, seg.source_id)
    if not source or not source.audio_path or not Path(source.audio_path).exists():
        return None

    settings = get_settings()
    clip_dir = settings.segments_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    out = clip_dir / f"{segment_id}.wav"
    if not out.exists():
        SegmentMerger.cut_segment_wav(
            source.audio_path, str(out), seg.start_sec, seg.end_sec
        )
    return out


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

_vocab_cache: dict[str, tuple[float, list[dict]]] = {}
_VOCAB_TTL = 60.0


def _filter_cache_key(filt: SegmentFilter, extra: str = "") -> str:
    return (
        f"{filt.source_id}|{filt.category_id}|{filt.lang}|{filt.status}|"
        f"{filt.review_status}|{filt.split}|{filt.include_validated_sources}|{extra}"
    )


def vocabulary_stats(
    db: Session,
    *,
    filt: SegmentFilter,
    min_count: int = 1,
    lexicon_status: str = "all",
    q: str | None = None,
) -> list[dict]:
    cache_key = _filter_cache_key(filt, f"v|{min_count}|{lexicon_status}|{q}")
    now = time.time()
    cached = _vocab_cache.get(cache_key)
    if cached and now - cached[0] < _VOCAB_TTL:
        return cached[1]

    lexicon = get_lexicon(db)
    query = db.query(Segment)
    query = apply_segment_filter(query, filt)
    segments = query.all()

    counts: Counter[str] = Counter()
    segment_ids: dict[str, set[int]] = defaultdict(set)
    lang_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for seg in segments:
        text = segment_text(seg)
        seen_in_seg: set[str] = set()
        for word, _s, _e in tokenize_words(text):
            lower = strip_accents(word.lower())
            counts[lower] += 1
            seen_in_seg.add(lower)
            lang_counts[lower][seg.lang.value] += 1
        for w in seen_in_seg:
            segment_ids[w].add(seg.id)

    rows: list[dict] = []
    for word, count in counts.items():
        if count < min_count:
            continue
        if q and q.lower() not in word:
            continue
        status = lexicon.status_of(word)
        if lexicon_status != "all" and status != lexicon_status:
            continue
        canonical = lexicon.alias_of(word) if status == "alias" else (
            word if status == "official" else None
        )
        rows.append(
            {
                "word": word,
                "count": count,
                "segment_count": len(segment_ids[word]),
                "lang_counts": dict(lang_counts[word]),
                "lexicon_status": status,
                "canonical": canonical,
                "cluster_key": phonetic_key(word),
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["word"]))
    _vocab_cache[cache_key] = (now, rows)
    return rows


def vocabulary_clusters(
    db: Session,
    *,
    filt: SegmentFilter,
    min_size: int = 2,
) -> list[dict]:
    stats = vocabulary_stats(db, filt=filt, min_count=1)
    by_key: dict[str, list[dict]] = defaultdict(list)
    for row in stats:
        key = row["cluster_key"]
        if key:
            by_key[key].append(row)
    clusters: list[dict] = []
    for key, words in by_key.items():
        if len(words) < min_size:
            continue
        total = sum(w["count"] for w in words)
        words_sorted = sorted(words, key=lambda w: -w["count"])
        clusters.append(
            {
                "cluster_key": key,
                "total_count": total,
                "words": words_sorted,
            }
        )
    clusters.sort(key=lambda c: -c["total_count"])
    return clusters


def word_occurrences(
    db: Session,
    *,
    word: str,
    filt: SegmentFilter,
    limit: int = 100,
) -> list[dict]:
    word_l = strip_accents(word.lower())
    pattern = re.compile(rf"\b{re.escape(word_l)}\b", re.IGNORECASE)
    query = db.query(Segment).options(joinedload(Segment.source))
    query = apply_segment_filter(query, filt)
    hits: list[dict] = []
    for seg in query.all():
        text = segment_text(seg)
        matches = [
            {"start": m.start(), "end": m.end()}
            for m in pattern.finditer(text)
        ]
        if not matches:
            # Also try accent-stripped comparison via tokenize
            for tok, start, end in tokenize_words(text):
                if strip_accents(tok.lower()) == word_l:
                    matches.append({"start": start, "end": end})
        if not matches:
            continue
        source = seg.source
        hits.append(
            {
                "segment_id": seg.id,
                "source_id": seg.source_id,
                "source_title": source.title if source else None,
                "review_status": source.review_status.value if source else "todo",
                "status": seg.status.value,
                "lang": seg.lang.value,
                "text": text,
                "matches": matches,
            }
        )
        if len(hits) >= limit:
            break
    return hits


# ---------------------------------------------------------------------------
# Search & replace
# ---------------------------------------------------------------------------


@dataclass
class SearchSpec:
    query: str
    mode: str = "word"  # word | substring | regex
    case_sensitive: bool = False


def compile_pattern(spec: SearchSpec) -> re.Pattern[str]:
    flags = 0 if spec.case_sensitive else re.IGNORECASE
    if spec.mode == "word":
        return re.compile(rf"\b{re.escape(spec.query)}\b", flags)
    if spec.mode == "substring":
        return re.compile(re.escape(spec.query), flags)
    if spec.mode == "regex":
        try:
            return re.compile(spec.query, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regex: {exc}") from exc
    raise ValueError(f"Unknown search mode: {spec.mode}")


def search_segments(
    db: Session,
    *,
    spec: SearchSpec,
    filt: SegmentFilter,
    limit: int = 500,
) -> list[dict]:
    pattern = compile_pattern(spec)
    query = db.query(Segment).options(joinedload(Segment.source))
    query = apply_segment_filter(query, filt)
    hits: list[dict] = []
    for seg in query.all():
        text = segment_text(seg)
        matches = [{"start": m.start(), "end": m.end()} for m in pattern.finditer(text)]
        if not matches:
            continue
        source = seg.source
        hits.append(
            {
                "segment_id": seg.id,
                "source_id": seg.source_id,
                "source_title": source.title if source else None,
                "review_status": source.review_status.value if source else "todo",
                "status": seg.status.value,
                "lang": seg.lang.value,
                "text": text,
                "matches": matches,
            }
        )
        if len(hits) >= limit:
            break
    return hits


def replace_preview(
    db: Session,
    *,
    spec: SearchSpec,
    replacement: str,
    filt: SegmentFilter,
    limit: int = 500,
) -> list[dict]:
    pattern = compile_pattern(spec)
    query = db.query(Segment).options(joinedload(Segment.source))
    query = apply_segment_filter(query, filt)
    previews: list[dict] = []
    for seg in query.all():
        text = segment_text(seg)
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        text_after = pattern.sub(replacement, text)
        source = seg.source
        previews.append(
            {
                "segment_id": seg.id,
                "source_id": seg.source_id,
                "source_title": source.title if source else None,
                "review_status": source.review_status.value if source else "todo",
                "status": seg.status.value,
                "text_before": text,
                "text_after": text_after,
                "matches": [{"start": m.start(), "end": m.end()} for m in matches],
            }
        )
        if len(previews) >= limit:
            break
    return previews


def replace_apply(
    db: Session,
    *,
    spec: SearchSpec,
    replacement: str,
    items: list[dict],
    user: User,
) -> dict:
    """items: [{segment_id, text_before, match_indexes: list[int] | null}]"""
    pattern = compile_pattern(spec)
    batch_id = str(uuid.uuid4())
    applied = 0
    skipped: list[dict] = []

    for item in items:
        sid = int(item["segment_id"])
        expected_before = item.get("text_before")
        match_indexes: list[int] | None = item.get("match_indexes")
        seg = db.get(Segment, sid)
        if not seg:
            skipped.append({"segment_id": sid, "reason": "not_found"})
            continue
        if seg.locked_by and seg.locked_by != user.email:
            skipped.append({"segment_id": sid, "reason": "locked", "locked_by": seg.locked_by})
            continue
        current = segment_text(seg)
        if expected_before is not None and current != expected_before:
            skipped.append({"segment_id": sid, "reason": "text_changed"})
            continue

        matches = list(pattern.finditer(current))
        if not matches:
            skipped.append({"segment_id": sid, "reason": "no_matches"})
            continue

        if match_indexes is not None:
            indexes = set(match_indexes)
            # Rebuild by replacing selected matches only (from end)
            chars = list(current)
            selected = [m for i, m in enumerate(matches) if i in indexes]
            if not selected:
                skipped.append({"segment_id": sid, "reason": "no_selected_matches"})
                continue
            for m in reversed(selected):
                chars[m.start() : m.end()] = list(replacement)
            text_after = "".join(chars)
        else:
            text_after = pattern.sub(replacement, current)

        if text_after == current:
            skipped.append({"segment_id": sid, "reason": "unchanged"})
            continue

        status_before = seg.status
        db.add(
            TextRevision(
                batch_id=batch_id,
                segment_id=sid,
                text_before=current,
                text_after=text_after,
                status_before=status_before,
                kind=TextRevisionKind.replace,
                query=spec.query,
                replacement=replacement,
                created_by_user_id=user.id,
            )
        )
        seg.text_corrected = text_after
        if seg.status == SegmentStatus.raw:
            seg.status = SegmentStatus.corrected
        seg.annotator = user.email
        applied += 1

    if applied:
        db.commit()
    return {"batch_id": batch_id, "applied": applied, "skipped": skipped}


def list_revision_batches(db: Session, *, limit: int = 50) -> list[dict]:
    rows = (
        db.query(
            TextRevision.batch_id,
            func.min(TextRevision.created_at).label("created_at"),
            func.count(TextRevision.id).label("count"),
            func.min(TextRevision.query).label("query"),
            func.min(TextRevision.replacement).label("replacement"),
            func.min(TextRevision.kind).label("kind"),
            func.min(TextRevision.created_by_user_id).label("created_by_user_id"),
        )
        .filter(TextRevision.kind == TextRevisionKind.replace)
        .group_by(TextRevision.batch_id)
        .order_by(func.min(TextRevision.created_at).desc())
        .limit(limit)
        .all()
    )
    result = []
    for row in rows:
        email = None
        if row.created_by_user_id:
            u = db.get(User, row.created_by_user_id)
            email = u.email if u else None
        result.append(
            {
                "batch_id": row.batch_id,
                "created_at": row.created_at,
                "count": row.count,
                "query": row.query,
                "replacement": row.replacement,
                "created_by_email": email,
            }
        )
    return result


def rollback_batch(db: Session, *, batch_id: str, user: User) -> dict:
    revisions = (
        db.query(TextRevision)
        .filter(
            TextRevision.batch_id == batch_id,
            TextRevision.kind == TextRevisionKind.replace,
        )
        .all()
    )
    if not revisions:
        raise ValueError("Batch not found")

    rollback_id = str(uuid.uuid4())
    restored = 0
    skipped: list[dict] = []

    for rev in revisions:
        seg = db.get(Segment, rev.segment_id)
        if not seg:
            skipped.append({"segment_id": rev.segment_id, "reason": "not_found"})
            continue
        current = segment_text(seg)
        if current != rev.text_after:
            skipped.append({"segment_id": rev.segment_id, "reason": "text_changed"})
            continue
        db.add(
            TextRevision(
                batch_id=rollback_id,
                segment_id=rev.segment_id,
                text_before=current,
                text_after=rev.text_before,
                status_before=seg.status,
                kind=TextRevisionKind.rollback,
                query=rev.query,
                replacement=rev.replacement,
                created_by_user_id=user.id,
            )
        )
        seg.text_corrected = rev.text_before
        seg.status = rev.status_before
        seg.annotator = user.email
        restored += 1

    if restored:
        db.commit()
    return {"batch_id": rollback_id, "restored": restored, "skipped": skipped}
