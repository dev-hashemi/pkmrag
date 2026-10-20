/**
 * Unit tests for pure PKMRAG Insights presentation helpers.
 */

import test from "node:test";
import assert from "node:assert/strict";
import {
  buildWikilink,
  displayTitle,
  excerpt,
  formatBridgePath,
  formatGapDistance,
  formatGraphBoost,
  gapCounterpart,
  noteStem,
  searchAnchor,
  searchLinkTitle,
} from "../src/format.js";
import type { SearchResult, SemanticGapCandidate } from "../src/types.js";

function makeCandidate(overrides: Partial<SemanticGapCandidate> = {}): SemanticGapCandidate {
  return {
    source_path: "Daily/2026-09-27.md",
    target_path: "Research/Vector Retrieval.md",
    source_title: "2026-09-27",
    target_title: "Vector Retrieval",
    similarity: 0.64,
    hops: 3,
    bridge_path: [],
    source_chunk_id: "Daily/2026-09-27.md#chunk_0",
    target_chunk_id: "Research/Vector Retrieval.md#chunk_0",
    source_chunk_text: "daily body",
    target_chunk_text: "vector body",
    ...overrides,
  };
}

function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    chunk_id: "Research/Vector Retrieval.md#chunk_0",
    note_path: "Research/Vector Retrieval.md",
    note_title: "Vector Retrieval",
    heading: "# Dense Vector Retrieval > ## Integration in PKMRAG",
    text: "Dense vector representations capture latent semantic similarities.",
    score: 0.04,
    dense_score: 0.45,
    sparse_score: 2.5,
    graph_boost_factor: 1.25,
    hop_distance: 1,
    ...overrides,
  };
}

test("noteStem strips extension and folder segments", () => {
  assert.equal(noteStem("Research/Vector Retrieval.md"), "Vector Retrieval");
  assert.equal(noteStem("Index.md"), "Index");
  assert.equal(noteStem("notes/a/b/deep.md"), "deep");
});

test("displayTitle prefers explicit title but rejects path-like titles", () => {
  assert.equal(displayTitle("Research/Vector Retrieval.md", "Vector Retrieval"), "Vector Retrieval");
  assert.equal(displayTitle("Research/Vector Retrieval.md", ""), "Vector Retrieval");
  assert.equal(displayTitle("Research/Vector Retrieval.md", null), "Vector Retrieval");
  // Legacy dismissed entries stored a path as the title.
  assert.equal(displayTitle("Research/Vector Retrieval.md", "Research/Vector Retrieval"), "Vector Retrieval");
});

test("formatGapDistance renders honest distance labels", () => {
  assert.equal(formatGapDistance(-1), "No path within 10 hops");
  assert.equal(formatGapDistance(0), "Same note");
  assert.equal(formatGapDistance(1), "1 hop away");
  assert.equal(formatGapDistance(3), "3 hops away");
});

test("gapCounterpart resolves the side that is not the open note", () => {
  const cand = makeCandidate();

  const whenSourceIsOpen = gapCounterpart(cand, "Daily/2026-09-27.md");
  assert.equal(whenSourceIsOpen.path, "Research/Vector Retrieval.md");
  assert.equal(whenSourceIsOpen.title, "Vector Retrieval");
  assert.equal(whenSourceIsOpen.isCurrent, true);

  const whenTargetIsOpen = gapCounterpart(cand, "Research/Vector Retrieval.md");
  assert.equal(whenTargetIsOpen.path, "Daily/2026-09-27.md");
  assert.equal(whenTargetIsOpen.title, "2026-09-27");
  assert.equal(whenTargetIsOpen.isCurrent, false);
});

test("formatBridgePath renders the chain with file stems", () => {
  assert.equal(
    formatBridgePath(["Daily/2026-09-27.md", "Projects/PKMRAG Core.md", "Research/Vector Retrieval.md"]),
    "2026-09-27 → PKMRAG Core → Vector Retrieval"
  );
  assert.equal(formatBridgePath([]), "");
});

test("searchAnchor extracts the leaf heading from a breadcrumb", () => {
  assert.equal(searchAnchor("# Dense Vector Retrieval > ## Integration in PKMRAG"), "Integration in PKMRAG");
  assert.equal(searchAnchor("## Only Section"), "Only Section");
  assert.equal(searchAnchor(""), "");
});

test("buildWikilink produces resolvable Obsidian links", () => {
  assert.equal(buildWikilink("Vector Retrieval"), "[[Vector Retrieval]]");
  assert.equal(buildWikilink("Vector Retrieval", "Core Formula"), "[[Vector Retrieval#Core Formula]]");
  assert.equal(buildWikilink("  "), "");
});

test("searchLinkTitle uses the note title when present", () => {
  assert.equal(searchLinkTitle(makeResult()), "Vector Retrieval");
  assert.equal(searchLinkTitle(makeResult({ note_title: "" })), "Vector Retrieval");
});

test("excerpt collapses whitespace and clips long text", () => {
  assert.equal(excerpt("a\n\n  b   c", 100), "a b c");
  assert.equal(excerpt("abcdefghij", 5), "abcde…");
  assert.equal(excerpt("abc", 5), "abc");
});

test("formatGraphBoost only reports an actual boost", () => {
  assert.equal(formatGraphBoost(makeResult()), "⚡ ×1.25 · 1 hop");
  assert.equal(formatGraphBoost(makeResult({ graph_boost_factor: 1.0 })), "");
  assert.equal(formatGraphBoost(makeResult({ hop_distance: null })), "⚡ ×1.25");
});
