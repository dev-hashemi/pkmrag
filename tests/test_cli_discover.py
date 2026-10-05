"""Tests for orbit discover CLI command."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from orbit.cli import app
from orbit.ingest import IngestPipeline

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


def _setup_vault(vault: Path) -> None:
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Alpha.md").write_text(
        "# Alpha Lock System\n\nDistributed locking algorithm with leases and timeouts.\n"
    )
    (vault / "Beta.md").write_text(
        "# Beta Redlock System\n\nDistributed locking algorithm using Redis nodes.\n"
    )
    pipeline = IngestPipeline(vault, target="all")
    pipeline.run()


def test_cli_discover_help() -> None:
    """Verify orbit discover --help renders options correctly."""
    result = runner.invoke(app, ["discover", "--help"], color=False)
    assert result.exit_code == 0
    clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output)
    assert "threshold" in clean
    assert "limit" in clean
    assert "dry-run" in clean
    assert "provider" in clean


def test_cli_discover_dry_run(tmp_path: Path) -> None:
    """Verify orbit discover --dry-run executes successfully and lists candidates."""
    vault = tmp_path / "vault"
    _setup_vault(vault)

    result = runner.invoke(
        app,
        ["discover", str(vault), "--threshold", "0.4", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "Semantic Gap Candidates" in result.output
    assert "Alpha.md" in result.output
    assert "Beta.md" in result.output


def test_cli_discover_json_dry_run(tmp_path: Path) -> None:
    """Verify orbit discover --dry-run --json outputs structured valid JSON."""
    vault = tmp_path / "vault"
    _setup_vault(vault)

    result = runner.invoke(
        app,
        ["discover", str(vault), "--threshold", "0.4", "--dry-run", "--json"],
    )
    assert result.exit_code == 0
    data = _extract_json(result.output)
    assert data["vault_path"] == str(vault.resolve())

    assert data["dry_run"] is True
    assert "candidates" in data
    assert len(data["candidates"]) >= 1
    assert data["candidates"][0]["source_path"] in ("Alpha.md", "Beta.md")


def test_cli_discover_ollama_flag(tmp_path: Path) -> None:
    """Verify orbit discover accepts --provider ollama and --model flags."""
    vault = tmp_path / "vault"
    _setup_vault(vault)

    result = runner.invoke(
        app,
        [
            "discover",
            str(vault),
            "--provider",
            "ollama",
            "--model",
            "llama3.2",
            "--threshold",
            "0.4",
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0
    data = _extract_json(result.output)
    assert data["dry_run"] is True
    assert "candidates" in data
