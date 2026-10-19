"""Compatibility façade over FileLexicon for existing callers."""

from functools import lru_cache
from pathlib import Path

from normalizer.lexicon import (
    DEFAULT_SKIP_WORDS,
    LEXICON_DIR,
    FileLexicon,
    default_file_lexicon,
    parse_aliases_text,
    parse_words_text,
)

__all__ = [
    "LEXICON_DIR",
    "DEFAULT_SKIP_WORDS",
    "load_lexicon",
    "lookup_word",
    "parse_aliases_text",
    "parse_words_text",
]


def _parse_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return parse_aliases_text(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_lexicon() -> tuple[set[str], dict[str, str]]:
    """Return (official_forms, variant_spelling → official_form)."""
    lex = default_file_lexicon()
    return set(lex.official_words()), lex.aliases()


def lookup_word(word: str) -> str | None:
    """Return official form if known via exact match or alias table."""
    return default_file_lexicon().lookup(word)
