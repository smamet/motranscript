# Transcription guide

## Verbatim rules

- Transcribe exactly what was spoken, including hesitations and false starts per project conventions.
- Do not translate. Keep each word in the language it was spoken.
- Code-switching is normal: "mo ti pe attend le bus, but it never came" stays as-is.

## Languages

- `kreol` — Mauritian Creole (Kreol Morisien)
- `fr` — French
- `en` — English
- `mix` — code-switched within the segment

## Orthography

- Aim for phonetic accuracy in Kreol; use **Normalize (Lortograf)** for official spelling.
- French and English are left unchanged by the normalizer.
- Review the diff before accepting — the normalizer fixes spelling only, not meaning.

## Normalizer workflow

1. Correct what was said (verbatim content).
2. Click **Normalize** on Kreol/mix segments, or **Normalize (Lortograf)** for all.
3. Accept or reject each suggestion.
4. Validate, then export.

## Status workflow

1. `raw` — machine draft from ASR
2. `corrected` — human edited
3. `validated` — ready for export and training

Only **validated** segments are exported to JSONL.
