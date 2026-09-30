"""Configuration settings for Project Orbit."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrbitSettings(BaseSettings):
    """Global configuration settings for Project Orbit."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Inference
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ORBIT_LLM_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("ORBIT_LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("ORBIT_LLM_MODEL", "LLM_MODEL"),
    )

    # Search & Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    similarity_threshold: float = 0.80
    graph_distance_threshold: int = 2

    # Traversal Defaults
    ignored_dirs: set[str] = {
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
        "logseq",
    }
    ignored_files: set[str] = {
        ".DS_Store",
        "desktop.ini",
        "thumbs.db",
    }
    supported_extensions: tuple[str, ...] = (".md", ".markdown", ".mdx")

    # Storage Directory Overrides
    db_dir: Optional[Path] = Field(default=None, validation_alias=AliasChoices("ORBIT_DB_DIR"))
    vector_dir: Optional[Path] = Field(
        default=None, validation_alias=AliasChoices("ORBIT_VECTOR_DIR")
    )

    def get_db_dir(self, vault_path: Path | str) -> Path:
        """Resolve LadybugDB graph storage directory."""
        if self.db_dir:
            return self.db_dir.resolve()
        return (Path(vault_path).resolve() / ".orbit" / "graph").resolve()

    def get_vector_dir(self, vault_path: Path | str) -> Path:
        """Resolve LanceDB vector storage directory."""
        if self.vector_dir:
            return self.vector_dir.resolve()
        return (Path(vault_path).resolve() / ".orbit" / "vectors").resolve()


settings = OrbitSettings()


def load_vault_env(vault_path: Path | str | None = None) -> OrbitSettings:
    """Load configuration from root or vault-level .env files."""
    env_file: Optional[Path] = None
    if vault_path:
        v_path = Path(vault_path).resolve()
        for candidate in (v_path / ".orbit" / ".env", v_path / ".env"):
            if candidate.is_file():
                env_file = candidate
                break

    global settings
    settings = OrbitSettings(_env_file=env_file) if env_file else OrbitSettings()  # type: ignore[call-arg]
    return settings
