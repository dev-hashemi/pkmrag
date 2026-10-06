"""Tests for the Orbit diagnostic health checks and CLI."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from pkmrag import __version__
from pkmrag.cli import app
from pkmrag.doctor import (
    check_ladybug_engine,
    check_lancedb_engine,
    check_ollama_engine,
    get_system_info,
    run_diagnostics,
)

runner = CliRunner()


def test_system_info() -> None:
    """Verify system info collection contains all essential keys."""
    info = get_system_info()
    assert "os" in info
    assert "arch" in info
    assert "python" in info
    assert "python_path" in info
    assert "virtual_env" in info


def test_ladybug_engine_health() -> None:
    """Verify that in-memory LadybugDB database passes transactional read/write."""
    result = check_ladybug_engine()
    assert result.passed is True
    assert result.name == "LadybugDB Property Graph"
    assert result.latency_ms > 0
    assert "verified" in result.details.lower()


def test_lancedb_engine_health() -> None:
    """Verify that LanceDB vector engine passes write and ANN query."""
    result = check_lancedb_engine()
    assert result.passed is True
    assert result.name == "LanceDB Vector Engine"
    assert result.latency_ms > 0
    assert "verified" in result.details.lower()


def test_ollama_engine_offline() -> None:
    """Verify Ollama engine health check returns non-blocking status when offline."""
    result = check_ollama_engine("http://127.0.0.1:9999")
    assert result.passed is True
    assert result.name == "Ollama Local Engine"
    assert result.version == "n/a"
    assert result.extra.get("active") is False
    assert "not detected" in result.details.lower()


def test_ollama_engine_online_mock() -> None:
    """Verify Ollama engine health check extracts models when server is responsive."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "version": "0.3.12",
        "models": [{"name": "llama3.2:latest"}, {"name": "nomic-embed-text:latest"}],
    }
    with patch("httpx.Client.get", return_value=mock_resp):
        result = check_ollama_engine("http://localhost:11434")
        assert result.passed is True
        assert result.version == "0.3.12"
        assert result.extra.get("active") is True
        assert "llama3.2:latest" in result.details


def test_run_diagnostics() -> None:
    """Verify aggregate diagnostics report."""
    report = run_diagnostics()
    assert report.all_passed is True
    assert len(report.checks) == 3


def test_cli_version() -> None:
    """Verify orbit --version command."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_doctor_text() -> None:
    """Verify orbit doctor standard output."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "LadybugDB" in result.stdout
    assert "LanceDB" in result.stdout
    assert "PASS" in result.stdout


def test_cli_doctor_json() -> None:
    """Verify orbit doctor --json output format."""
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    stdout_lower = result.stdout.lower()
    assert '"all_passed": true' in stdout_lower or '"passed": true' in stdout_lower
