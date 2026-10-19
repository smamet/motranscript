"""DB-backed Lortograf lexicon with in-memory cache."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from apps.annotator.db.models import (
    LexiconEntry,
    LexiconKind,
    LexiconOrigin,
    Segment,
    SegmentStatus,
)
from normalizer.lexicon import LexiconProvider, StaticLexicon, parse_aliases_text, parse_words_text
from normalizer.normalizer import tokenize_words
from normalizer.phonetic import strip_accents
from sqlalchemy import func, select
from sqlalchemy.orm import Session

_cache: dict[str, object] = {"version": None, "lexicon": None}


def _db_version(db: Session) -> tuple[int, int | None]:
    count, max_id = db.execute(
        select(func.count(LexiconEntry.id), func.max(LexiconEntry.id))
    ).one()
    return int(count or 0), max_id


def invalidate_lexicon_cache() -> None:
    _cache["version"] = None
    _cache["lexicon"] = None


def load_static_from_db(db: Session) -> StaticLexicon:
    rows = db.query(LexiconEntry).all()
    official: set[str] = set()
    aliases: dict[str, str] = {}
    skip: set[str] = set()
    for row in rows:
        word = row.word.lower()
        if row.kind == LexiconKind.official:
            official.add(word)
        elif row.kind == LexiconKind.alias:
            if row.canonical:
                aliases[word] = row.canonical.lower()
                official.add(row.canonical.lower())
        elif row.kind == LexiconKind.skip:
            skip.add(word)
    return StaticLexicon(official, aliases, skip)


def get_lexicon(db: Session | None = None) -> LexiconProvider:
    """Return cached DbLexicon when DB has entries; otherwise FileLexicon."""
    if db is None:
        from normalizer.lexicon import default_file_lexicon

        return default_file_lexicon()

    version = _db_version(db)
    if version[0] == 0:
        from normalizer.lexicon import default_file_lexicon

        return default_file_lexicon()

    if _cache["version"] == version and _cache["lexicon"] is not None:
        return _cache["lexicon"]  # type: ignore[return-value]

    lexicon = load_static_from_db(db)
    _cache["version"] = version
    _cache["lexicon"] = lexicon
    return lexicon


@dataclass
class LexiconEntryDTO:
    id: int
    word: str
    kind: str
    canonical: str | None
    origin: str
    note: str | None


def list_entries(
    db: Session,
    *,
    kind: str | None = None,
    origin: str | None = None,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[LexiconEntry]:
    query = db.query(LexiconEntry)
    if kind:
        query = query.filter(LexiconEntry.kind == LexiconKind(kind))
    if origin:
        query = query.filter(LexiconEntry.origin == LexiconOrigin(origin))
    if q:
        query = query.filter(LexiconEntry.word.contains(q.lower()))
    return (
        query.order_by(LexiconEntry.word)
        .offset(offset)
        .limit(min(limit, 2000))
        .all()
    )


def upsert_entry(
    db: Session,
    *,
    word: str,
    kind: str,
    canonical: str | None = None,
    origin: str = "manual",
    note: str | None = None,
    created_by_user_id: int | None = None,
) -> LexiconEntry:
    word_l = strip_accents(word.strip().lower())
    if not word_l:
        raise ValueError("word is required")
    kind_e = LexiconKind(kind)
    origin_e = LexiconOrigin(origin)
    canonical_l = strip_accents(canonical.strip().lower()) if canonical else None

    if kind_e == LexiconKind.alias:
        if not canonical_l:
            raise ValueError("alias requires canonical")
        # Ensure canonical exists as official
        existing_can = (
            db.query(LexiconEntry).filter(LexiconEntry.word == canonical_l).one_or_none()
        )
        if existing_can is None:
            db.add(
                LexiconEntry(
                    word=canonical_l,
                    kind=LexiconKind.official,
                    canonical=None,
                    origin=origin_e,
                    note=None,
                    created_by_user_id=created_by_user_id,
                )
            )
        elif existing_can.kind == LexiconKind.skip:
            existing_can.kind = LexiconKind.official
            existing_can.canonical = None

    existing = db.query(LexiconEntry).filter(LexiconEntry.word == word_l).one_or_none()
    if existing:
        existing.kind = kind_e
        existing.canonical = canonical_l if kind_e == LexiconKind.alias else None
        existing.origin = origin_e
        if note is not None:
            existing.note = note
        entry = existing
    else:
        entry = LexiconEntry(
            word=word_l,
            kind=kind_e,
            canonical=canonical_l if kind_e == LexiconKind.alias else None,
            origin=origin_e,
            note=note,
            created_by_user_id=created_by_user_id,
        )
        db.add(entry)

    db.commit()
    db.refresh(entry)
    invalidate_lexicon_cache()
    return entry


def delete_entry(db: Session, entry_id: int) -> bool:
    entry = db.get(LexiconEntry, entry_id)
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    invalidate_lexicon_cache()
    return True


def import_text(
    db: Session,
    *,
    text: str,
    format: str = "auto",
    origin: str = "manual",
    created_by_user_id: int | None = None,
) -> dict:
    """Import words.txt and/or alias lines (word:canonical)."""
    origin_e = LexiconOrigin(origin)
    added = 0
    updated = 0

    # Detect aliases vs words by presence of ':'
    alias_lines: list[str] = []
    word_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.split("#")[0].strip()
        if not stripped:
            continue
        if ":" in stripped and format != "words":
            alias_lines.append(stripped)
        else:
            word_lines.append(stripped)

    for word in parse_words_text("\n".join(word_lines)):
        existing = db.query(LexiconEntry).filter(LexiconEntry.word == word).one_or_none()
        if existing:
            if existing.kind != LexiconKind.official:
                existing.kind = LexiconKind.official
                existing.canonical = None
                existing.origin = origin_e
                updated += 1
            continue
        db.add(
            LexiconEntry(
                word=word,
                kind=LexiconKind.official,
                origin=origin_e,
                created_by_user_id=created_by_user_id,
            )
        )
        added += 1

    for src, dst in parse_aliases_text("\n".join(alias_lines)).items():
        can = (
            db.query(LexiconEntry).filter(LexiconEntry.word == dst).one_or_none()
        )
        if can is None:
            db.add(
                LexiconEntry(
                    word=dst,
                    kind=LexiconKind.official,
                    origin=origin_e,
                    created_by_user_id=created_by_user_id,
                )
            )
            added += 1
        existing = db.query(LexiconEntry).filter(LexiconEntry.word == src).one_or_none()
        if existing:
            existing.kind = LexiconKind.alias
            existing.canonical = dst
            existing.origin = origin_e
            updated += 1
        else:
            db.add(
                LexiconEntry(
                    word=src,
                    kind=LexiconKind.alias,
                    canonical=dst,
                    origin=origin_e,
                    created_by_user_id=created_by_user_id,
                )
            )
            added += 1

    db.commit()
    invalidate_lexicon_cache()
    return {"added": added, "updated": updated}


def export_text(db: Session) -> str:
    lines: list[str] = ["# Official forms", ""]
    officials = (
        db.query(LexiconEntry)
        .filter(LexiconEntry.kind == LexiconKind.official)
        .order_by(LexiconEntry.word)
        .all()
    )
    for row in officials:
        lines.append(row.word)
    lines.extend(["", "# Aliases (variant:canonical)", ""])
    aliases = (
        db.query(LexiconEntry)
        .filter(LexiconEntry.kind == LexiconKind.alias)
        .order_by(LexiconEntry.word)
        .all()
    )
    for row in aliases:
        if row.canonical:
            lines.append(f"{row.word}:{row.canonical}")
    lines.extend(["", "# Skip words", ""])
    skips = (
        db.query(LexiconEntry)
        .filter(LexiconEntry.kind == LexiconKind.skip)
        .order_by(LexiconEntry.word)
        .all()
    )
    for row in skips:
        lines.append(f"# skip:{row.word}")
    return "\n".join(lines) + "\n"


def suggest_from_corpus(db: Session, *, min_count: int = 3) -> list[dict]:
    """Unknown words appearing >= min_count times in validated segments."""
    lexicon = get_lexicon(db)
    segments = (
        db.query(Segment)
        .filter(Segment.status == SegmentStatus.validated)
        .all()
    )
    counter: Counter[str] = Counter()
    for seg in segments:
        text = seg.text_corrected or seg.text_raw or ""
        for word, _s, _e in tokenize_words(text):
            lower = strip_accents(word.lower())
            if lexicon.status_of(lower) == "unknown":
                counter[lower] += 1

    return [
        {"word": word, "count": count}
        for word, count in counter.most_common()
        if count >= min_count
    ]
