"""WER/CER and phonetic CER metrics."""

from __future__ import annotations

import re

import jiwer

from normalizer.phonetic import phonetic_key


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def phonetic_text(text: str) -> str:
    words = re.findall(r"[\w'-]+", normalize_text(text))
    return " ".join(phonetic_key(w) for w in words if phonetic_key(w))


def compute_wer_cer(references: list[str], hypotheses: list[str]) -> dict[str, float]:
    refs = [normalize_text(r) for r in references]
    hyps = [normalize_text(h) for h in hypotheses]
    return {
        "wer": float(jiwer.wer(refs, hyps)),
        "cer": float(jiwer.cer(refs, hyps)),
    }


def compute_phonetic_cer(references: list[str], hypotheses: list[str]) -> float:
    refs = [phonetic_text(r) for r in references]
    hyps = [phonetic_text(h) for h in hypotheses]
    return float(jiwer.cer(refs, hyps))


def metrics_by_language(
    references: list[str],
    hypotheses: list[str],
    langs: list[str],
    *,
    min_seconds: float = 30.0,
    durations: list[float] | None = None,
) -> dict[str, dict[str, float]]:
    from collections import defaultdict

    by_lang: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for i, (ref, hyp, lang) in enumerate(zip(references, hypotheses, langs, strict=True)):
        dur = durations[i] if durations else 0.0
        by_lang[lang].append((ref, hyp, dur))

    out: dict[str, dict[str, float]] = {}
    for lang, pairs in by_lang.items():
        total_dur = sum(p[2] for p in pairs)
        if total_dur < min_seconds and len(pairs) < 3:
            continue
        refs = [p[0] for p in pairs]
        hyps = [p[1] for p in pairs]
        base = compute_wer_cer(refs, hyps)
        base["phonetic_cer"] = compute_phonetic_cer(refs, hyps)
        base["seconds"] = total_dur
        out[lang] = base
    return out


def gate_passes(
    candidate: dict[str, dict[str, float]],
    baseline: dict[str, dict[str, float]],
) -> tuple[bool, list[str]]:
    """Publish only if WER and CER improve for every language present in baseline."""
    reasons: list[str] = []
    for lang, base in baseline.items():
        if lang not in candidate:
            reasons.append(f"missing language in candidate metrics: {lang}")
            continue
        cand = candidate[lang]
        if cand["wer"] >= base["wer"] or cand["cer"] >= base["cer"]:
            reasons.append(
                f"{lang}: WER {cand['wer']:.3f} vs {base['wer']:.3f}, "
                f"CER {cand['cer']:.3f} vs {base['cer']:.3f}"
            )
    return len(reasons) == 0, reasons
