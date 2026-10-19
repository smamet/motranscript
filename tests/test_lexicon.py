"""DB lexicon CRUD and cache invalidation."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.annotator.api.lexicon import (
    get_lexicon,
    import_text,
    invalidate_lexicon_cache,
    list_entries,
    upsert_entry,
)
from apps.annotator.db.models import Base, LexiconKind


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
        invalidate_lexicon_cache()


def test_upsert_alias_and_cache(db: Session) -> None:
    invalidate_lexicon_cache()
    upsert_entry(db, word="mo", kind="official", origin="manual")
    upsert_entry(db, word="mwen", kind="alias", canonical="mo", origin="manual")

    lex = get_lexicon(db)
    assert lex.lookup("mwen") == "mo"
    assert lex.status_of("mwen") == "alias"

    entries = list_entries(db, kind="alias")
    assert len(entries) == 1
    assert entries[0].word == "mwen"


def test_import_export_roundtrip(db: Session) -> None:
    result = import_text(
        db,
        text="manze\nmwen:mo\n",
        origin="manual",
    )
    assert result["added"] >= 2
    entries = list_entries(db)
    words = {e.word: e for e in entries}
    assert "manze" in words
    assert words["manze"].kind == LexiconKind.official
    assert words["mwen"].kind == LexiconKind.alias
    assert words["mwen"].canonical == "mo"

    # Cache invalidates on write
    lex1 = get_lexicon(db)
    upsert_entry(db, word="nou", kind="alias", canonical="nu", origin="manual")
    lex2 = get_lexicon(db)
    assert lex2.lookup("nou") == "nu"
    assert lex1 is not lex2 or lex2.lookup("nou") == "nu"
