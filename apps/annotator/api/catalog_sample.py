"""Weighted random sample from the Downloaded catalog (no promote)."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogCandidate:
    source_id: int
    category_slug: str
    duration_sec: float


def sample_catalog(
    candidates: list[CatalogCandidate],
    *,
    target_hours: float,
    weights: dict[str, float],
    rng: random.Random | None = None,
) -> dict:
    """Greedy weighted mix. Returns ids + seconds by category (does not promote)."""
    rng = rng or random.Random()
    target_sec = max(0.0, float(target_hours) * 3600.0)
    if target_sec <= 0 or not candidates:
        return {"source_ids": [], "seconds_by_category": {}, "total_seconds": 0.0}

    by_cat: dict[str, list[CatalogCandidate]] = {}
    for c in candidates:
        if c.duration_sec <= 0:
            continue
        by_cat.setdefault(c.category_slug, []).append(c)

    active_slugs = [s for s in by_cat if weights.get(s, 0) > 0]
    if not active_slugs:
        # Equal weights across available categories when none specified
        active_slugs = list(by_cat.keys())
        weights = {s: 1.0 for s in active_slugs}
    weight_sum = sum(max(0.0, float(weights.get(s, 0))) for s in active_slugs)
    if weight_sum <= 0:
        return {"source_ids": [], "seconds_by_category": {}, "total_seconds": 0.0}

    budgets = {
        s: target_sec * (max(0.0, float(weights.get(s, 0))) / weight_sum) for s in active_slugs
    }
    pools: dict[str, list[CatalogCandidate]] = {
        s: list(by_cat[s]) for s in active_slugs
    }
    for pool in pools.values():
        rng.shuffle(pool)

    selected: list[CatalogCandidate] = []
    used: set[int] = set()
    seconds_by_category: dict[str, float] = {s: 0.0 for s in active_slugs}

    def try_fill(slug: str, budget: float) -> None:
        pool = pools[slug]
        while pool and seconds_by_category[slug] < budget:
            # Prefer a clip that fits remaining budget; else take shortest leftover
            remaining = budget - seconds_by_category[slug]
            fit = [c for c in pool if c.source_id not in used and c.duration_sec <= remaining]
            if fit:
                pick = fit[0]
            else:
                leftovers = [c for c in pool if c.source_id not in used]
                if not leftovers:
                    break
                # Avoid huge overshoot if something shorter exists later — pick shortest
                pick = min(leftovers, key=lambda c: c.duration_sec)
                if seconds_by_category[slug] > 0 and pick.duration_sec > remaining * 1.5:
                    break
            pool.remove(pick)
            used.add(pick.source_id)
            selected.append(pick)
            seconds_by_category[slug] += pick.duration_sec

    for slug in active_slugs:
        try_fill(slug, budgets[slug])

    # Spill leftover budget across categories still having stock
    total = sum(seconds_by_category.values())
    leftover = target_sec - total
    if leftover > 30:
        spill_order = list(active_slugs)
        rng.shuffle(spill_order)
        for slug in spill_order:
            if leftover <= 30:
                break
            before = seconds_by_category[slug]
            try_fill(slug, before + leftover)
            gained = seconds_by_category[slug] - before
            leftover -= gained

    total_seconds = sum(seconds_by_category.values())
    return {
        "source_ids": [c.source_id for c in selected],
        "seconds_by_category": {k: v for k, v in seconds_by_category.items() if v > 0},
        "total_seconds": total_seconds,
    }
