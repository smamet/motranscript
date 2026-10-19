"""Post-processing helpers for ASR output."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"\S+")
_WORD_KEY_RE = re.compile(r"^[^\wÀ-ÿ]+|[^\wÀ-ÿ]+$")
_APOSTROPHE_WORD_RE = re.compile(r"\b([cdjlnsmt]|qu) '([a-zàâäéèêëïîôùûüç])", re.I)
_HYPHEN_GAP_RE = re.compile(r"(\w) -(?=\w)")
_DOUBLE_APOSTROPHE_RE = re.compile(r"''+")


# Common Whisper hallucinations on silence/music (especially YouTube-trained bias)
_HALLUCINATION_PHRASES = (
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "subscribe to the channel",
    "like and subscribe",
    "thanks for watching please subscribe",
    "merci d'avoir regarde",
    "merci d'avoir regardé",
    "sous-titres realises",
    "sous-titres réalisés",
    "subtitles by",
    "amara.org",
    "اشتركوا في القناة",
)

_OUTRO_HINT_RE = re.compile(
    r"\b(thank(s| you)|subscribe|watching|like and subscribe)\b",
    re.I,
)


def _normalize_hallucination_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def is_whisper_hallucination(text: str, duration_sec: float) -> bool:
    """Detect short/noise segments where Whisper invents YouTube outros."""
    normalized = _normalize_hallucination_text(text)
    if not normalized:
        return True

    for phrase in _HALLUCINATION_PHRASES:
        norm_phrase = _normalize_hallucination_text(phrase)
        if normalized == norm_phrase or normalized.startswith(norm_phrase):
            return True

    duration = max(0.0, duration_sec)
    if duration <= 3.0:
        for phrase in _HALLUCINATION_PHRASES:
            if _normalize_hallucination_text(phrase) in normalized:
                return True

    if duration <= 1.5 and len(normalized.split()) <= 8 and _OUTRO_HINT_RE.search(normalized):
        return True

    return False


def collapse_repeated_tokens(text: str, max_consecutive: int = 2) -> str:
    """Collapse stutter loops like 'nous, nous, nous, …' from Whisper hallucinations."""
    parts = _TOKEN_RE.findall(text)
    if not parts:
        return text

    out: list[str] = []
    prev_key: str | None = None
    run = 0
    for part in parts:
        key = _WORD_KEY_RE.sub("", part.lower())
        if key and key == prev_key:
            run += 1
            if run <= max_consecutive:
                out.append(part)
        else:
            prev_key = key or prev_key
            run = 1
            out.append(part)
    return join_asr_words(out)


def join_asr_words(words: list[str]) -> str:
    """Join Whisper word tokens; fix spurious spaces around apostrophes and hyphens."""
    parts: list[str] = []
    for raw in words:
        word = raw.strip()
        if not word:
            continue
        if not parts:
            parts.append(word)
            continue
        prev = parts[-1]
        if word.startswith(("'", "'")):
            parts[-1] = prev + word
        elif prev.endswith(("'", "'")):
            parts[-1] = prev + word
        elif word.startswith("-") and prev and prev[-1].isalnum():
            parts[-1] = prev + word
        else:
            parts.append(word)
    return fix_apostrophe_spacing(" ".join(parts))


def fix_apostrophe_spacing(text: str) -> str:
    """Fix 'c est' / \"c 'est\" artifacts from naive word joining."""
    text = _APOSTROPHE_WORD_RE.sub(r"\1'\2", text)
    text = _HYPHEN_GAP_RE.sub(r"\1-", text)
    text = _DOUBLE_APOSTROPHE_RE.sub("'", text)
    return re.sub(r" +", " ", text).strip()
