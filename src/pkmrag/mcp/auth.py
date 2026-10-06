"""Authentication token generation, storage, and request validation for HTTP/SSE server."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

from starlette.requests import Request

from pkmrag.config import settings


def get_token_file_path(vault_path: Path) -> Path:
    """Return the filesystem location of the server authentication token file."""
    pkmrag_path = (vault_path.resolve() / ".pkmrag" / "server_token").resolve()
    legacy_path = (vault_path.resolve() / ".orbit" / "server_token").resolve()
    if not pkmrag_path.is_file() and legacy_path.is_file():
        return legacy_path
    return pkmrag_path


def get_or_create_token_file(vault_path: Path) -> tuple[str, bool]:
    """Retrieve existing server token or generate and persist a new one with 0o600 permissions."""
    token_file = get_token_file_path(vault_path)
    if token_file.is_file():
        try:
            content = token_file.read_text(encoding="utf-8").strip()
            if content:
                return content, False
        except OSError:
            pass

    token_file.parent.mkdir(parents=True, exist_ok=True)
    new_token = secrets.token_hex(16)

    # Write securely with restricted permissions (read/write only by owner)
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(new_token)

    return new_token, True


def resolve_server_token(
    vault_path: Path,
    cli_token: Optional[str] = None,
    no_auth: bool = False,
) -> str:
    """Determine the active authentication token from CLI, environment, or vault file."""
    if no_auth:
        return ""
    if cli_token is not None:
        return cli_token.strip()
    if settings.server_token.strip():
        return settings.server_token.strip()

    token, _ = get_or_create_token_file(vault_path)
    return token


def extract_request_token(request: Request) -> str:
    """Extract token from Authorization, X-Pkmrag-Token, X-Orbit-Token, or query param."""
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    custom_header = (
        request.headers.get("x-pkmrag-token")
        or request.headers.get("X-Pkmrag-Token")
        or request.headers.get("x-orbit-token")
        or request.headers.get("X-Orbit-Token")
        or ""
    )
    if custom_header.strip():
        return custom_header.strip()

    # Query param fallback for browser/Electron EventSource
    query_token = request.query_params.get("token", "")
    return query_token.strip()


def validate_token(request_token: str, expected_token: str) -> bool:
    """Validate incoming token against expected token using constant-time comparison."""
    if not expected_token:
        return True
    if not request_token:
        return False
    return secrets.compare_digest(request_token, expected_token)
