"""Tests for the semantic gap scanner: candidate discovery, scoping, and enrichment."""

from __future__ import annotations

from pathlib import Path

from pkmrag.discovery.engine import GapDiscoveryEngine


def test_gap_candidates_carry_note_titles(semantic_gap_vault: Path) -> None:
    """Verify that candidates expose the file stem titles of both notes."""
    engine = GapDiscoveryEngine(semantic_gap_vault)
    try:
        candidates = engine.find_gap_candidates(min_similarity=0.50)
    finally:
        engine.close()

    assert len(candidates) >= 1
    for cand in candidates:
        assert cand.source_title == Path(cand.source_path).stem
        assert cand.target_title == Path(cand.target_path).stem


def test_enrich_candidates_adds_hops_and_bridge_path(semantic_gap_vault: Path) -> None:
    """Verify enrichment reports the real graph distance and the connecting path."""
    engine = GapDiscoveryEngine(semantic_gap_vault)
    try:
        candidates = engine.find_gap_candidates(min_similarity=0.50)
        assert len(candidates) >= 1
        enriched = engine.enrich_candidates(candidates)
    finally:
        engine.close()

    for cand in enriched:
        if cand.hops < 0:
            # No path within the search radius: the bridge list must be empty.
            assert cand.bridge_path == []
            continue
        assert cand.hops >= 1
        assert len(cand.bridge_path) == cand.hops + 1
        assert cand.bridge_path[0] == cand.source_path
        assert cand.bridge_path[-1] == cand.target_path


def test_discover_enrich_flag_populates_graph_distance(semantic_gap_vault: Path) -> None:
    """Verify the discover(enrich=True) path annotates candidates with graph distance."""
    engine = GapDiscoveryEngine(semantic_gap_vault)
    try:
        plain, _, _ = engine.discover(similarity_threshold=0.50, limit=10, dry_run=True)
        enriched, _, _ = engine.discover(
            similarity_threshold=0.50, limit=10, dry_run=True, enrich=True
        )
    finally:
        engine.close()

    assert len(plain) >= 1
    assert len(enriched) == len(plain)
    assert all(c.hops == -1 and c.bridge_path == [] for c in plain)
    assert any(c.hops != -1 or c.bridge_path == [] for c in enriched)


def test_per_note_scan_matches_vault_wide_filtered(semantic_gap_vault: Path) -> None:
    """A note-scoped sweep must return exactly the vault-wide pairs touching that note."""
    engine = GapDiscoveryEngine(semantic_gap_vault)
    try:
        vault_wide = engine.find_gap_candidates(min_similarity=0.50)
        assert len(vault_wide) >= 1

        for cand in vault_wide:
            focused = engine.find_gap_candidates(
                min_similarity=0.50,
                focus_path=cand.source_path,
            )
            focused_pairs = {(c.source_path, c.target_path) for c in focused}
            expected = {
                (c.source_path, c.target_path)
                for c in vault_wide
                if cand.source_path in (c.source_path, c.target_path)
            }
            assert focused_pairs == expected
    finally:
        engine.close()


def test_per_note_scan_is_scoped_to_the_focus_note(semantic_gap_vault: Path) -> None:
    """A note-scoped sweep must never surface pairs between two unrelated notes."""
    engine = GapDiscoveryEngine(semantic_gap_vault)
    try:
        focused = engine.find_gap_candidates(
            min_similarity=0.50,
            focus_path="DistributedLocks.md",
        )
        assert focused
        for cand in focused:
            assert "DistributedLocks.md" in (cand.source_path, cand.target_path)
    finally:
        engine.close()


def test_per_note_scan_uses_canonical_pair_order(semantic_gap_vault: Path) -> None:
    """Pair ordering must stay canonical so dismissal keys match the vault-wide scan."""
    engine = GapDiscoveryEngine(semantic_gap_vault)
    try:
        vault_wide = engine.find_gap_candidates(min_similarity=0.50)
        focused = engine.find_gap_candidates(
            min_similarity=0.50,
            focus_path="RedlockAlgorithm.md",
        )
        wide_keys = {f"{c.source_path}::{c.target_path}" for c in vault_wide}
        focused_keys = {f"{c.source_path}::{c.target_path}" for c in focused}
        assert focused_keys <= wide_keys
        for key in focused_keys:
            src, dst = key.split("::")
            assert src <= dst
    finally:
        engine.close()


def test_per_note_scan_for_unknown_note_is_empty(semantic_gap_vault: Path) -> None:
    """A focus note that is not indexed must yield no candidates."""
    engine = GapDiscoveryEngine(semantic_gap_vault)
    try:
        assert engine.find_gap_candidates(min_similarity=0.50, focus_path="Missing.md") == []
    finally:
        engine.close()
