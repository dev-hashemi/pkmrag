"""Unit and integration tests for inference and discovery telemetry."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from pkmrag.discovery import GapDiscoveryEngine
from pkmrag.inference import OpenAICompatibleProvider
from pkmrag.ingest import IngestPipeline
from pkmrag.telemetry import (
    get_memory_collector,
    setup_telemetry,
    shutdown_telemetry,
)


@pytest.fixture(autouse=True)
def clean_telemetry() -> Generator[None, None, None]:
    """Ensure clean telemetry state for inference tests."""
    shutdown_telemetry()
    yield
    shutdown_telemetry()


def test_http_llm_provider_token_tracking_and_spans() -> None:
    """HttpLLMProvider extracts token usage and records tokens on span attributes."""
    setup_telemetry(enable_memory_collector=True)
    collector = get_memory_collector()
    assert collector is not None

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp_200 = httpx.Response(
        200,
        request=req,
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"rel_type": "EXTENDS", "confidence": 0.85, '
                            '"reason": "Expands functionality.", "direction": "source_to_target"}'
                        )
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 140,
                "completion_tokens": 42,
                "total_tokens": 182,
            },
        },
    )

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = resp_200

    provider = OpenAICompatibleProvider(api_key="test-key")
    with patch("httpx.Client", return_value=mock_client):
        result = provider.classify_relationship("Note A", "Content A", "Note B", "Content B")

    assert result.rel_type == "EXTENDS"
    assert provider.total_prompt_tokens == 140
    assert provider.total_completion_tokens == 42

    spans = collector.get_spans()
    llm_span = next(s for s in spans if s.name == "llm.classify_relationship")
    assert llm_span.attributes["tokens.prompt"] == 140
    assert llm_span.attributes["tokens.completion"] == 42
    assert llm_span.attributes["tokens.total"] == 182
    assert llm_span.attributes["rel_type"] == "EXTENDS"


def test_discovery_engine_telemetry_and_tokens_saved(tmp_path: Path) -> None:
    """GapDiscoveryEngine records discovery spans and calculates tokens saved by graph pruning."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "Doc1.md").write_text("# Doc 1\nDistributed consensus protocols and Raft.\n")
    (vault / "Doc2.md").write_text("# Doc 2\nPaxos and distributed consensus algorithms.\n")
    (vault / "Doc3.md").write_text("# Doc 3\nGardening tips for springtime tomatoes.\n")

    IngestPipeline(vault, target="all").run()

    setup_telemetry(enable_memory_collector=True)
    collector = get_memory_collector()
    assert collector is not None

    engine = GapDiscoveryEngine(vault)
    try:
        candidates, inferred, stats = engine.discover(
            similarity_threshold=0.50, limit=10, dry_run=True
        )
    finally:
        engine.close()

    spans = collector.get_spans()
    span_names = [s.name for s in spans]

    assert "pkmrag.discover" in span_names
    assert "gap.vector_ann" in span_names
    assert "gap.graph_filter" in span_names

    filter_span = next(s for s in spans if s.name == "gap.graph_filter")
    assert "candidates.count" in filter_span.attributes
    assert "pruned_by_graph" in filter_span.attributes

    # Stats model should reflect tokens saved
    assert stats.tokens_saved_by_graph >= 0
