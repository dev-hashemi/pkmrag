"""Integration tests for targeted single-note and vault delta reindexing."""

from __future__ import annotations

from pathlib import Path

from orbit.graph.paths import get_note_structural_context
from orbit.graph.store import GraphStore
from orbit.ingest.pipeline import IngestPipeline
from orbit.ingest.reindexer import SingleNoteReindexer
from orbit.search.service import SearchService
from orbit.search.vector_store import VectorStore


def test_single_note_reindex_and_graph_population(tmp_path: Path) -> None:
    """Verify reindexing a single note updates LadybugDB graph and LanceDB vector chunks."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Base.md").write_text("# Base\nFoundational note.", encoding="utf-8")

    pipe = IngestPipeline(vault, target="all")
    pipe.run()

    # Create a new note on disk with links and tags
    new_note = vault / "Component.md"
    new_note.write_text(
        "# Component\nConnecting to [[Base]].\nTagged with #architecture and #core.",
        encoding="utf-8",
    )

    reindexer = SingleNoteReindexer(vault)
    result = reindexer.reindex_note("Component.md")

    assert result.status == "indexed"
    assert result.chunks_count >= 1
    assert result.links_count == 1
    assert result.tags_count == 2
    assert result.duration_ms > 0

    # Verify graph state
    with GraphStore(vault / ".orbit" / "graph", read_only=True) as gstore:
        ctx = get_note_structural_context(gstore.conn, "Component.md")
        assert ctx is not None
        assert "Base.md" in ctx.outgoing_links
        assert "architecture" in ctx.tags
        assert "core" in ctx.tags

    # Verify vector state
    with VectorStore(vault / ".orbit" / "vectors") as vstore:
        dense_hits = vstore.search_sparse("architecture", limit=5)
        assert any(h["note_path"] == "Component.md" for h in dense_hits)

    # Subsequent reindex updates cleanly
    warm_res = reindexer.reindex_note("Component.md")
    assert warm_res.status == "indexed"
    assert warm_res.duration_ms > 0

    reindexer.close()


def test_ghost_note_reconciliation_on_reindex(tmp_path: Path) -> None:
    """Verify creating and reindexing a note resolves dangling ghost note links."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Caller.md").write_text("# Caller\nReferences [[TargetAPI]].", encoding="utf-8")

    pipe = IngestPipeline(vault, target="all")
    pipe.run()

    # Verify ghost note exists initially
    with GraphStore(vault / ".orbit" / "graph", read_only=True) as gstore:
        notes = gstore.get_all_notes()
        assert "TargetAPI.md" in notes
        assert notes["TargetAPI.md"]["is_unresolved"] is True

    # Real note is created on disk
    (vault / "TargetAPI.md").write_text("# Target API\nFully implemented API.", encoding="utf-8")

    reindexer = SingleNoteReindexer(vault)
    res = reindexer.reindex_note("TargetAPI.md")
    assert res.status == "indexed"
    assert res.ghosts_reconciled == 1

    # Verify ghost note migrated into real note
    with GraphStore(vault / ".orbit" / "graph", read_only=True) as gstore:
        notes = gstore.get_all_notes()
        assert "TargetAPI.md" in notes
        assert notes["TargetAPI.md"]["is_unresolved"] is False

        caller_ctx = get_note_structural_context(gstore.conn, "Caller.md")
        assert caller_ctx is not None
        assert "TargetAPI.md" in caller_ctx.outgoing_links

    reindexer.close()


def test_single_note_deletion_lifecycle(tmp_path: Path) -> None:
    """Verify deleting a note file and reindexing purges graph edges and vector chunks."""
    vault = tmp_path / "vault"
    vault.mkdir()
    note_file = vault / "Obsolete.md"
    note_file.write_text("# Obsolete\nThis will be deleted.", encoding="utf-8")

    pipe = IngestPipeline(vault, target="all")
    pipe.run()

    # Delete from disk
    note_file.unlink()

    reindexer = SingleNoteReindexer(vault)
    result = reindexer.reindex_note("Obsolete.md")
    assert result.status == "deleted"

    with GraphStore(vault / ".orbit" / "graph", read_only=True) as gstore:
        notes = gstore.get_all_notes()
        assert "Obsolete.md" not in notes

    with VectorStore(vault / ".orbit" / "vectors") as vstore:
        hits = vstore.search_sparse("Obsolete", limit=5)
        assert len(hits) == 0

    reindexer.close()


def test_reindexer_security_boundaries(tmp_path: Path) -> None:
    """Verify reindexer rejects path traversal and protected internal directory paths."""
    vault = tmp_path / "vault"
    vault.mkdir()

    reindexer = SingleNoteReindexer(vault)

    # 1. Path traversal
    r1 = reindexer.reindex_note("../../../outside.md")
    assert r1.status == "error"
    assert "outside vault" in (r1.error_message or "").lower()

    # 2. Protected directory (.orbit)
    r2 = reindexer.reindex_note(".orbit/graph/fake.md")
    assert r2.status == "error"
    assert "protected" in (r2.error_message or "").lower()

    # 3. Empty path
    r3 = reindexer.reindex_note("   ")
    assert r3.status == "error"

    reindexer.close()


def test_sync_vault_delta(tmp_path: Path) -> None:
    """Verify delta scan identifies newly added and modified notes."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note1.md").write_text("# Note 1\nInitial content.", encoding="utf-8")
    (vault / "Note2.md").write_text("# Note 2\nSecond note.", encoding="utf-8")

    pipe = IngestPipeline(vault, target="all")
    pipe.run()

    # Modify Note1, add Note3
    (vault / "Note1.md").write_text("# Note 1\nUpdated modified content.", encoding="utf-8")
    (vault / "Note3.md").write_text("# Note 3\nBrand new note.", encoding="utf-8")

    reindexer = SingleNoteReindexer(vault)
    delta_results = reindexer.sync_vault_delta()

    updated_paths = {r.path for r in delta_results if r.status == "indexed"}
    assert "Note1.md" in updated_paths
    assert "Note3.md" in updated_paths
    assert "Note2.md" not in updated_paths

    reindexer.close()


def test_cache_invalidation_end_to_end(tmp_path: Path) -> None:
    """Verify SearchService cache is invalidated when a note is modified and reindexed."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Guide.md").write_text(
        "# Retrieval Guide\nExplaining how vector caching works in detail.",
        encoding="utf-8",
    )

    pipe = IngestPipeline(vault, target="all")
    pipe.run()

    svc = SearchService(vault)
    r1 = svc.search("vector caching", mode="hybrid")
    assert len(r1) > 0
    assert r1[0].note_path == "Guide.md"

    # Second search should hit L1 cache
    stats1 = svc.get_cache_stats()
    assert stats1.misses == 1

    r2 = svc.search("vector caching", mode="hybrid")
    assert len(r2) > 0
    stats2 = svc.get_cache_stats()
    assert stats2.hits == 1
    assert stats2.misses == 1

    # Now externally update Guide.md
    (vault / "Guide.md").write_text(
        "# Retrieval Guide\nRevised documentation with updated section on invalidation.",
        encoding="utf-8",
    )

    # Reindex Guide.md
    reindexer = SingleNoteReindexer(vault, cache_manager=svc.cache_manager)
    reindex_res = reindexer.reindex_note("Guide.md")
    assert reindex_res.cache_entries_evicted >= 1

    # Search again: should miss cache and retrieve fresh content
    r3 = svc.search("vector caching", mode="hybrid")
    assert len(r3) > 0
    stats3 = svc.get_cache_stats()
    assert stats3.misses == 2

    svc.close()
    reindexer.close()
