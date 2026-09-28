"""Evaluation benchmark against the Golden 10 dataset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbit.ingest import IngestPipeline
from orbit.search import SearchService

BENCHMARK_PATH = Path(__file__).resolve().parent.parent / "benchmarks" / "golden_10.json"
TEST_VAULT_PATH = Path("/home/ali/Vaults/orbit-test-vault")


@pytest.mark.skipif(
    not TEST_VAULT_PATH.exists(),
    reason="Test vault /home/ali/Vaults/orbit-test-vault not found",
)
def test_golden_10_evaluation() -> None:
    """Evaluate retrieval accuracy on the 10 Golden Queries."""
    assert BENCHMARK_PATH.exists()
    dataset = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

    # Ensure test vault is indexed
    pipeline = IngestPipeline(TEST_VAULT_PATH, target="all")
    pipeline.run()

    reciprocal_ranks: list[float] = []
    hits_at_3: int = 0

    with SearchService(TEST_VAULT_PATH) as service:
        for entry in dataset:
            query = entry["query"]
            near = entry.get("near")
            expected_notes = entry["expected_notes"]

            results = service.search(query=query, near=near, mode="hybrid", limit=5)
            hit_rank = 0
            for rank, r in enumerate(results, start=1):
                if any(r.note_path == exp for exp in expected_notes):
                    hit_rank = rank
                    break

            if hit_rank > 0:
                reciprocal_ranks.append(1.0 / hit_rank)
                if hit_rank <= 3:
                    hits_at_3 += 1
            else:
                reciprocal_ranks.append(0.0)

    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    hit_rate_at_3 = hits_at_3 / len(dataset)

    # Assert high retrieval performance on the ground truth benchmark
    assert mrr >= 0.80, f"MRR {mrr:.2f} is below 0.80"
    assert hit_rate_at_3 >= 0.90, f"Hits@3 {hit_rate_at_3:.2f} is below 0.90"
