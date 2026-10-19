"""Unit tests for weighted catalog sampling."""

import random

from apps.annotator.api.catalog_sample import CatalogCandidate, sample_catalog


def _c(sid: int, slug: str, minutes: float) -> CatalogCandidate:
    return CatalogCandidate(source_id=sid, category_slug=slug, duration_sec=minutes * 60)


def test_sample_respects_target_and_weights():
    candidates = [
        _c(1, "komiko", 30),
        _c(2, "komiko", 30),
        _c(3, "komiko", 60),
        _c(4, "lir-ekril", 45),
        _c(5, "lir-ekril", 45),
        _c(6, "tempo-la-so", 20),
        _c(7, "tempo-la-so", 40),
        _c(8, "tempo-la-so", 40),
    ]
    result = sample_catalog(
        candidates,
        target_hours=2.0,
        weights={"komiko": 1, "lir-ekril": 1, "tempo-la-so": 1},
        rng=random.Random(42),
    )
    assert result["source_ids"]
    assert all(isinstance(i, int) for i in result["source_ids"])
    assert result["total_seconds"] > 0
    # Should not invent ids
    assert set(result["source_ids"]).issubset({1, 2, 3, 4, 5, 6, 7, 8})
    # Roughly near 2h (allow overshoot from discrete clips)
    assert result["total_seconds"] <= 2.0 * 3600 + 60 * 60


def test_sample_empty_candidates():
    result = sample_catalog([], target_hours=10, weights={"komiko": 1})
    assert result["source_ids"] == []
    assert result["total_seconds"] == 0


def test_sample_ignores_zero_weight_categories():
    candidates = [_c(1, "komiko", 60), _c(2, "tempo-la-so", 60)]
    result = sample_catalog(
        candidates,
        target_hours=1.0,
        weights={"komiko": 1, "tempo-la-so": 0},
        rng=random.Random(0),
    )
    assert 2 not in result["source_ids"]
    assert all(
        c.category_slug != "tempo-la-so"
        for c in candidates
        if c.source_id in result["source_ids"]
    )


def test_sample_only_from_given_pool():
    candidates = [_c(10, "komiko", 30), _c(11, "komiko", 30)]
    result = sample_catalog(
        candidates,
        target_hours=10,
        weights={"komiko": 1},
        rng=random.Random(1),
    )
    assert set(result["source_ids"]).issubset({10, 11})
