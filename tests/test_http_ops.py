"""Integration tests for operational endpoints: ingest, discover, llm test, and settings."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from pkmrag.inference.mock import MockInferenceProvider
from pkmrag.ingest import IngestPipeline
from pkmrag.mcp.http_server import create_http_app


def test_http_ops_settings_lifecycle(tmp_path: Path) -> None:
    """Verify settings GET and POST endpoints update vault runtime config."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    app = create_http_app(vault, token="test_token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_token"}

    # 1. GET settings returns defaults
    r_get = client.get("/api/v1/settings", headers=headers)
    assert r_get.status_code == 200
    cfg = r_get.json()
    assert "llm_provider" in cfg

    # 2. POST settings updates configuration
    update_payload = {
        "llm_provider": "custom",
        "llm_base_url": "https://api.deepseek.com/v1",
        "llm_model": "deepseek-chat",
        "llm_api_key": "sk-12345",
    }
    r_post = client.post("/api/v1/settings", json=update_payload, headers=headers)
    assert r_post.status_code == 200
    updated = r_post.json()
    assert updated["llm_provider"] == "custom"
    assert updated["llm_model"] == "deepseek-chat"

    # 3. GET verifies persistence
    r_verify = client.get("/api/v1/settings", headers=headers)
    assert r_verify.status_code == 200
    assert r_verify.json()["llm_model"] == "deepseek-chat"


def test_http_ops_llm_test_endpoint(tmp_path: Path) -> None:
    """Verify /api/v1/llm/test validates credentials and connection latency."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    app = create_http_app(vault, token="test_token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_token"}

    with patch("pkmrag.mcp.http_ops.resolve_provider") as mock_resolve:
        mock_prov = MockInferenceProvider()
        mock_resolve.return_value = mock_prov

        resp = client.post(
            "/api/v1/llm/test",
            json={"provider": "mock", "model": "test-v1"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Mock provider" in data["message"]
        assert data["latency_ms"] >= 0


def test_http_ops_ingest_endpoint(tmp_path: Path) -> None:
    """Verify /api/v1/ingest triggers background vault ingestion."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Note.md").write_text("# Test\n\nContent.")

    app = create_http_app(vault, token="test_token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_token"}

    resp = client.post("/api/v1/ingest", json={"rebuild": True}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_http_ops_discover_endpoint(tmp_path: Path) -> None:
    """Verify /api/v1/discover triggers background gap discovery."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Note1.md").write_text("# Note 1\n\nContent about algorithms.")
    (vault / "Note2.md").write_text("# Note 2\n\nContent about data structures.")
    IngestPipeline(vault).run()

    app = create_http_app(vault, token="test_token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_token"}

    resp = client.post(
        "/api/v1/discover",
        json={"dry_run": True, "threshold": 0.5},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"
