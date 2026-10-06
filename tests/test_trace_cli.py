"""Integration tests for CLI execution tracing via --trace flag."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pkmrag.cli import app
from pkmrag.telemetry import shutdown_telemetry

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_telemetry() -> Generator[None, None, None]:
    """Ensure clean telemetry state for CLI tests."""
    shutdown_telemetry()
    yield
    shutdown_telemetry()


def test_cli_search_with_trace_flag(tmp_path: Path) -> None:
    """orbit search --trace outputs both search results and Rich waterfall trace tree."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "NoteA.md").write_text("# Note A\nFast embedded search engine.\n", encoding="utf-8")
    (vault / "NoteB.md").write_text(
        "# Note B\nLadybug graph and LanceDB vector.\n", encoding="utf-8"
    )

    # Ingest vault first
    res_ingest = runner.invoke(app, ["ingest", str(vault)])
    assert res_ingest.exit_code == 0

    # Search with --trace
    res = runner.invoke(app, ["search", "embedded search", "--vault", str(vault), "--trace"])
    assert res.exit_code == 0

    # Verify search result is present
    assert "NoteA.md" in res.stdout

    # Verify OpenTelemetry trace tree rendering is present
    assert "Trace: pkmrag.search" in res.stdout
    assert "cache.lookup" in res.stdout
    assert "embed.query" in res.stdout


def test_cli_ingest_with_trace_flag(tmp_path: Path) -> None:
    """orbit ingest --trace outputs both ingestion report and execution trace tree."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "Doc1.md").write_text("# Doc 1\nKnowledge base architecture.\n", encoding="utf-8")

    res = runner.invoke(app, ["ingest", str(vault), "--trace"])
    assert res.exit_code == 0
    assert "Trace: pkmrag.ingest" in res.stdout
    assert "ingest.scan_files" in res.stdout


def test_cli_discover_with_trace_flag(tmp_path: Path) -> None:
    """orbit discover --trace outputs discovery report and execution trace tree."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "Page1.md").write_text("# Page 1\nRaft consensus.\n", encoding="utf-8")
    (vault / "Page2.md").write_text("# Page 2\nPaxos consensus.\n", encoding="utf-8")

    runner.invoke(app, ["ingest", str(vault)])

    res = runner.invoke(app, ["discover", str(vault), "--dry-run", "--trace"])
    assert res.exit_code == 0
    assert "Trace: pkmrag.discover" in res.stdout
    assert "gap.graph_filter" in res.stdout
