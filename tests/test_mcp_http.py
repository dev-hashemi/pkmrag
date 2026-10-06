"""Integration tests for MCP HTTP/SSE Starlette server and REST endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from pkmrag.ingest import IngestPipeline
from pkmrag.mcp.http_server import create_http_app, run_server


@pytest.fixture
def populated_vault(tmp_path: Path) -> Path:
    """Create and index a temporary two-note vault."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Alpha.md").write_text("# Alpha Node\n\nDiscussion on [[Beta]] architecture.\n#arch")
    (vault / "Beta.md").write_text("# Beta Node\n\nDetailed specifications.\n#arch")

    pipeline = IngestPipeline(vault, target="all")
    pipeline.run()
    return vault


def test_http_health_endpoint_public(populated_vault: Path) -> None:
    """Verify /health endpoint is accessible without authentication."""
    app = create_http_app(populated_vault, token="secure_test_token")
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["vault"] == populated_vault.name
    assert data["transport"] == "sse"
    assert data["auth_enabled"] is True


def test_http_auth_enforcement(populated_vault: Path) -> None:
    """Verify unauthorized requests are rejected and valid tokens are accepted."""
    app = create_http_app(populated_vault, token="secret123")
    client = TestClient(app)

    # 1. No token -> 401
    r_unauth = client.get("/api/v1/overview")
    assert r_unauth.status_code == 401
    assert "Unauthorized" in r_unauth.json().get("error", "")

    # 2. Invalid token -> 401
    r_bad = client.get("/api/v1/overview", headers={"Authorization": "Bearer wrong"})
    assert r_bad.status_code == 401

    # 3. Valid Bearer token -> 200
    r_bearer = client.get("/api/v1/overview", headers={"Authorization": "Bearer secret123"})
    assert r_bearer.status_code == 200
    assert r_bearer.json()["total_notes"] >= 2

    # 4. Valid X-Orbit-Token -> 200
    r_custom = client.get("/api/v1/overview", headers={"X-Orbit-Token": "secret123"})
    assert r_custom.status_code == 200

    # 5. Valid query param token -> 200
    r_query = client.get("/api/v1/overview?token=secret123")
    assert r_query.status_code == 200


def test_http_context_endpoint(populated_vault: Path) -> None:
    """Verify /api/v1/context returns structured graph metadata."""
    app = create_http_app(populated_vault, token="tok")
    client = TestClient(app)

    # Missing note_path parameter -> 400
    r_missing = client.get("/api/v1/context", headers={"Authorization": "Bearer tok"})
    assert r_missing.status_code == 400

    # Nonexistent note -> 404
    r_404 = client.get(
        "/api/v1/context?note_path=Missing.md", headers={"Authorization": "Bearer tok"}
    )
    assert r_404.status_code == 404

    # Existing note -> 200
    r_ok = client.get("/api/v1/context?note_path=Alpha.md", headers={"Authorization": "Bearer tok"})
    assert r_ok.status_code == 200
    data = r_ok.json()
    assert data["path"] == "Alpha.md"
    assert "Beta" in str(data.get("outgoing_links", []))


def test_http_search_endpoint(populated_vault: Path) -> None:
    """Verify /api/v1/search executes hybrid search queries."""
    app = create_http_app(populated_vault, token="tok")
    client = TestClient(app)

    payload = {"query": "Beta architecture", "mode": "hybrid", "limit": 5}
    resp = client.post("/api/v1/search", json=payload, headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) >= 1


def test_http_reindex_endpoint(populated_vault: Path) -> None:
    """Verify /api/v1/reindex re-indexes updated note."""
    app = create_http_app(populated_vault, token="tok")
    client = TestClient(app)

    resp = client.post(
        "/api/v1/reindex", json={"note_path": "Alpha.md"}, headers={"Authorization": "Bearer tok"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "Alpha.md"
    assert data["status"] in ("indexed", "unchanged")


def test_http_gaps_endpoint(populated_vault: Path) -> None:
    """Verify /api/v1/gaps discovers semantic gap candidates."""
    app = create_http_app(populated_vault, token="tok")
    client = TestClient(app)

    resp = client.get("/api/v1/gaps?threshold=0.10", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data
    assert "total" in data


def test_http_cors_headers(populated_vault: Path) -> None:
    """Verify CORS middleware permits Obsidian app origin."""
    app = create_http_app(populated_vault, token="tok")
    client = TestClient(app)

    headers = {
        "Origin": "app://obsidian.md",
        "Access-Control-Request-Method": "POST",
    }
    resp = client.options("/api/v1/search", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "app://obsidian.md"


def test_run_server_invalid_transport(tmp_path: Path) -> None:
    """Verify run_server raises ValueError for unrecognized transport."""
    with pytest.raises(ValueError, match="Unsupported transport 'ftp'"):
        run_server(tmp_path, transport="ftp")
