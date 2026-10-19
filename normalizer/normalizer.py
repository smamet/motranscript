import re
from dataclasses import dataclass, field

from normalizer.lexicon import FileLexicon, LexiconProvider, default_file_lexicon
from normalizer.phonetic import strip_accents

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)?|[^A-Za-zÀ-ÿ\s]+|\s+")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)?")


def tokenize_words(text: str) -> list[tuple[str, int, int]]:
    """Return [(word, start, end), ...] for alphabetic tokens only."""
    return [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(text or "")]


@dataclass
class WordChange:
    original: str
    normalized: str
    start: int
    end: int


@dataclass
class NormalizeResult:
    original: str
    normalized: str
    changes: list[WordChange] = field(default_factory=list)
    unknown_tokens: list[str] = field(default_factory=list)
    skipped_llm: bool = True

    @property
    def changed(self) -> bool:
        return self.original != self.normalized


class LortografNormalizer:
    """Normalize Kreol spelling to official Lortograf; preserve FR/EN in code-switched text."""

    def __init__(
        self,
        lexicon: LexiconProvider | None = None,
        use_llm: bool = False,
    ) -> None:
        self.lexicon = lexicon if lexicon is not None else default_file_lexicon()
        self.use_llm = use_llm

    def should_normalize_lang(self, lang: str) -> bool:
        return lang in ("kreol", "mix")

    def normalize_text(self, text: str, lang: str = "mix") -> NormalizeResult:
        if not self.should_normalize_lang(lang):
            return NormalizeResult(original=text, normalized=text)

        changes: list[WordChange] = []
        unknown: set[str] = set()
        parts: list[str] = []

        for match in _TOKEN_RE.finditer(text):
            token = match.group(0)
            start, end = match.start(), match.end()

            if not re.match(r"[A-Za-zÀ-ÿ]", token):
                parts.append(token)
                continue

            word_clean = token.strip()
            lower = strip_accents(word_clean.lower())

            if self.lexicon.is_skip(lower):
                parts.append(token)
                continue

            official = self.lexicon.lookup(word_clean)
            if official and official != lower:
                replacement = self._apply_casing(word_clean, official)
                changes.append(
                    WordChange(
                        original=word_clean,
                        normalized=replacement,
                        start=start,
                        end=end,
                    )
                )
                parts.append(replacement)
            elif official:
                parts.append(word_clean)
            else:
                unknown.add(lower)
                parts.append(token)

        normalized = "".join(parts)

        if self.use_llm and normalized == text:
            from normalizer.llm_pass import llm_normalize_spelling

            llm_result = llm_normalize_spelling(text)
            if llm_result and llm_result != text:
                normalized = llm_result
                changes.append(
                    WordChange(original=text, normalized=normalized, start=0, end=len(text))
                )
                return NormalizeResult(
                    original=text,
                    normalized=normalized,
                    changes=changes,
                    unknown_tokens=sorted(unknown),
                    skipped_llm=False,
                )

        return NormalizeResult(
            original=text,
            normalized=normalized,
            changes=changes,
            unknown_tokens=sorted(unknown),
        )

    @staticmethod
    def _apply_casing(original: str, official: str) -> str:
        if original.isupper():
            return official.upper()
        if original[0].isupper():
            return official.capitalize()
        return official
