"""Tests for Ollama local inference provider."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from orbit.inference.ollama import OllamaProvider


def test_ollama_provider_defaults() -> None:
    """Verify default configuration for local Ollama provider."""
    provider = OllamaProvider()
    assert provider.name == "ollama (llama3.2)"
    assert provider.model == "llama3.2"
    assert provider.base_url == "http://localhost:11434/v1"
    assert provider.api_key == "ollama"
    assert provider.is_local is True


def test_ollama_provider_custom_url_normalization() -> None:
    """Verify Ollama URL auto-appends /v1 when omitted."""
    p1 = OllamaProvider(base_url="http://127.0.0.1:11434", model="qwen2.5:3b")
    assert p1.base_url == "http://127.0.0.1:11434/v1"
    assert p1.model == "qwen2.5:3b"

    p2 = OllamaProvider(base_url="http://localhost:11434/v1")
    assert p2.base_url == "http://localhost:11434/v1"


def test_ollama_rate_limit_bypass() -> None:
    """Verify local models bypass token-bucket rate limiting."""
    provider = OllamaProvider(is_local=True)
    with patch.object(provider.rate_limiter, "acquire") as mock_acquire:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "rel_type": "EXTENDS",
                                "confidence": 0.88,
                                "reason": "Local test inference",
                                "direction": "source_to_target",
                            }
                        )
                    }
                }
            ]
        }
        with patch("httpx.Client.post", return_value=mock_response):
            result = provider.classify_relationship(
                source_title="Note A",
                source_excerpt="Content A",
                target_title="Note B",
                target_excerpt="Content B",
            )
            assert result.rel_type == "EXTENDS"
            assert result.confidence == 0.88
            assert result.reason == "Local test inference"
            mock_acquire.assert_not_called()
