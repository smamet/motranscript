"""Lexicon providers for Lortograf normalization."""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from normalizer.phonetic import strip_accents

LEXICON_DIR = Path(__file__).resolve().parent / "lexicon"

# French/English function words common in code-switching — never normalize
DEFAULT_SKIP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "it",
        "is",
        "was",
        "are",
        "be",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "me",
        "my",
        "you",
        "your",
        "we",
        "they",
        "he",
        "she",
        "this",
        "that",
        "never",
        "came",
        "see",
        "later",
        "everyone",
        "take",
        "care",
        "let",
        "check",
        "phone",
        "first",
        "half",
        "hour",
        "maybe",
        "weather",
        "nice",
        "today",
        "already",
        "non",
        "oui",
        "alors",
        "on",
        "peut",
        "aller",
        "manger",
        "quelque",
        "chose",
        "pour",
        "le",
        "la",
        "les",
        "de",
        "du",
        "des",
        "un",
        "une",
        "et",
        "bonjour",
        "tout",
        "monde",
        "bientot",
        "bientôt",
        "merci",
        "beaucoup",
    }
)


def parse_aliases_text(text: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        src, dst = line.split(":", 1)
        src, dst = src.strip().lower(), dst.strip().lower()
        if src and dst:
            aliases[src] = dst
    return aliases


def parse_words_text(text: str) -> set[str]:
    official: set[str] = set()
    for line in text.splitlines():
        word = line.split("#")[0].strip().lower()
        if word:
            official.add(word)
    return official


def _parse_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return parse_aliases_text(path.read_text(encoding="utf-8"))


class LexiconProvider(ABC):
    @abstractmethod
    def is_official(self, word: str) -> bool: ...

    @abstractmethod
    def alias_of(self, word: str) -> str | None: ...

    @abstractmethod
    def is_skip(self, word: str) -> bool: ...

    @abstractmethod
    def official_words(self) -> frozenset[str]: ...

    @abstractmethod
    def aliases(self) -> dict[str, str]: ...

    def lookup(self, word: str) -> str | None:
        """Return official form if known via exact match or alias table."""
        lower = strip_accents(word.lower())
        if self.is_official(lower):
            return lower
        return self.alias_of(lower)

    def status_of(self, word: str) -> str:
        """Return official | alias | skip | unknown."""
        lower = strip_accents(word.lower())
        if self.is_skip(lower):
            return "skip"
        if self.is_official(lower):
            return "official"
        if self.alias_of(lower) is not None:
            return "alias"
        return "unknown"


class StaticLexicon(LexiconProvider):
    def __init__(
        self,
        official: set[str] | frozenset[str],
        aliases: dict[str, str],
        skip: set[str] | frozenset[str] | None = None,
    ) -> None:
        self._official = frozenset(w.lower() for w in official)
        self._aliases = {k.lower(): v.lower() for k, v in aliases.items()}
        # Alias targets are official
        self._official = self._official | frozenset(self._aliases.values())
        self._skip = frozenset(w.lower() for w in (skip or ()))

    def is_official(self, word: str) -> bool:
        return word.lower() in self._official

    def alias_of(self, word: str) -> str | None:
        return self._aliases.get(word.lower())

    def is_skip(self, word: str) -> bool:
        return strip_accents(word.lower()) in self._skip

    def official_words(self) -> frozenset[str]:
        return self._official

    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)


class FileLexicon(LexiconProvider):
    """Load lexicon from normalizer/lexicon/*.txt plus DEFAULT_SKIP_WORDS."""

    def __init__(self, lexicon_dir: Path | None = None) -> None:
        directory = lexicon_dir or LEXICON_DIR
        official: set[str] = set()
        words_file = directory / "words.txt"
        if words_file.exists():
            official = parse_words_text(words_file.read_text(encoding="utf-8"))
        aliases = _parse_aliases(directory / "asr_aliases.txt")
        self._inner = StaticLexicon(official, aliases, DEFAULT_SKIP_WORDS)

    def is_official(self, word: str) -> bool:
        return self._inner.is_official(word)

    def alias_of(self, word: str) -> str | None:
        return self._inner.alias_of(word)

    def is_skip(self, word: str) -> bool:
        return self._inner.is_skip(word)

    def official_words(self) -> frozenset[str]:
        return self._inner.official_words()

    def aliases(self) -> dict[str, str]:
        return self._inner.aliases()


@lru_cache(maxsize=1)
def default_file_lexicon() -> FileLexicon:
    return FileLexicon()
