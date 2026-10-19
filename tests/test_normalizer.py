"""Normalizer + LexiconProvider tests."""

import pytest

from normalizer.lexicon import StaticLexicon, default_file_lexicon
from normalizer.lexicon_loader import load_lexicon, lookup_word
from normalizer.normalizer import LortografNormalizer


@pytest.fixture
def normalizer() -> LortografNormalizer:
    return LortografNormalizer(use_llm=False)


def test_lexicon_size() -> None:
    official, aliases = load_lexicon()
    assert len(official) >= 1900
    assert len(aliases) >= 10


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("mwen", "mo"),
        ("nou", "nu"),
        ("ou", "u"),
        ("manje", "manze"),
        ("eske", "eski"),
    ],
)
def test_asr_aliases(token: str, expected: str) -> None:
    assert lookup_word(token) == expected


def test_inflected_forms_not_collapsed() -> None:
    assert lookup_word("revini") == "revini"
    assert lookup_word("revinn") == "revinn"


def test_normalizes_common_asr_spellings(normalizer: LortografNormalizer) -> None:
    result = normalizer.normalize_text("Mwen manje aret nou ale la kaz", lang="kreol")
    assert result.normalized == "Mo manze aret nu ale la kaz"
    assert result.changed
    assert {c.original.lower() for c in result.changes} == {"mwen", "manje", "nou"}


def test_skips_french_function_words(normalizer: LortografNormalizer) -> None:
    result = normalizer.normalize_text("Bonjour tout le monde", lang="mix")
    assert not result.changed
    assert result.normalized == "Bonjour tout le monde"


def test_unknown_tokens_reported(normalizer: LortografNormalizer) -> None:
    result = normalizer.normalize_text("nou yankou soukou", lang="kreol")
    assert "yankou" in result.unknown_tokens
    assert "soukou" in result.unknown_tokens


def test_english_not_normalized(normalizer: LortografNormalizer) -> None:
    result = normalizer.normalize_text("Hello world", lang="en")
    assert not result.changed


def test_static_lexicon_provider() -> None:
    lex = StaticLexicon(
        official={"mo", "manze"},
        aliases={"mwen": "mo", "manje": "manze"},
        skip={"le", "la"},
    )
    n = LortografNormalizer(lexicon=lex, use_llm=False)
    result = n.normalize_text("mwen manje le pain", lang="kreol")
    assert result.normalized == "mo manze le pain"
    assert lex.status_of("mwen") == "alias"
    assert lex.status_of("mo") == "official"
    assert lex.status_of("le") == "skip"


def test_file_lexicon_default() -> None:
    lex = default_file_lexicon()
    assert lex.is_official("mo") or lex.alias_of("mwen") == "mo"
