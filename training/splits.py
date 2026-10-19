"""Train/dev/test split helpers for the training dataset."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any


class SplitError(ValueError):
    pass


def assign_dev_split(
    rows: list[dict[str, Any]],
    *,
    fraction: float = 0.08,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Carve dev rows from train pool (non-test), stratified by lang."""
    train_pool = [r for r in rows if r.get("split") != "test"]
    test_rows = [r for r in rows if r.get("split") == "test"]
    if not train_pool:
        return rows

    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in train_pool:
        by_lang[row.get("lang", "mix")].append(row)

    rng = random.Random(seed)
    dev_ids: set[str] = set()
    for lang_rows in by_lang.values():
        n_dev = max(1, int(len(lang_rows) * fraction)) if len(lang_rows) >= 2 else 0
        if n_dev:
            picked = rng.sample(lang_rows, min(n_dev, len(lang_rows)))
            dev_ids.update(_row_id(r) for r in picked)

    out: list[dict[str, Any]] = []
    for row in train_pool:
        item = dict(row)
        item["split"] = "dev" if _row_id(row) in dev_ids else "train"
        out.extend([item])
    out.extend(test_rows)
    return out


def validate_test_split(rows: list[dict[str, Any]], *, min_test_seconds: float) -> None:
    test_rows = [r for r in rows if r.get("split") == "test"]
    if not test_rows:
        raise SplitError("No frozen test split found. Mark a source as frozen test before training.")
    total_sec = sum(float(r.get("duration", 0)) for r in test_rows)
    if total_sec < min_test_seconds:
        raise SplitError(
            f"Frozen test set is only {total_sec / 60:.1f} min; need at least {min_test_seconds / 60:.0f} min."
        )
    langs = {r.get("lang") for r in test_rows}
    if len(langs) < 2:
        raise SplitError("Frozen test set should cover multiple languages (kreol/fr/en/mix).")


def _row_id(row: dict[str, Any]) -> str:
    return f"{row.get('source_id')}:{row.get('segment_id', row.get('audio_path'))}"
