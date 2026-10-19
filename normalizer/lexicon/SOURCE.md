# Lortograf lexicon sources

## Primary dictionary

- **File:** `normalizer/dokumen.pub_diksyoner-kreol-morisyen-mauritian-english-dictionary.pdf`
- **Title:** *Diksyoner Kreol Morisyen* (Mauritian Creole–English dictionary)
- **Compiled:** Rajki (2008), published Chazal (2012)

## Generated files

| File | Purpose |
|------|---------|
| `words.txt` | Headwords **and** parenthetical inflected forms from the PDF |
| `asr_aliases.txt` | Manual Whisper/ASR **spelling** fixes only |

## Important: no PDF-derived aliases

Parenthetical forms in the dictionary (e.g. `revini (revinn)`) are often **different tenses**, not alternate spellings — like French *reviens* vs *revenu*. They are all registered as valid forms in `words.txt`. The normalizer must **not** map one to the other.

Only add entries to `asr_aliases.txt` when you are sure it is orthography (e.g. `manje→manze`, `mwen→mo`), not grammar.

## Regenerate from PDF

```bash
uv sync --extra dev
uv run python normalizer/build_lexicon_from_pdf.py
```

## Lookup order

1. Exact match in `words.txt` → keep as-is
2. Alias in `asr_aliases.txt` → replace (spelling fix only)
