"""Integration tests verifying OpenTelemetry tracing in the search pipeline."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from pkmrag.ingest import IngestPipeline
from pkmrag.search import SearchService
from pkmrag.telemetry import (
    get_memory_collector,
    setup_telemetry,
    shutdown_telemetry,
)


@pytest.fixture(autouse=True)
def clean_telemetry() -> Generator[None, None, None]:
    """Ensure clean telemetry state for each search test."""
    shutdown_telemetry()
    yield
    shutdown_telemetry()


def test_search_pipeline_trace_hierarchy(tmp_path: Path) -> None:
    """SearchService produces hierarchical spans with correct attributes and timing."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "LadybugDB.md").write_text(
        "# LadybugDB Engine\n\nLadybugDB is an embedded graph database for traversal.\n"
        "It links to [[LanceDB]].\n",
        encoding="utf-8",
    )
    (vault / "LanceDB.md").write_text(
        "# LanceDB Engine\n\nLanceDB provides fast vector search and BM25 indexing.\n",
        encoding="utf-8",
    )

    IngestPipeline(vault, target="all").run()

    setup_telemetry(enable_memory_collector=True)
    collector = get_memory_collector()
    assert collector is not None

    with SearchService(vault) as service:
        # First query: Cache Miss
        hits = service.search("LadybugDB traversal", mode="hybrid", near="LadybugDB.md", limit=2)
        assert len(hits) >= 1

        spans = collector.get_spans()
        span_names = [s.name for s in spans]

        # Verify all expected phase spans are captured
        assert "pkmrag.search" in span_names
        assert "cache.lookup" in span_names
        assert "embed.query" in span_names
        assert "lancedb.dense_search" in span_names
        assert "lancedb.sparse_search" in span_names
        assert "rrf.fuse" in span_names
        assert "ladybug.proximity_boost" in span_names
        assert "cache.store" in span_names

        root = next(s for s in spans if s.name == "pkmrag.search")
        assert root.attributes["query"] == "LadybugDB traversal"
        assert root.attributes["mode"] == "hybrid"
        assert root.attributes["near"] == "LadybugDB.md"

        cache_lookup = next(s for s in spans if s.name == "cache.lookup")
        assert cache_lookup.attributes["cache.hit"] is False
        assert cache_lookup.parent_span_id == root.span_id

        embed_span = next(s for s in spans if s.name == "embed.query")
        assert embed_span.attributes.get("query.dim") == 384
        assert embed_span.parent_span_id == root.span_id

        collector.clear()

        # Second query: Cache Hit
        cached_hits = service.search(
            "LadybugDB traversal", mode="hybrid", near="LadybugDB.md", limit=2
        )
        assert len(cached_hits) == len(hits)

        spans_cached = collector.get_spans()
        cached_names = [s.name for s in spans_cached]

        assert "pkmrag.search" in cached_names
        assert "cache.lookup" in cached_names
        # Dense search, BM25, and RRF should be skipped on cache hit
        assert "lancedb.dense_search" not in cached_names
        assert "rrf.fuse" not in cached_names

        cached_lookup = next(s for s in spans_cached if s.name == "cache.lookup")
        assert cached_lookup.attributes["cache.hit"] is True
