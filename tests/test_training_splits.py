"""Tests for training split helpers."""

import pytest

from training.metrics import gate_passes
from training.splits import SplitError, assign_dev_split, validate_test_split


def test_assign_dev_split_stratified():
    rows = [
        {"lang": "kreol", "split": "train", "duration": 10, "source_id": 1, "segment_id": i}
        for i in range(10)
    ] + [
        {"lang": "fr", "split": "train", "duration": 10, "source_id": 1, "segment_id": 100 + i}
        for i in range(10)
    ]
    out = assign_dev_split(rows, fraction=0.1, seed=42)
    dev = [r for r in out if r["split"] == "dev"]
    train = [r for r in out if r["split"] == "train"]
    assert len(dev) >= 2
    assert len(train) >= 16


def test_validate_test_split_requires_test():
    with pytest.raises(SplitError):
        validate_test_split([{"split": "train", "duration": 3600}], min_test_seconds=1200)


def test_gate_passes_all_languages():
    baseline = {
        "kreol": {"wer": 0.5, "cer": 0.3},
        "fr": {"wer": 0.2, "cer": 0.1},
    }
    better = {
        "kreol": {"wer": 0.4, "cer": 0.25},
        "fr": {"wer": 0.15, "cer": 0.08},
    }
    ok, reasons = gate_passes(better, baseline)
    assert ok
    assert reasons == []

    worse = {
        "kreol": {"wer": 0.6, "cer": 0.25},
        "fr": {"wer": 0.15, "cer": 0.08},
    }
    ok2, reasons2 = gate_passes(worse, baseline)
    assert not ok2
    assert reasons2
