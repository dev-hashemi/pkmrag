"""Configuration settings and defaults for Project Orbit."""

from __future__ import annotations

import os
from pathlib import Path

# Default directories and file patterns to ignore during vault traversal
DEFAULT_IGNORED_DIRS: set[str] = {
    ".obsidian",
    ".git",
    ".orbit",
    ".trash",
    ".trash-bin",
    ".vscode",
    ".idea",
    "node_modules",
    ".venv",
    "__pycache__",
}

DEFAULT_IGNORED_FILES: set[str] = {
    ".DS_Store",
    "desktop.ini",
    "thumbs.db",
}


DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIM: int = 384


def get_default_db_dir(vault_path: Path | str) -> Path:
    """Resolve the default LadybugDB graph storage directory.

    Checks the `ORBIT_DB_DIR` environment variable first, falling back to `<vault>/.orbit/graph`.
    """
    env_dir = os.environ.get("ORBIT_DB_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    return (Path(vault_path).resolve() / ".orbit" / "graph").resolve()


def get_default_vector_dir(vault_path: Path | str) -> Path:
    """Resolve the default LanceDB vector storage directory.

    Checks `ORBIT_VECTOR_DIR` env variable first, falling back to `<vault>/.orbit/vectors`.
    """

    env_dir = os.environ.get("ORBIT_VECTOR_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    return (Path(vault_path).resolve() / ".orbit" / "vectors").resolve()
