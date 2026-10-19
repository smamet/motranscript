"""Extract Kreol headwords from Diksioner PDF into lexicon source files."""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pymupdf

PDF_NAME = "dokumen.pub_diksyoner-kreol-morisyen-mauritian-english-dictionary.pdf"
LEXICON_DIR = Path(__file__).resolve().parent / "lexicon"

HEADER_RE = re.compile(r"DIKSYONER KREOL MORISYEN", re.I)
PAGE_NUM_RE = re.compile(r"^\d+$")
SECTION_LETTER_RE = re.compile(r"^[A-Z]$")

# Headword line: kreol word(s), optional (variant), optional (sense#), optional [from|see ...], then :
ENTRY_HEAD_RE = re.compile(
    r"^([a-z][a-z'-]*(?:\s+[a-z][a-z'-]*)*)"
    r"(?:\s*\(([^)]+)\))*"
    r"(?:\s*\(\d+\))?"
    r"(?:\s*\[(?:from|see)[^\]]*\])?"
    r"\s*:\s",
    re.IGNORECASE,
)

SENSE_NUM_RE = re.compile(r"^\d+$")


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def clean_page_text(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or HEADER_RE.search(line):
            continue
        if PAGE_NUM_RE.match(line) or SECTION_LETTER_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def merge_entry_lines(text: str) -> list[str]:
    """Join wrapped definition lines onto their headword line."""
    merged: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ENTRY_HEAD_RE.match(line):
            if buffer:
                merged.append(buffer)
            buffer = line
        else:
            buffer = f"{buffer} {line}" if buffer else line
    if buffer:
        merged.append(buffer)
    return merged


def parse_head(line: str) -> tuple[str, list[str]] | None:
    m = ENTRY_HEAD_RE.match(line)
    if not m:
        return None
    head = m.group(1).strip().lower()
    if not head or len(head) > 48:
        return None
    if not re.match(r"^[a-z'-]+(?: [a-z'-]+)*$", head):
        return None

    variants: list[str] = []
    prefix = line[: m.end()]
    for vm in re.finditer(r"\(([^)]+)\)", prefix):
        content = vm.group(1).strip().lower()
        if SENSE_NUM_RE.match(content):
            continue
        if re.match(r"^[a-z][a-z'-]*$", content):
            variants.append(content)
    return head, variants


def extract_from_pdf(pdf_path: Path) -> set[str]:
    doc = pymupdf.open(pdf_path)
    # Dictionary body starts around page 3 (1-based); skip front matter.
    start_page = 2
    for i in range(min(10, doc.page_count)):
        if "abandone" in doc[i].get_text().lower():
            start_page = i
            break

    body = "\n".join(clean_page_text(doc[p].get_text()) for p in range(start_page, doc.page_count))
    merged_lines = merge_entry_lines(body)

    official: set[str] = set()

    for line in merged_lines:
        parsed = parse_head(line)
        if not parsed:
            continue
        head, variants = parsed
        official.add(head)
        # Parenthetical forms are often inflected/tense variants (revini vs revinn),
        # not alternate spellings — keep each as a valid form, never alias one to another.
        for variant in variants:
            official.add(variant)

    return official


def write_lexicon(official: set[str], words_path: Path) -> None:
    words_path.write_text(
        "\n".join(
            [
                "# Official Lortograf forms extracted from Diksioner Kreol Morisyen",
                "# Includes headwords and parenthetical inflected forms (e.g. revini, revinn).",
                "# Source: normalizer/dokumen.pub_diksyoner-kreol-morisyen-mauritian-english-dictionary.pdf",
                "# Regenerate: uv run python normalizer/build_lexicon_from_pdf.py",
                "",
                *sorted(official),
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(__file__).resolve().parent / PDF_NAME,
    )
    args = parser.parse_args()

    official = extract_from_pdf(args.pdf)
    write_lexicon(official, LEXICON_DIR / "words.txt")
    print(f"Extracted {len(official)} official forms (headwords + inflected forms)")
    print(f"Wrote {LEXICON_DIR / 'words.txt'}")
    print(f"ASR spelling aliases: edit {LEXICON_DIR / 'asr_aliases.txt'} manually")


if __name__ == "__main__":
    main()
