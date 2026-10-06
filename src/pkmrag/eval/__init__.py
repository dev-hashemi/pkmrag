"""Evaluation harness and information retrieval benchmarking subsystem."""

from __future__ import annotations

from pkmrag.eval.harness import EvaluationHarness
from pkmrag.eval.models import BenchmarkQuery, EvalMetrics, EvalReport, QueryEvalResult
from pkmrag.eval.views import render_eval_report

__all__ = [
    "BenchmarkQuery",
    "EvalMetrics",
    "EvalReport",
    "EvaluationHarness",
    "QueryEvalResult",
    "render_eval_report",
]
