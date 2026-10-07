"""Tests for vault runtime configuration and provider factory."""

from __future__ import annotations

from pathlib import Path

from pkmrag.inference.factory import resolve_provider
from pkmrag.inference.mock import MockInferenceProvider
from pkmrag.vault_config import (
    VaultRuntimeConfig,
    get_vault_config_path,
    load_vault_config,
    save_vault_config,
)


def test_vault_config_defaults(tmp_path: Path) -> None:
    """Verify default config falls back to global settings."""
    cfg = load_vault_config(tmp_path)
    assert cfg.llm_provider in ("openai", "ollama")
    assert cfg.llm_rpm >= 1


def test_vault_config_save_and_load(tmp_path: Path) -> None:
    """Verify custom vault config is serialized and deserialized accurately."""
    custom = VaultRuntimeConfig(
        llm_provider="custom",
        llm_base_url="https://api.example.com/v1",
        llm_model="custom-reasoner-7b",
        llm_api_key="secret-key-123",
        llm_rpm=45,
        llm_tpm=12000,
        similarity_threshold=0.88,
    )
    save_vault_config(tmp_path, custom)

    path = get_vault_config_path(tmp_path)
    assert path.is_file()

    loaded = load_vault_config(tmp_path)
    assert loaded.llm_provider == "custom"
    assert loaded.llm_base_url == "https://api.example.com/v1"
    assert loaded.llm_model == "custom-reasoner-7b"
    assert loaded.llm_api_key == "secret-key-123"
    assert loaded.llm_rpm == 45
    assert loaded.similarity_threshold == 0.88


def test_resolve_provider_uses_vault_config(tmp_path: Path) -> None:
    """Verify resolve_provider reads vault-level config."""
    custom = VaultRuntimeConfig(
        llm_provider="custom",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_model="llama-3.3-70b",
        llm_api_key="gsk-xyz",
    )
    save_vault_config(tmp_path, custom)

    provider = resolve_provider(vault_path=tmp_path)
    assert provider.model == "llama-3.3-70b"


def test_mock_inference_test_connection() -> None:
    """Verify test_connection returns success and latency on MockInferenceProvider."""
    mock = MockInferenceProvider()
    ok, msg, latency = mock.test_connection()
    assert ok is True
    assert "Mock provider" in msg
    assert latency > 0
