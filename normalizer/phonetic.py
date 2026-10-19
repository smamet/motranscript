"""Phonetic key generation for Kreol Morisien (Lortograf)."""

import re
import unicodedata

# Kreol grapheme → phoneme-ish key (simplified for bootstrap lexicon matching)
_G2P_SUBS = (
    ("tion", "sion"),
    ("ph", "f"),
    ("qu", "k"),
    ("ck", "k"),
    ("ll", "l"),
    ("nn", "n"),
    ("mm", "m"),
    ("tt", "t"),
    ("ss", "s"),
    ("ee", "i"),
    ("ea", "i"),
    ("ou", "u"),
    ("oi", "wa"),
    ("an", "an"),
    ("en", "an"),
    ("in", "en"),
    ("on", "on"),
)


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def phonetic_key(word: str) -> str:
    """Map a word to a phonetic lookup key."""
    w = strip_accents(word.lower())
    w = re.sub(r"[^a-z'-]", "", w)
    if not w:
        return ""
    for src, dst in _G2P_SUBS:
        w = w.replace(src, dst)
    # Collapse repeated chars
    w = re.sub(r"(.)\1+", r"\1", w)
    return w
