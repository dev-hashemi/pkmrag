"""Pydantic models for semantic gap discovery, token estimation, and metrics."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidatePairSummary(BaseModel):
    """Summary of a candidate pair evaluated or proposed for relationship discovery."""

    source_path: str
    target_path: str
    source_title: str
    target_title: str
    similarity: float


class DiscoveryEstimate(BaseModel):
    """Pre-flight estimation of token usage and candidate count before LLM inference."""

    candidate_count: int
    evaluated_count: int
    estimated_prompt_tokens: int
    estimated_completion_tokens: int
    total_tokens: int
    provider: str
    model: str
    candidate_pairs: list[CandidatePairSummary] = Field(default_factory=list)


class DiscoveryStats(BaseModel):
    """Summary metrics from a semantic gap discovery run."""

    vault_path: str
    total_notes_scanned: int
    vector_candidates_found: int
    graph_filtered_candidates: int
    relationships_inferred: int
    duration_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_saved_by_graph: int = 0
