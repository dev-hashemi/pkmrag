"""Ground-truth evaluation benchmark against the 50-query Obsidian Help dataset."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from orbit.search import SearchService

BENCHMARK_PATH = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "golden_50_obsidian_help.json"
)
TEST_VAULT_PATH = Path("/home/ali/Vaults/obsidian-help")


@pytest.mark.skipif(
    not TEST_VAULT_PATH.exists(),
    reason="Obsidian Help vault not found at /home/ali/Vaults/obsidian-help",
)
def test_obsidian_help_golden_50_evaluation() -> None:
    """Evaluate retrieval accuracy on the 50 Obsidian Help benchmark queries."""
    assert BENCHMARK_PATH.exists(), f"Benchmark file missing: {BENCHMARK_PATH}"
    dataset: list[dict[str, Any]] = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    assert len(dataset) == 50, f"Expected 50 queries, found {len(dataset)}"

    reciprocal_ranks: list[float] = []
    hits_at_1: int = 0
    hits_at_3: int = 0
    hits_at_5: int = 0

    category_stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0.0, "mrr_sum": 0.0, "h1": 0.0, "h3": 0.0, "h5": 0.0}
    )

    with SearchService(TEST_VAULT_PATH) as service:
        for entry in dataset:
            query: str = entry["query"]
            near: str | None = entry.get("near")
            expected_notes: list[str] = entry["expected_notes"]
            category: str = entry.get("category", "unknown")

            results = service.search(query=query, near=near, mode="hybrid", limit=10)

            hit_rank = 0
            for rank, r in enumerate(results, start=1):
                if any(r.note_path == exp for exp in expected_notes):
                    hit_rank = rank
                    break

            rr = 1.0 / hit_rank if hit_rank > 0 else 0.0
            reciprocal_ranks.append(rr)

            h1 = 1 if 0 < hit_rank <= 1 else 0
            h3 = 1 if 0 < hit_rank <= 3 else 0
            h5 = 1 if 0 < hit_rank <= 5 else 0

            hits_at_1 += h1
            hits_at_3 += h3
            hits_at_5 += h5

            stats = category_stats[category]
            stats["count"] += 1.0
            stats["mrr_sum"] += rr
            stats["h1"] += h1
            stats["h3"] += h3
            stats["h5"] += h5

    total = len(dataset)
    mrr = sum(reciprocal_ranks) / total
    hit_rate_at_1 = hits_at_1 / total
    hit_rate_at_3 = hits_at_3 / total
    hit_rate_at_5 = hits_at_5 / total

    print("\n" + "=" * 68)
    print("OBSIDIAN HELP 50-QUERY BENCHMARK EVALUATION RESULTS")
    print("=" * 68)
    for cat, stats in category_stats.items():
        cat_count = int(stats["count"])
        cat_mrr = stats["mrr_sum"] / cat_count if cat_count else 0.0
        cat_h1 = (stats["h1"] / cat_count) * 100 if cat_count else 0.0
        cat_h3 = (stats["h3"] / cat_count) * 100 if cat_count else 0.0
        cat_h5 = (stats["h5"] / cat_count) * 100 if cat_count else 0.0
        print(
            f"Category [{cat:16s}]: {cat_count:2d} queries | "
            f"MRR: {cat_mrr:.3f} | H@1: {cat_h1:5.1f}% | H@3: {cat_h3:5.1f}% | H@5: {cat_h5:5.1f}%"
        )
    print("-" * 68)
    print(
        f"OVERALL (n={total}): "
        f"MRR: {mrr:.3f} | Hits@1: {hit_rate_at_1 * 100:.1f}% | "
        f"Hits@3: {hit_rate_at_3 * 100:.1f}% | Hits@5: {hit_rate_at_5 * 100:.1f}%"
    )
    print("=" * 68 + "\n")

    # Benchmark assertions
    assert mrr >= 0.70, f"MRR {mrr:.3f} is below 0.70 threshold"
    assert hit_rate_at_3 >= 0.75, f"Hits@3 {hit_rate_at_3:.3f} is below 0.75 threshold"
    assert hit_rate_at_5 >= 0.80, f"Hits@5 {hit_rate_at_5:.3f} is below 0.80 threshold"
