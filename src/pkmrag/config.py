"""Configuration settings for PKMRAG."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PkmragSettings(BaseSettings):
    """Global configuration settings for PKMRAG."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Inference
    llm_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("PKMRAG_LLM_PROVIDER", "ORBIT_LLM_PROVIDER", "LLM_PROVIDER"),
    )
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("PKMRAG_LLM_API_KEY", "ORBIT_LLM_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices(
            "PKMRAG_LLM_BASE_URL", "ORBIT_LLM_BASE_URL", "OPENAI_BASE_URL"
        ),
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("PKMRAG_LLM_MODEL", "ORBIT_LLM_MODEL", "LLM_MODEL"),
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        validation_alias=AliasChoices(
            "PKMRAG_OLLAMA_BASE_URL", "ORBIT_OLLAMA_BASE_URL", "OLLAMA_BASE_URL"
        ),
    )
    ollama_model: str = Field(
        default="llama3.2",
        validation_alias=AliasChoices("PKMRAG_OLLAMA_MODEL", "ORBIT_OLLAMA_MODEL", "OLLAMA_MODEL"),
    )
    llm_rpm: int = Field(
        default=30,
        validation_alias=AliasChoices("PKMRAG_LLM_RPM", "ORBIT_LLM_RPM", "LLM_RPM"),
    )
    llm_tpm: int = Field(
        default=8000,
        validation_alias=AliasChoices("PKMRAG_LLM_TPM", "ORBIT_LLM_TPM", "LLM_TPM"),
    )
    llm_max_retries: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "PKMRAG_LLM_MAX_RETRIES", "ORBIT_LLM_MAX_RETRIES", "LLM_MAX_RETRIES"
        ),
    )

    # HTTP & SSE Server
    server_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("PKMRAG_SERVER_HOST", "ORBIT_SERVER_HOST", "SERVER_HOST"),
    )
    server_port: int = Field(
        default=3747,
        validation_alias=AliasChoices("PKMRAG_SERVER_PORT", "ORBIT_SERVER_PORT", "SERVER_PORT"),
    )
    server_token: str = Field(
        default="",
        validation_alias=AliasChoices("PKMRAG_SERVER_TOKEN", "ORBIT_SERVER_TOKEN", "SERVER_TOKEN"),
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "app://obsidian.md",
            "capacitor://localhost",
            "http://localhost",
            "http://127.0.0.1",
        ]
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
        ".pkmrag",
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
    vault_path: Optional[Path] = Field(
        default=None,
        validation_alias=AliasChoices(
            "PKMRAG_VAULT_PATH", "ORBIT_VAULT_PATH", "VAULT_PATH", "OBSIDIAN_VAULT_PATH"
        ),
    )
    db_dir: Optional[Path] = Field(
        default=None, validation_alias=AliasChoices("PKMRAG_DB_DIR", "ORBIT_DB_DIR")
    )
    vector_dir: Optional[Path] = Field(
        default=None, validation_alias=AliasChoices("PKMRAG_VECTOR_DIR", "ORBIT_VECTOR_DIR")
    )
    cache_dir: Optional[Path] = Field(
        default=None, validation_alias=AliasChoices("PKMRAG_CACHE_DIR", "ORBIT_CACHE_DIR")
    )

    @field_validator("vault_path", mode="after")
    @classmethod
    def _expand_vault_path(cls, v: Optional[Path]) -> Optional[Path]:
        if v is not None:
            return v.expanduser().resolve()
        return None

    # Query Cache
    cache_enabled: bool = True
    cache_max_entries: int = 1000
    cache_ttl_seconds: Optional[int] = None

    # Observability & Distributed Tracing
    tracing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("PKMRAG_TRACING", "ORBIT_TRACING", "TRACING_ENABLED"),
    )
    otlp_endpoint: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT")
    )
    otlp_headers: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_HEADERS")
    )
    service_name: str = "pkmrag"

    def get_db_dir(self, vault_path: Path | str) -> Path:
        """Resolve LadybugDB graph storage directory."""
        if self.db_dir:
            return self.db_dir.resolve()
        v = Path(vault_path).resolve()
        legacy = v / ".orbit" / "graph"
        if not (v / ".pkmrag" / "graph").exists() and legacy.exists():
            return legacy.resolve()
        return (v / ".pkmrag" / "graph").resolve()

    def get_vector_dir(self, vault_path: Path | str) -> Path:
        """Resolve LanceDB vector storage directory."""
        if self.vector_dir:
            return self.vector_dir.resolve()
        v = Path(vault_path).resolve()
        legacy = v / ".orbit" / "vectors"
        if not (v / ".pkmrag" / "vectors").exists() and legacy.exists():
            return legacy.resolve()
        return (v / ".pkmrag" / "vectors").resolve()

    def get_cache_db_path(self, vault_path: Path | str) -> Path:
        """Resolve SQLite cache database file path."""
        if self.cache_dir:
            return (self.cache_dir.resolve() / "cache.db").resolve()
        v = Path(vault_path).resolve()
        legacy = v / ".orbit" / "cache.db"
        if not (v / ".pkmrag" / "cache.db").exists() and legacy.exists():
            return legacy.resolve()
        return (v / ".pkmrag" / "cache.db").resolve()


OrbitSettings = PkmragSettings
settings = PkmragSettings()


def load_vault_env(vault_path: Path | str | None = None) -> PkmragSettings:
    """Load configuration from root or vault-level .env files."""
    env_file: Optional[Path] = None
    if vault_path:
        v_path = Path(vault_path).resolve()
        for candidate in (v_path / ".pkmrag" / ".env", v_path / ".orbit" / ".env", v_path / ".env"):
            if candidate.is_file():
                env_file = candidate
                break

    global settings
    settings = PkmragSettings(_env_file=env_file) if env_file else PkmragSettings()  # type: ignore[call-arg]
    return settings
