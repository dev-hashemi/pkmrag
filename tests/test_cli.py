"""Integration tests for Project Orbit CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from orbit import __version__
from orbit.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    """Verify orbit --version outputs the correct version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_doctor_json() -> None:
    """Verify orbit doctor --json executes and outputs valid JSON report."""
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "system_info" in data
    assert "checks" in data
    assert len(data["checks"]) >= 2


def test_cli_mcp_config(mock_vault: Path) -> None:
    """Verify orbit mcp-config outputs JSON configuration containing vault path."""
    result = runner.invoke(app, ["mcp-config", str(mock_vault)])
    assert result.exit_code == 0
    assert "mcpServers" in result.output
    assert "orbit" in result.output
    assert str(mock_vault.resolve()) in result.output


def test_cli_ingest_and_search_json(mock_vault: Path) -> None:
    """Verify orbit ingest --json indexes notes and orbit search --json finds results."""
    # 1. Ingest
    ingest_res = runner.invoke(app, ["ingest", str(mock_vault), "--target", "all", "--json"])
    assert ingest_res.exit_code == 0
    ingest_data = json.loads(ingest_res.output)
    assert ingest_data["notes_scanned"] == 3
    assert ingest_data["total_notes"] >= 3

    # 2. Search
    search_res = runner.invoke(
        app,
        ["search", "architecture", "--vault", str(mock_vault), "--json"],
    )
    assert search_res.exit_code == 0
    results = json.loads(search_res.output)
    assert isinstance(results, list)
    assert len(results) >= 1
    assert any("Alpha.md" in r["note_path"] for r in results)
