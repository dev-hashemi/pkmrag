"""Benchmark evaluation harness orchestrating search queries and threshold scoring."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from pkmrag.config import settings
from pkmrag.eval.metrics import (
    aggregate_metrics,
    compute_average_precision,
    compute_precision_at_k,
    compute_recall_at_k,
    compute_reciprocal_rank,
)
from pkmrag.eval.models import BenchmarkQuery, EvalReport, QueryEvalResult
from pkmrag.ingest import IngestPipeline
from pkmrag.search import SearchService


def get_default_benchmark_vault_path() -> Path:
    """Resolve in-repo default benchmark vault directory."""
    return (Path(__file__).resolve().parent.parent.parent.parent / "benchmarks" / "vault").resolve()


def get_default_benchmark_dataset_path() -> Path:
    """Resolve in-repo default golden_10.json dataset path."""
    return (
        Path(__file__).resolve().parent.parent.parent.parent / "benchmarks" / "golden_10.json"
    ).resolve()


class EvaluationHarness:
    """Executes benchmark queries against a vault and checks regression gates."""

    def __init__(
        self,
        vault_path: Optional[Path | str] = None,
        benchmark_path: Optional[Path | str] = None,
    ) -> None:
        self.vault_path = (
            Path(vault_path).resolve() if vault_path else get_default_benchmark_vault_path()
        )
        self.benchmark_path = (
            Path(benchmark_path).resolve()
            if benchmark_path
            else get_default_benchmark_dataset_path()
        )

        if not self.vault_path.exists():
            raise FileNotFoundError(f"Evaluation vault directory not found: {self.vault_path}")
        if not self.benchmark_path.exists():
            raise FileNotFoundError(f"Benchmark dataset JSON not found: {self.benchmark_path}")

    def _ensure_indexed(self) -> None:
        """Verify storage directories exist, automatically indexing if missing."""
        db_dir = settings.get_db_dir(self.vault_path)
        vec_dir = settings.get_vector_dir(self.vault_path)
        if not db_dir.exists() or not vec_dir.exists():
            pipeline = IngestPipeline(self.vault_path, target="all")
            pipeline.run()

    def run(
        self,
        limit: int = 5,
        min_mrr: float = 0.80,
        min_recall: float = 0.80,
    ) -> EvalReport:
        """Run benchmark evaluation and assert quality thresholds."""
        t0 = time.perf_counter()
        self._ensure_indexed()

        raw_data = json.loads(self.benchmark_path.read_text(encoding="utf-8"))
        queries = [BenchmarkQuery.model_validate(q) for q in raw_data]

        query_results: list[QueryEvalResult] = []

        with SearchService(self.vault_path) as service:
            for q in queries:
                search_hits = service.search(
                    query=q.query,
                    near=q.near,
                    mode=q.mode,
                    limit=limit,
                )

                # Extract unique note paths preserving retrieval rank
                seen: set[str] = set()
                retrieved_notes: list[str] = []
                for hit in search_hits:
                    if hit.note_path not in seen:
                        seen.add(hit.note_path)
                        retrieved_notes.append(hit.note_path)

                rank, rr = compute_reciprocal_rank(retrieved_notes, q.expected_notes)
                recall = compute_recall_at_k(retrieved_notes, q.expected_notes)
                precision = compute_precision_at_k(retrieved_notes, q.expected_notes)
                ap = compute_average_precision(retrieved_notes, q.expected_notes)

                is_multi_hop = len(q.expected_notes) >= 2
                multi_hop_complete = is_multi_hop and (recall >= 1.0)

                query_results.append(
                    QueryEvalResult(
                        query_id=q.id,
                        query=q.query,
                        near=q.near,
                        expected_notes=q.expected_notes,
                        retrieved_notes=retrieved_notes,
                        first_hit_rank=rank,
                        reciprocal_rank=rr,
                        recall=recall,
                        precision=precision,
                        average_precision=ap,
                        is_multi_hop=is_multi_hop,
                        multi_hop_complete=multi_hop_complete,
                    )
                )

        metrics = aggregate_metrics(query_results)

        failure_reasons: list[str] = []
        if metrics.mrr < min_mrr:
            failure_reasons.append(
                f"MRR score {metrics.mrr:.3f} is below minimum threshold {min_mrr:.3f}"
            )
        if metrics.mean_recall_at_5 < min_recall:
            failure_reasons.append(
                f"Context Recall {metrics.mean_recall_at_5:.3f} is below target {min_recall:.3f}"
            )

        duration = round((time.perf_counter() - t0) * 1000, 2)
        passed = len(failure_reasons) == 0

        return EvalReport(
            benchmark_file=str(self.benchmark_path),
            vault_path=str(self.vault_path),
            metrics=metrics,
            results=query_results,
            passed=passed,
            failure_reasons=failure_reasons,
            duration_ms=duration,
        )
