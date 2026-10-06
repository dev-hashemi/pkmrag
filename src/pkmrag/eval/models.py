"""Domain models for retrieval benchmark evaluation."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BenchmarkQuery(BaseModel):
    """A curated evaluation query with ground-truth expected notes."""

    id: str
    query: str
    expected_notes: list[str]
    near: Optional[str] = None
    mode: str = "hybrid"
    category: Optional[str] = None


class QueryEvalResult(BaseModel):
    """Detailed evaluation metrics for a single query."""

    query_id: str
    query: str
    near: Optional[str] = None
    expected_notes: list[str]
    retrieved_notes: list[str]
    first_hit_rank: Optional[int] = None
    reciprocal_rank: float = 0.0
    recall: float = 0.0
    precision: float = 0.0
    average_precision: float = 0.0
    is_multi_hop: bool = False
    multi_hop_complete: bool = False


class EvalMetrics(BaseModel):
    """Aggregated information retrieval metrics across the benchmark dataset."""

    total_queries: int = 0
    mrr: float = 0.0
    hits_at_1: float = 0.0
    hits_at_3: float = 0.0
    hits_at_5: float = 0.0
    mean_recall_at_5: float = 0.0
    mean_precision_at_5: float = 0.0
    map_at_5: float = 0.0
    multi_hop_queries: int = 0
    multi_hop_completeness: float = 0.0


class EvalReport(BaseModel):
    """Complete benchmark evaluation report with pass/fail gates."""

    benchmark_file: str
    vault_path: str
    metrics: EvalMetrics
    results: list[QueryEvalResult]
    passed: bool
    failure_reasons: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
