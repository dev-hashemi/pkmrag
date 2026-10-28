/**
 * Unit tests for pure PKMRAG Insights presentation helpers.
 */

import test from "node:test";
import assert from "node:assert/strict";
import {
  buildWikilink,
  classifyRequestError,
  displayTitle,
  excerpt,
  formatBridgePath,
  formatGapDistance,
  formatGraphBoost,
  formatRelativeTime,
  gapCounterpart,
  isDismissedPair,
  normalizeHeading,
  noteStem,
  pairKey,
  searchAnchor,
  splitChunkHeading,
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
    chunk_similarity: 0.64,
    matched_chunks: [],
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

test("pairKey is order independent", () => {
  assert.equal(pairKey("b.md", "a.md"), pairKey("a.md", "b.md"));
  assert.equal(pairKey("a.md", "b.md"), "a.md::b.md");
});

test("isDismissedPair matches regardless of edge direction", () => {
  const dismissed = { "a.md::b.md": { sourcePath: "a.md", targetPath: "b.md" } };

  // The LLM may store the inferred edge in either direction.
  assert.equal(isDismissedPair(dismissed, "a.md", "b.md"), true);
  assert.equal(isDismissedPair(dismissed, "b.md", "a.md"), true);
  assert.equal(isDismissedPair(dismissed, "a.md", "c.md"), false);
  assert.equal(isDismissedPair({}, "a.md", "b.md"), false);
});

test("splitChunkHeading separates the breadcrumb from the body", () => {
  const chunk = "# Daily Notes — 2026-09-27 > ## Log\n\nToday we validated the pipeline.";
  const { heading, body } = splitChunkHeading(chunk);
  assert.equal(heading, "# Daily Notes — 2026-09-27 > ## Log");
  assert.equal(body, "Today we validated the pipeline.");
  assert.equal(searchAnchor(heading), "Log");
});

test("splitChunkHeading tolerates chunks without a heading", () => {
  const { heading, body } = splitChunkHeading("  plain body text");
  assert.equal(heading, "");
  assert.equal(body, "plain body text");
});

test("classifyRequestError separates an unindexed vault from an unreachable daemon", () => {
  assert.equal(classifyRequestError("VAULT_UNINDEXED"), "unindexed");
  assert.equal(classifyRequestError("Context fetch failed with HTTP 500"), "offline");
  assert.equal(classifyRequestError("Failed to fetch"), "offline");
});

test("normalizeHeading strips markdown formatting, leading hashes, and normalizes spacing", () => {
  assert.equal(normalizeHeading("## **5. Service contains ...**"), "5. service contains ...");
  assert.equal(normalizeHeading("# **5. Service contains ..."), "5. service contains ...");
  assert.equal(normalizeHeading("5. Service contains ..."), "5. service contains ...");
  assert.equal(normalizeHeading("### [[Section Name|Alias]]"), "alias");
  assert.equal(normalizeHeading("### [Link Text](https://example.com)"), "link text");
  assert.equal(normalizeHeading(""), "");
});

test("formatRelativeTime formats relative timestamps accurately", () => {
  assert.equal(formatRelativeTime(""), "");
  assert.equal(formatRelativeTime("invalid-date"), "");

  const now = Date.now();
  assert.equal(formatRelativeTime(new Date(now - 10 * 1000).toISOString()), "just now");
  assert.equal(formatRelativeTime(new Date(now - 5 * 60 * 1000).toISOString()), "5m ago");
  assert.equal(formatRelativeTime(new Date(now - 3 * 3600 * 1000).toISOString()), "3h ago");
  assert.equal(formatRelativeTime(new Date(now - 24 * 3600 * 1000).toISOString()), "yesterday");
  assert.equal(formatRelativeTime(new Date(now - 3 * 24 * 3600 * 1000).toISOString()), "3d ago");
});
