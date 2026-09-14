"""Tests for the Orbit diagnostic health checks and CLI."""

from typer.testing import CliRunner

from orbit.cli import app
from orbit.doctor import check_kuzu_engine, check_lancedb_engine, get_system_info, run_diagnostics

runner = CliRunner()


def test_system_info() -> None:
    """Verify system info collection contains all essential keys."""
    info = get_system_info()
    assert "os" in info
    assert "arch" in info
    assert "python" in info
    assert "python_path" in info
    assert "virtual_env" in info


def test_kuzu_engine_health() -> None:
    """Verify that in-memory Kùzu database passes transactional read/write."""
    result = check_kuzu_engine()
    assert result.passed is True
    assert result.name == "Kùzu Property Graph"
    assert result.latency_ms > 0
    assert "verified" in result.details.lower()


def test_lancedb_engine_health() -> None:
    """Verify that LanceDB vector engine passes write and ANN query."""
    result = check_lancedb_engine()
    assert result.passed is True
    assert result.name == "LanceDB Vector Engine"
    assert result.latency_ms > 0
    assert "verified" in result.details.lower()


def test_run_diagnostics() -> None:
    """Verify aggregate diagnostics report."""
    report = run_diagnostics()
    assert report.all_passed is True
    assert len(report.checks) == 2


def test_cli_version() -> None:
    """Verify orbit --version command."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.0.1" in result.stdout


def test_cli_doctor_text() -> None:
    """Verify orbit doctor standard output."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Kùzu Property Graph" in result.stdout
    assert "LanceDB Vector Engine" in result.stdout
    assert "PASS" in result.stdout


def test_cli_doctor_json() -> None:
    """Verify orbit doctor --json output format."""
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    stdout_lower = result.stdout.lower()
    assert '"all_passed": true' in stdout_lower or '"passed": true' in stdout_lower
