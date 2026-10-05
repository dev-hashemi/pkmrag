"""Tests for MCP HTTP/SSE server authentication and token management."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import MagicMock

from starlette.requests import Request

from orbit.mcp.auth import (
    extract_request_token,
    get_or_create_token_file,
    get_token_file_path,
    resolve_server_token,
    validate_token,
)


def test_get_or_create_token_file(tmp_path: Path) -> None:
    """Verify token generation, persistence, and file permissions."""
    token, created = get_or_create_token_file(tmp_path)
    assert created is True
    assert len(token) == 32

    token_file = get_token_file_path(tmp_path)
    assert token_file.is_file()
    assert token_file.read_text(encoding="utf-8").strip() == token

    # Verify restricted file permissions (0o600: read/write only by owner)
    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode == 0o600

    # Second call should load existing token without regenerating
    token2, created2 = get_or_create_token_file(tmp_path)
    assert created2 is False
    assert token2 == token


def test_resolve_server_token_options(tmp_path: Path) -> None:
    """Verify precedence rules when resolving server token."""
    # 1. no_auth should always return empty string
    assert resolve_server_token(tmp_path, no_auth=True) == ""
    assert resolve_server_token(tmp_path, cli_token="my-token", no_auth=True) == ""

    # 2. CLI token override
    assert resolve_server_token(tmp_path, cli_token="explicit-cli-token") == "explicit-cli-token"

    # 3. Default fallback to vault token file
    tok = resolve_server_token(tmp_path)
    assert len(tok) == 32
    assert get_token_file_path(tmp_path).is_file()


def test_extract_request_token() -> None:
    """Verify token extraction from Authorization header, custom header, and query param."""
    # 1. Authorization: Bearer <tok>
    req1 = MagicMock(spec=Request)
    req1.headers = {"authorization": "Bearer secret_bearer_token"}
    req1.query_params = {}
    assert extract_request_token(req1) == "secret_bearer_token"

    # 2. X-Orbit-Token: <tok>
    req2 = MagicMock(spec=Request)
    req2.headers = {"x-orbit-token": "secret_custom_token"}
    req2.query_params = {}
    assert extract_request_token(req2) == "secret_custom_token"

    # 3. ?token=<tok> (browser EventSource fallback)
    req3 = MagicMock(spec=Request)
    req3.headers = {}
    req3.query_params = {"token": "secret_query_token"}
    assert extract_request_token(req3) == "secret_query_token"

    # 4. No token provided
    req4 = MagicMock(spec=Request)
    req4.headers = {}
    req4.query_params = {}
    assert extract_request_token(req4) == ""


def test_validate_token() -> None:
    """Verify constant-time token comparison."""
    assert validate_token("", "") is True  # No auth required when expected is empty
    assert validate_token("anything", "") is True
    assert validate_token("", "expected_token") is False
    assert validate_token("wrong_token", "expected_token") is False
    assert validate_token("expected_token", "expected_token") is True
