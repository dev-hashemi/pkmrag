"""Vault-level runtime configuration and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from pkmrag.config import settings


class VaultRuntimeConfig(BaseModel):
    """Runtime configuration overrides stored in <vault>/.pkmrag/config.json."""

    model_config = ConfigDict(extra="ignore")

    llm_provider: str = Field(
        default="openai",
        description="Inference provider: 'openai', 'ollama', or 'custom'.",
    )
    llm_base_url: str = Field(
        default="",
        description="Base URL for LLM provider API.",
    )
    llm_model: str = Field(
        default="",
        description="Model identifier string.",
    )
    llm_api_key: str = Field(
        default="",
        description="API key for authentication (optional for local models).",
    )
    llm_rpm: int = Field(
        default=30,
        ge=1,
        le=1000,
        description="Maximum requests per minute rate limit.",
    )
    llm_tpm: int = Field(
        default=8000,
        ge=100,
        le=500000,
        description="Maximum tokens per minute rate limit.",
    )
    similarity_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Custom cosine similarity threshold for gap discovery.",
    )
    graph_distance_threshold: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Minimum graph hop distance threshold for gap discovery.",
    )
    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="FastEmbed model identifier for vector embeddings.",
    )
    embedding_dim: int = Field(
        default=384,
        ge=64,
        le=4096,
        description="Vector embedding dimensions.",
    )


def get_vault_config_path(vault_path: Path) -> Path:
    """Return the filesystem path for <vault>/.pkmrag/config.json."""
    return vault_path / ".pkmrag" / "config.json"


def load_vault_config(vault_path: Path) -> VaultRuntimeConfig:
    """Load runtime config from vault, falling back to global settings defaults."""
    cfg_file = get_vault_config_path(vault_path)
    if cfg_file.is_file():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return VaultRuntimeConfig.model_validate(data)
        except Exception:
            pass

    # Populate defaults from global settings
    provider = settings.llm_provider
    if provider == "ollama":
        base_url = settings.ollama_base_url
        model = settings.ollama_model
        api_key = ""
    else:
        base_url = settings.openai_base_url
        model = settings.llm_model
        api_key = settings.openai_api_key

    return VaultRuntimeConfig(
        llm_provider=provider,
        llm_base_url=base_url,
        llm_model=model,
        llm_api_key=api_key,
        llm_rpm=settings.llm_rpm,
        llm_tpm=settings.llm_tpm,
        similarity_threshold=settings.similarity_threshold,
        graph_distance_threshold=settings.graph_distance_threshold,
        embedding_model=settings.embedding_model,
        embedding_dim=settings.embedding_dim,
    )


def save_vault_config(vault_path: Path, config: VaultRuntimeConfig) -> None:
    """Persist runtime config into <vault>/.pkmrag/config.json securely."""
    cfg_file = get_vault_config_path(vault_path)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    try:
        cfg_file.chmod(0o600)
    except OSError:
        pass
