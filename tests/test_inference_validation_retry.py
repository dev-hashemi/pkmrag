"""Tests for LLM conversational validation feedback retries."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from pkmrag.inference.provider import OpenAICompatibleProvider


def test_validation_retry_recovers_on_second_attempt() -> None:
    """Verify that a validation failure triggers a conversational correction and succeeds."""
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        is_local=True,
        max_retries=3,
    )

    # First attempt: invalid rel_type ('INVALID_REL')
    resp_invalid = MagicMock()
    resp_invalid.status_code = 200
    resp_invalid.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rel_type": "INVALID_REL",
                            "confidence": 0.9,
                            "reason": "Invalid relation",
                            "direction": "source_to_target",
                        }
                    )
                }
            }
        ]
    }

    # Second attempt: valid rel_type ('SUPPORTS')
    resp_valid = MagicMock()
    resp_valid.status_code = 200
    resp_valid.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rel_type": "SUPPORTS",
                            "confidence": 0.85,
                            "reason": "Corrected on second attempt",
                            "direction": "source_to_target",
                        }
                    )
                }
            }
        ]
    }

    with patch("httpx.Client.post", side_effect=[resp_invalid, resp_valid]) as mock_post:
        result = provider.classify_relationship(
            source_title="A",
            source_excerpt="Content A",
            target_title="B",
            target_excerpt="Content B",
        )

        assert result.rel_type == "SUPPORTS"
        assert result.confidence == 0.85
        assert result.reason == "Corrected on second attempt"
        assert mock_post.call_count == 2

        # Verify second call included validation feedback in messages
        second_call_payload = mock_post.call_args_list[1][1]["json"]
        messages = second_call_payload["messages"]
        assert len(messages) == 4  # system + user + assistant (bad) + user (feedback)
        assert "INVALID_REL" in messages[2]["content"]
        assert "failed validation" in messages[3]["content"].lower()


def test_validation_retry_exhausted_returns_none() -> None:
    """Verify that exhausted retries gracefully default to RelationshipType.NONE."""
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        is_local=True,
        max_retries=2,
    )

    resp_bad = MagicMock()
    resp_bad.status_code = 200
    resp_bad.json.return_value = {
        "choices": [{"message": {"content": "This is completely invalid json {"}}]
    }

    with patch("httpx.Client.post", return_value=resp_bad) as mock_post:
        result = provider.classify_relationship(
            source_title="A",
            source_excerpt="Content A",
            target_title="B",
            target_excerpt="Content B",
        )

        assert result.rel_type == "NONE"
        assert result.confidence == 0.0
        assert "validation failed" in result.reason.lower()
        # 1 initial attempt + 2 retries = 3 attempts total
        assert mock_post.call_count == 3
