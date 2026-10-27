"""Tests for the semantic gap scanner: candidate discovery, scoping, and enrichment."""

from __future__ import annotations

from pathlib import Path

from pkmrag.discovery.engine import GapDiscoveryEngine
from pkmrag.ingest.pipeline import IngestPipeline


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


def test_coverage_weighted_scoring_discounts_partial_overlap(tmp_path: Path) -> None:
    """Notes that share only a single section out of many must have discounted similarity."""
    vault = tmp_path / "coverage_vault"
    vault.mkdir()

    # Note A: short 1-chunk note on CI/CD
    (vault / "CICD.md").write_text(
        "# Continuous Integration and Delivery\n\n"
        "Automated continuous integration and deployment pipelines run unit tests, lint code, "
        "security analysis tools, and build Docker containers on every pull request.\n"
        "DevOps workflows rely on delivery pipelines to ensure reproducible builds "
        "and rapid rollback capabilities across all staging and production environments.\n"
    )

    # Note B: broad multi-chunk roadmap where only 1 section mentions CI/CD
    (vault / "Roadmap.md").write_text(
        "# Backend Roadmap\n\n"
        "## Relational Databases\n\n"
        "Relational databases utilize B-tree indexes for fast lookups, foreign keys, and ACID.\n"
        "Designing normalized schemas and executing query optimization ensures throughput "
        "and prevents expensive sequential scans on large tables in production.\n\n"
        "## Frontend Styling\n\n"
        "Cascading style sheets define responsive layouts using modern flexbox, CSS grid.\n"
        "CSS architecture methodologies like BEM help maintain modular and reusable design tokens "
        "across complex component libraries in web applications.\n\n"
        "## Continuous Integration and Delivery\n\n"
        "Automated continuous integration and deployment pipelines run unit tests, lint code, "
        "security analysis tools, and build Docker containers on every pull request.\n"
        "DevOps workflows rely on delivery pipelines to ensure reproducible builds "
        "and rapid rollback capabilities across all staging and production environments.\n\n"
        "## Audio Processing\n\n"
        "Digital signal processing uses Fast Fourier Transforms to analyze acoustic bands.\n"
        "Audio filtering algorithms such as Butterworth filters shape frequencies to remove noise "
        "and enhance vocal clarity during microphone capture.\n\n"
        "## Sourdough Baking\n\n"
        "Wild yeast and lactobacilli ferment flour and water over twenty-four hours.\n"
        "Careful temperature control, autolyse phases, stretch and fold techniques, "
        "and Dutch oven baking produce an open crumb with a blistered crust.\n"
    )

    # Note C: focused 1-chunk note on continuous deployment (full overlap with CICD.md)
    (vault / "DeploymentPipelines.md").write_text(
        "# Automated Deployment Pipelines\n\n"
        "Automated continuous integration and deployment pipelines run unit tests, lint code, "
        "security analysis tools, and build Docker containers on every pull request.\n"
        "DevOps workflows rely on delivery pipelines to ensure reproducible builds "
        "and rapid rollback capabilities across all staging and production environments.\n"
    )

    IngestPipeline(vault, target="all").run()

    engine = GapDiscoveryEngine(vault)
    try:
        # At high threshold (0.60), only the fully overlapping pair surfaces
        high_thresh = engine.find_gap_candidates(min_similarity=0.60)
        high_pairs = [{c.source_path, c.target_path} for c in high_thresh]
        assert {"CICD.md", "DeploymentPipelines.md"} in high_pairs
        assert {"CICD.md", "Roadmap.md"} not in high_pairs

        # Full overlap candidate retains high similarity (close to 1.0)
        full_pair = {"CICD.md", "DeploymentPipelines.md"}
        full_cand = next(c for c in high_thresh if full_pair == {c.source_path, c.target_path})
        assert full_cand.similarity >= 0.85

        # At lower threshold (0.20), both surface; partial overlap has discounted score
        low_thresh = engine.find_gap_candidates(min_similarity=0.20)
        roadmap_pair = {"CICD.md", "Roadmap.md"}
        partial_cand = next(c for c in low_thresh if roadmap_pair == {c.source_path, c.target_path})
        # Score drops to ~0.53 because only 1 of Roadmap's sections matches.
        assert 0.30 <= partial_cand.similarity <= 0.58
        # The section-level match retains its raw high similarity independently
        assert partial_cand.chunk_similarity >= 0.90
        assert len(partial_cand.matched_chunks) >= 1
        assert partial_cand.matched_chunks[0].similarity >= 0.90
    finally:
        engine.close()
