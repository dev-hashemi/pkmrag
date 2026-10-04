"""Integration tests for the `orbit eval` CLI command and EvaluationHarness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from orbit.cli import app
from orbit.eval.harness import EvaluationHarness

runner = CliRunner()


def _extract_json(text: str) -> Any:
    """Robustly extract and parse JSON payload from CLI output, ignoring warning lines."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    clean_lines = [
        line
        for line in text.splitlines()
        if not (
            line.startswith("[") and any(lvl in line for lvl in ("WARN", "INFO", "ERROR", "DEBUG"))
        )
    ]
    candidate = "\n".join(clean_lines).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = candidate.find(start_char)
        end = candidate.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue

    return json.loads(text)


def test_eval_cli_default() -> None:
    """Verify orbit eval runs against default in-repo benchmark and passes."""
    result = runner.invoke(app, ["eval"])
    assert result.exit_code == 0
    assert "Retrieval Evaluation Summary" in result.output
    assert "All quality gates passed" in result.output
    assert "Mean Reciprocal Rank" in result.output


def test_eval_cli_json() -> None:
    """Verify orbit eval --json outputs valid JSON report with metrics."""
    result = runner.invoke(app, ["eval", "--json"])
    assert result.exit_code == 0
    data = _extract_json(result.output)
    assert data["passed"] is True
    assert "metrics" in data
    assert data["metrics"]["total_queries"] == 10
    assert data["metrics"]["mrr"] >= 0.80
    assert data["metrics"]["mean_recall_at_5"] >= 0.80
    assert len(data["results"]) == 10


def test_eval_cli_threshold_failure_mrr() -> None:
    """Verify orbit eval exits with code 1 when MRR threshold is not met."""
    result = runner.invoke(app, ["eval", "--min-mrr", "0.999"])
    assert result.exit_code == 1
    assert "Retrieval regression detected" in result.output
    assert "MRR" in result.output


def test_eval_cli_threshold_failure_recall() -> None:
    """Verify orbit eval exits with code 1 when Recall threshold is not met."""
    result = runner.invoke(app, ["eval", "--min-recall", "0.999"])
    assert result.exit_code == 1
    assert "Retrieval regression detected" in result.output
    assert "Recall@5" in result.output


def test_eval_cli_explicit_paths() -> None:
    """Verify orbit eval with explicit vault path and benchmark arguments."""
    vault = Path(__file__).resolve().parent.parent / "benchmarks" / "vault"
    bench = Path(__file__).resolve().parent.parent / "benchmarks" / "golden_10.json"

    result = runner.invoke(app, ["eval", str(vault), "-b", str(bench)])
    assert result.exit_code == 0
    assert "All quality gates passed" in result.output


def test_eval_harness_missing_benchmark() -> None:
    """Verify EvaluationHarness raises FileNotFoundError when benchmark is missing."""
    with pytest.raises(FileNotFoundError, match="Benchmark dataset JSON not found"):
        EvaluationHarness(benchmark_path=Path("/nonexistent/bench.json"))


def test_eval_harness_missing_vault() -> None:
    """Verify EvaluationHarness raises FileNotFoundError when vault is missing."""
    with pytest.raises(FileNotFoundError, match="Evaluation vault directory not found"):
        EvaluationHarness(vault_path=Path("/nonexistent/vault"))
