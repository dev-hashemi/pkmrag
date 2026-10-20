"""Tests for graceful handling of a vault database locked by another process."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Generator

import pytest
from typer.testing import CliRunner

from pkmrag.cli import app
from pkmrag.graph.store import GraphStore, GraphStoreLockedError
from pkmrag.ingest import IngestPipeline

runner = CliRunner()

HOLD_LOCK_SCRIPT = """
import sys, time
from pathlib import Path
from pkmrag.graph.store import GraphStore

db_dir = Path(sys.argv[1])
sentinel = Path(sys.argv[2])
store = GraphStore(db_dir, read_only=False)
sentinel.write_text("locked")
time.sleep(60)
"""


@pytest.fixture
def locked_vault(tmp_path: Path) -> Generator[Path, None, None]:
    """Create an indexed vault and hold its graph database from another process."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Alpha.md").write_text("# Alpha\n\nSome content about locks.\n")
    (vault / "Beta.md").write_text("# Beta\n\nSome content about locks.\n")
    IngestPipeline(vault, target="all").run()

    sentinel = tmp_path / "locked.flag"
    holder = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", HOLD_LOCK_SCRIPT, str(vault / ".pkmrag" / "graph"), str(sentinel)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 30
    while time.time() < deadline and not sentinel.exists():
        time.sleep(0.1)
    if not sentinel.exists():
        holder.terminate()
        pytest.fail("Helper process did not acquire the vault database lock")

    try:
        yield vault
    finally:
        holder.terminate()
        holder.wait(timeout=15)


def test_graph_store_raises_locked_error(locked_vault: Path) -> None:
    """Opening the vault graph read-write must fail with a domain error, not a driver error."""
    with pytest.raises(GraphStoreLockedError):
        GraphStore(locked_vault / ".pkmrag" / "graph", read_only=False)


def test_graph_store_read_only_still_works(locked_vault: Path) -> None:
    """Read-only access must remain available while another process holds the lock."""
    store = GraphStore(locked_vault / ".pkmrag" / "graph", read_only=True)
    try:
        assert store.get_stats().get("notes", 0) >= 2
    finally:
        store.close()


def test_cli_discover_reports_locked_database(locked_vault: Path) -> None:
    """The CLI must print an actionable message instead of a driver traceback."""
    result = runner.invoke(app, ["discover", str(locked_vault)])
    assert result.exit_code == 1
    assert "locked" in result.output.lower()
    assert "Traceback" not in result.output


def test_cli_discover_dry_run_works_while_locked(locked_vault: Path) -> None:
    """A read-only dry run must succeed even while the daemon holds the vault database."""
    result = runner.invoke(app, ["discover", str(locked_vault), "--dry-run"])
    assert result.exit_code == 0
