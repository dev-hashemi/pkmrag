"""Tests for orbit discover CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from orbit.cli import app
from orbit.ingest import IngestPipeline

runner = CliRunner()


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
    result = runner.invoke(app, ["discover", "--help"])
    assert result.exit_code == 0
    assert "--threshold" in result.output
    assert "--limit" in result.output
    assert "--dry-run" in result.output
    assert "--json" in result.output


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
    data = json.loads(result.output)
    assert data["vault_path"] == str(vault.resolve())
    assert data["dry_run"] is True
    assert "candidates" in data
    assert len(data["candidates"]) >= 1
    assert data["candidates"][0]["source_path"] in ("Alpha.md", "Beta.md")
