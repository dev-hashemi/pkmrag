"""Unit tests for the inference provider subsystem and rate limiter."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from orbit.inference import (
    InferredRelationshipResult,
    MockInferenceProvider,
    OpenAICompatibleProvider,
    RateLimiter,
    estimate_tokens,
    parse_retry_after,
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


def test_strict_json_schema_conforms_to_openai_groq() -> None:
    """Verify strict JSON schema has additionalProperties=false and all required fields."""
    schema = InferredRelationshipResult.strict_json_schema()
    assert schema.get("additionalProperties") is False
    props = schema.get("properties", {})
    required = schema.get("required", [])
    assert isinstance(props, dict)
    assert isinstance(required, list)
    assert set(props.keys()) == set(required)
    assert "rel_type" in props
    assert "confidence" in props
    assert "reason" in props
    assert "direction" in props


def test_rate_limiter_rpm_enforcement() -> None:
    """Verify rate limiter permits RPM allowance and throttles when exhausted."""
    limiter = RateLimiter(rpm=2, tpm=10000)
    waited: list[tuple[float, str]] = []

    # First two calls should succeed immediately
    t0 = time.monotonic()
    limiter.acquire(100, on_wait=lambda d, r: waited.append((d, r)))
    limiter.acquire(100, on_wait=lambda d, r: waited.append((d, r)))
    assert len(waited) == 0

    # Mock older timestamps so we don't have to sleep 60s in tests
    with limiter._lock:
        limiter._requests[0] = t0 - 59.9
        limiter._requests[1] = t0 - 59.8

    # Third call should wait ~0.15s and record the wait
    limiter.acquire(100, on_wait=lambda d, r: waited.append((d, r)))
    assert len(waited) == 1
    assert "RPM limit" in waited[0][1]


def test_rate_limiter_tpm_enforcement() -> None:
    """Verify rate limiter respects TPM token limit."""
    limiter = RateLimiter(rpm=100, tpm=500)
    waited: list[tuple[float, str]] = []

    t0 = time.monotonic()
    limiter.acquire(400, on_wait=lambda d, r: waited.append((d, r)))
    assert len(waited) == 0

    # Mock token timestamp to almost 60s ago
    with limiter._lock:
        limiter._tokens[0] = (t0 - 59.9, 400)

    # Second call of 200 tokens exceeds 500 TPM, triggers wait
    limiter.acquire(200, on_wait=lambda d, r: waited.append((d, r)))
    assert len(waited) == 1
    assert "TPM limit" in waited[0][1]


def test_parse_retry_after_headers_and_body() -> None:
    """Verify parsing retry-after from HTTP headers or body JSON."""
    req = httpx.Request("POST", "https://api.groq.com")

    # Standard Retry-After header
    resp1 = httpx.Response(429, request=req, headers={"Retry-After": "2.5"})
    assert parse_retry_after(resp1) == 2.5

    # Milliseconds header
    resp2 = httpx.Response(429, request=req, headers={"retry-after-ms": "1500"})
    assert parse_retry_after(resp2) == 1.5

    # Groq error body
    resp3 = httpx.Response(
        429,
        request=req,
        json={"error": {"message": "Rate limit exceeded. Please try again in 3.42s."}},
    )
    assert parse_retry_after(resp3) == 3.42


def test_estimate_tokens() -> None:
    """Verify conservative token estimation."""
    text = "A" * 380
    tokens = estimate_tokens(text)
    assert tokens >= 100


def test_openai_provider_handles_429_retry() -> None:
    """Verify OpenAICompatibleProvider retries upon receiving 429."""
    req = httpx.Request("POST", "https://api.groq.com/chat/completions")
    resp_429 = httpx.Response(429, request=req, headers={"Retry-After": "0.01"})
    resp_200 = httpx.Response(
        200,
        request=req,
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"rel_type": "SUPPORTS", "confidence": 0.90, '
                            '"reason": "Verified", "direction": "source_to_target"}'
                        )
                    }
                }
            ]
        },
    )

    limiter = RateLimiter(rpm=30, tpm=30000, max_retries=2)
    provider = OpenAICompatibleProvider(api_key="test", rate_limiter=limiter)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = [resp_429, resp_200]

    with patch("httpx.Client", return_value=mock_client):
        res = provider.classify_relationship("T1", "E1", "T2", "E2")
        assert res.rel_type == "SUPPORTS"
        assert res.confidence == 0.90
        assert mock_client.post.call_count == 2


def test_dotenv_loading(tmp_path: Path, monkeypatch: Any) -> None:
    """Verify load_vault_env reads variables from a .env file."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ORBIT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("ORBIT_LLM_MODEL", raising=False)
    monkeypatch.delenv("ORBIT_LLM_RPM", raising=False)
    monkeypatch.delenv("ORBIT_LLM_TPM", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".env").write_text(
        "OPENAI_API_KEY=sk-test-secret-env\n"
        "ORBIT_LLM_MODEL=custom-llm\n"
        "ORBIT_LLM_RPM=45\n"
        "ORBIT_LLM_TPM=12000\n"
    )

    from orbit.config import load_vault_env

    cfg = load_vault_env(vault)

    provider = OpenAICompatibleProvider()
    assert provider.api_key == "sk-test-secret-env"
    assert provider.model == "custom-llm"
    assert cfg.llm_rpm == 45
    assert cfg.llm_tpm == 12000
    assert provider.rate_limiter.rpm == 45
    assert provider.rate_limiter.tpm == 12000
