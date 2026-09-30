"""Unit tests for the inference provider subsystem."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orbit.inference import (
    InferredRelationshipResult,
    MockInferenceProvider,
    OpenAICompatibleProvider,
)


def test_mock_inference_provider_custom_mapping() -> None:
    """Verify MockInferenceProvider correctly resolves configured relationships."""
    expected = InferredRelationshipResult(
        rel_type="CONTRADICTS",
        confidence=0.92,
        reason="Note A assumes locks are reliable, Note B proves they fail.",
        direction="source_to_target",
    )
    provider = MockInferenceProvider(
        custom_mapping={("Distributed Locks", "Redis Redlock"): expected}
    )

    res = provider.classify_relationship(
        "Distributed Locks",
        "Locks work always.",
        "Redis Redlock",
        "Redlock is unsafe under partitions.",
    )
    assert res.rel_type == "CONTRADICTS"
    assert res.confidence == 0.92
    assert "assumes locks are reliable" in res.reason


def test_mock_inference_provider_default_none() -> None:
    """Verify unmapped note pairs default to NONE without hallucination."""
    provider = MockInferenceProvider()
    res = provider.classify_relationship("Note 1", "Content 1", "Note 2", "Content 2")
    assert res.rel_type == "NONE"


def test_openai_provider_json_parser_clean() -> None:
    """Verify JSON parsing handles clean structured outputs."""
    provider = OpenAICompatibleProvider(api_key="test")
    raw = (
        '{"rel_type": "EXTENDS", "confidence": 0.88, '
        '"reason": "Expands the architecture with new layers.", "direction": "source_to_target"}'
    )
    res = provider._parse_json_result(raw)
    assert res.rel_type == "EXTENDS"
    assert res.confidence == 0.88
    assert res.direction == "source_to_target"


def test_openai_provider_json_parser_markdown_wrapped() -> None:
    """Verify parser extracts JSON embedded within markdown text."""
    provider = OpenAICompatibleProvider(api_key="test")
    raw = (
        "Here is the classification result:\n```json\n"
        '{"rel_type": "PREREQUISITE_FOR", "confidence": 0.95, '
        '"reason": "Math foundations required.", "direction": "source_to_target"}\n```'
    )
    res = provider._parse_json_result(raw)
    assert res.rel_type == "PREREQUISITE_FOR"
    assert res.confidence == 0.95


def test_dotenv_loading(tmp_path: Path, monkeypatch: Any) -> None:
    """Verify load_vault_env reads variables from a .env file."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ORBIT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("ORBIT_LLM_MODEL", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".env").write_text("OPENAI_API_KEY=sk-test-secret-env\nORBIT_LLM_MODEL=custom-llm\n")

    from orbit.config import load_vault_env

    load_vault_env(vault)

    provider = OpenAICompatibleProvider()
    assert provider.api_key == "sk-test-secret-env"
    assert provider.model == "custom-llm"
