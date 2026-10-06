"""Integration tests for hybrid search and CLI search commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pkmrag.cli import app
from pkmrag.ingest import IngestPipeline
from pkmrag.search import SearchService

runner = CliRunner()


def test_search_service_and_incremental_indexing(tmp_path: Path) -> None:
    """Verify hybrid search service and incremental vector indexing."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "LadybugDB.md").write_text(
        "# LadybugDB Engine\n\n"
        "LadybugDB is an embedded graph database built for fast traversal.\n"
        "It links to [[LanceDB]].\n"
    )
    (vault / "LanceDB.md").write_text(
        "# LanceDB Engine\n\n"
        "LanceDB is a serverless vector database providing fast vector search and BM25.\n"
    )

    (vault / "Unrelated.md").write_text(
        "# Cooking Recipes\n\nHow to bake delicious sourdough bread from scratch.\n"
    )

    # 1. Ingest all (graph + vector)
    pipeline = IngestPipeline(vault, target="all")
    stats = pipeline.run()
    assert stats.chunks_created >= 3
    assert stats.total_chunks >= 3
    assert stats.total_notes == 3

    # 2. Incremental run: no changes should mean 0 new chunks
    pipeline2 = IngestPipeline(vault, target="all")
    stats2 = pipeline2.run()
    assert stats2.chunks_created == 0
    assert stats2.notes_unchanged == 3

    # 3. SearchService query
    with SearchService(vault) as service:
        # Hybrid search
        hits = service.search("vector database search", mode="hybrid", limit=3)
        assert len(hits) >= 1
        assert hits[0].note_path == "LanceDB.md"

        # Sparse keyword search
        sparse_hits = service.search("LadybugDB", mode="sparse", limit=2)
        assert len(sparse_hits) >= 1
        assert any(h.note_path == "LadybugDB.md" for h in sparse_hits)

        # Proximity boosted search near LadybugDB
        # LanceDB links from LadybugDB (1 hop away)
        boosted_hits = service.search("database engine", near="LadybugDB", mode="hybrid", limit=3)
        assert len(boosted_hits) >= 1
        top_hit = boosted_hits[0]
        assert top_hit.graph_boost_factor >= 1.0

        # Folder filter (should match none because files are in root)
        folder_hits = service.search("database", folder="Guides", mode="hybrid")
        assert len(folder_hits) == 0

        # Root folder filter matches
        root_hits = service.search("database", folder="", mode="hybrid")
        assert len(root_hits) >= 1


def test_cli_search_command(tmp_path: Path) -> None:
    """Verify CLI orbit search command with human and JSON output."""
    vault = tmp_path / "cli_vault"
    vault.mkdir()

    (vault / "Arch.md").write_text(
        "# Architecture\n\nOrbit uses a 3-tier architecture with graph, vector, and LLM tiers.\n"
    )

    # Ingest first
    res_ingest = runner.invoke(app, ["ingest", str(vault), "--target", "all"])
    assert res_ingest.exit_code == 0

    # Search human-readable
    res_search = runner.invoke(app, ["search", "architecture", "--vault", str(vault)])
    assert res_search.exit_code == 0
    assert "Search Results for" in res_search.stdout
    assert "Arch.md" in res_search.stdout

    # Search JSON
    res_json = runner.invoke(app, ["search", "architecture", "--vault", str(vault), "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.stdout)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["note_path"] == "Arch.md"
    assert "score" in data[0]


def test_cli_ingest_targets(tmp_path: Path) -> None:
    """Verify orbit ingest supports --target graph and --target vector."""
    vault = tmp_path / "target_vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Target Note\nTesting specific target flags.")

    # Ingest vector only
    res_vec = runner.invoke(app, ["ingest", str(vault), "--target", "vector", "--json"])
    assert res_vec.exit_code == 0
    data_vec = json.loads(res_vec.stdout)
    assert data_vec["target"] == "vector"
    assert data_vec["chunks_created"] >= 1

    # Ingest graph only
    res_graph = runner.invoke(app, ["ingest", str(vault), "--target", "graph", "--json"])
    assert res_graph.exit_code == 0
    data_graph = json.loads(res_graph.stdout)
    assert data_graph["target"] == "graph"
    assert data_graph["total_notes"] >= 1
