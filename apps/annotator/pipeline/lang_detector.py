"""Heuristic Kreol vs French detection for mixed transcripts."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# High-signal French function/content words (code-switching context)
_FRENCH_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
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
        "merci",
        "beaucoup",
        "parce",
        "que",
        "qui",
        "quoi",
        "nous",
        "vous",
        "ils",
        "elles",
        "notre",
        "votre",
        "leur",
        "cette",
        "cet",
        "ces",
        "donc",
        "mais",
        "comme",
        "très",
        "tres",
        "aussi",
        "avec",
        "sans",
        "dans",
        "sur",
        "sous",
        "entre",
        "chez",
        "être",
        "etre",
        "avoir",
        "faire",
        "dit",
        "dire",
        "pas",  # French "not" — not Kreol
        "cest",
        "nest",
        "coûte",
        "coute",
        "cher",
        "raisons",
        "infrastructure",
        "gouvernement",
        "secteur",
        "entreprises",
        "contribution",
        "nécessaire",
        "necessaire",
        "indéminées",
        "indeminees",
        "depuis",
        "souffert",
        "financièrement",
        "financierement",
        "fragile",
        "disparaître",
        "disparaitre",
        "nouveau",
        "souffle",
        "changement",
        "adresse",
        "permis",
        "vie",
    }
)

# Common Kreol words not always caught by lexicon alone (incl. ASR spellings)
# Do NOT include French homographs like "pas".
_KREOL_HINTS = frozenset(
    {
        "ban",
        "bann",
        "depi",
        "bocou",
        "boucou",
        "zot",
        "ki",
        "seki",
        "eski",
        "pou",
        "dan",
        "ek",
        "aster",
        "kor",
        "kuma",
        "komie",
        "kifer",
        "kote",
        "kont",
        "mo",
        "nu",
        "u",
        "li",
        "nou",
        "ou",
        "pme",
        "soufer",
        "soufri",
        "manze",
        "manje",
        "kone",
        "konn",
        "finn",
        "pe",
        "ti",
        "ena",
        "pa",  # Kreol "not" — but only after French check loses; see classify order
    }
)

# Prefer French when ambiguous short tokens that exist in both
_AMBIGUOUS_FRENCH_FIRST = frozenset({"pas", "la", "le", "les", "de", "du", "des", "un", "une", "et", "a", "on"})

_FR_ACCENT_RE = re.compile(r"[àâäéèêëïîôùûüç]", re.I)
_FR_APOSTROPHE_RE = re.compile(r"^[a-z]{1,3}'", re.I)
_TOKEN_CLEAN_RE = re.compile(r"^[^A-Za-zÀ-ÿ]+|[^A-Za-zÀ-ÿ]+$")


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=1)
def _kreol_lexicon() -> frozenset[str]:
    from normalizer.lexicon_loader import load_lexicon

    official, aliases = load_lexicon()
    return frozenset(official | set(aliases.keys()) | set(aliases.values()))


def classify_word(word: str) -> str:
    """Return 'kreol', 'fr', or 'unknown'."""
    token = _TOKEN_CLEAN_RE.sub("", word.strip())
    if not token or not re.search(r"[A-Za-zÀ-ÿ]", token):
        return "unknown"

    if _FR_ACCENT_RE.search(token):
        return "fr"
    if _FR_APOSTROPHE_RE.match(token):
        return "fr"

    lower = strip_accents(token.lower())
    # French first for ambiguous homographs (pas, la, …)
    if lower in _AMBIGUOUS_FRENCH_FIRST or lower in _FRENCH_WORDS:
        return "fr"
    if lower in _KREOL_HINTS or lower in _kreol_lexicon():
        return "kreol"
    return "unknown"


def resolve_segment_lang(words: list[str], fallback: str = "mix") -> str:
    counts = {"kreol": 0, "fr": 0}
    for word in words:
        label = classify_word(word)
        if label in counts:
            counts[label] += 1
    total = counts["kreol"] + counts["fr"]
    if not total:
        return fallback
    # Require clear Kreol signal; otherwise prefer French / fallback
    if counts["kreol"] >= 2 and counts["kreol"] >= counts["fr"]:
        if counts["fr"]:
            return "mix"
        return "kreol"
    if counts["fr"] and counts["kreol"]:
        return "mix"
    if counts["fr"]:
        return "fr"
    if counts["kreol"]:
        return "kreol"
    return fallback


def should_split_on_lang(chunk_lang: str | None, word_lang: str) -> bool:
    if chunk_lang is None or word_lang == "unknown":
        return False
    if chunk_lang == "unknown":
        return False
    return chunk_lang in {"kreol", "fr"} and word_lang in {"kreol", "fr"} and chunk_lang != word_lang
