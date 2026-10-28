/**
 * Unit tests for matching evidence, hover preview, and deep-link navigation in PKMRAG Insights.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { MarkdownView } from "obsidian";

import {
  attachHoverPreview,
  EXCERPT_LENGTH_THRESHOLD,
  navigateToEvidence,
  renderEvidence,
} from "../src/view_evidence.js";
import { SemanticGapCandidate } from "../src/types.js";
import { createMockEl, MockEl } from "./mock_dom.js";

function createMockPlugin(): any {
  const openLinkCalls: Array<{ linktext: string; sourcePath: string; newLeaf?: any }> = [];
  const triggeredEvents: Array<{ name: string; data: any }> = [];
  const activeLeafCalls: any[] = [];
  const leaves: any[] = [];
  const fileCaches: Record<string, any> = {};

  return {
    calls: { openLinkCalls, triggeredEvents, activeLeafCalls },
    leaves,
    fileCaches,
    app: {
      workspace: {
        openLinkText: async (linktext: string, sourcePath: string, newLeaf?: any) => {
          openLinkCalls.push({ linktext, sourcePath, newLeaf });
        },
        trigger: (name: string, ...data: any[]) => {
          triggeredEvents.push({ name, data });
        },
        getLeavesOfType: (type: string) => (type === "markdown" ? leaves : []),
        setActiveLeaf: (leaf: any, params?: any) => {
          activeLeafCalls.push({ leaf, params });
        },
      },
      metadataCache: {
        getFileCache: (file: any) => fileCaches[file.path] || null,
      },
    },
  };
}

function createSampleGap(overrides: Partial<SemanticGapCandidate> = {}): SemanticGapCandidate {
  return {
    source_path: "Notes/Alpha.md",
    target_path: "Notes/Beta.md",
    source_title: "Alpha Note",
    target_title: "Beta Note",
    similarity: 0.88,
    hops: 2,
    bridge_path: ["Notes/Alpha.md", "Notes/Middle.md", "Notes/Beta.md"],
    source_chunk_id: "chunk-a",
    target_chunk_id: "chunk-b",
    source_chunk_text: "# Alpha Note > ## Core Principle\nThis is a short chunk.",
    target_chunk_text:
      "# Beta Note > ## Applications\n" +
      "This is a long text passage designed to exceed the excerpt length threshold. ".repeat(6),
    chunk_similarity: 0.88,
    matched_chunks: [
      {
        source_chunk_id: "chunk-a",
        target_chunk_id: "chunk-b",
        source_chunk_text: "# Alpha Note > ## Core Principle\nThis is a short chunk.",
        target_chunk_text:
          "# Beta Note > ## Applications\n" +
          "This is a long text passage designed to exceed the excerpt length threshold. ".repeat(6),
        similarity: 0.88,
        source_heading: "Core Principle",
        target_heading: "Applications",
      },
    ],
    ...overrides,
  };
}

test("renderEvidence creates summary header with section match percentage", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap();

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const summary = (card as unknown as MockEl).children[0].children[0];
  assert.equal(summary.className, "pkmrag-evidence-summary");
  assert.match(summary.textContent, /Why are these similar\? \(88% section match\)/);
});

test("renderEvidence marks open note as 'This note' and counter note as 'To'", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap();

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const body = (card as unknown as MockEl).children[0].children[1];
  const pair = body.children[0];
  const rowFrom = pair.children[1]; // First row: Alpha.md (current note)
  const rowTo = pair.children[2]; // Second row: Beta.md (counterpart)

  assert.equal(rowFrom.className, "pkmrag-evidence-row pkmrag-evidence-current");
  assert.equal(rowFrom.children[0].textContent, "This note");

  assert.equal(rowTo.className, "pkmrag-evidence-row");
  assert.equal(rowTo.children[0].textContent, "To");
});

test("clicking note title link calls openLinkText with note path and modifier state", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap();

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const body = (card as unknown as MockEl).children[0].children[1];
  const pair = body.children[0];
  const rowTo = pair.children[2]; // Beta.md
  const noteLink = rowTo.children[1]; // Note anchor link

  assert.equal(noteLink.className, "pkmrag-evidence-note pkmrag-link");
  assert.equal(noteLink.textContent, "Beta Note");

  // Click with Ctrl/Meta (opens in new tab)
  noteLink.onclick?.({ metaKey: true, preventDefault: () => {} } as any);
  assert.equal(plugin.calls.openLinkCalls.length, 1);
  assert.equal(plugin.calls.openLinkCalls[0].linktext, "Notes/Beta.md");
  assert.equal(plugin.calls.openLinkCalls[0].newLeaf, "tab");
});

test("clicking section heading link calls openLinkText with note and #section anchor", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap();

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const body = (card as unknown as MockEl).children[0].children[1];
  const pair = body.children[0];
  const rowTo = pair.children[2]; // Beta.md
  const headingLink = rowTo.children[2]; // Section anchor link

  assert.equal(headingLink.className, "pkmrag-evidence-heading pkmrag-link");
  assert.equal(headingLink.textContent, "# Applications");

  headingLink.onclick?.({ preventDefault: () => {} } as any);
  assert.equal(plugin.calls.openLinkCalls.length, 1);
  assert.equal(plugin.calls.openLinkCalls[0].linktext, "Notes/Beta.md#Applications");
  assert.equal(plugin.calls.openLinkCalls[0].newLeaf, false);
});

test("clicking section heading on current open note scrolls editor directly and sets cursor", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap();

  let scrolledTo: any = null;
  let cursorSetTo: any = null;

  const view = new MarkdownView(null as any);
  view.file = { path: "Notes/Alpha.md", extension: "md" } as any;
  view.editor = {
    getValue: () => "# Alpha Note\nIntro text\n## Core Principle\nBody content here",
    offsetToPos: (off: number) => ({ line: 2, ch: off }),
    scrollIntoView: (range: any, center: boolean) => {
      scrolledTo = { range, center };
    },
    setCursor: (pos: any) => {
      cursorSetTo = pos;
    },
  } as any;
  plugin.leaves.push({ view });

  // Provide metadataCache with the heading line
  plugin.fileCaches["Notes/Alpha.md"] = {
    headings: [
      { heading: "Alpha Note", level: 1, position: { start: { line: 0, col: 0, offset: 0 } } },
      { heading: "Core Principle", level: 2, position: { start: { line: 2, col: 0, offset: 25 } } },
    ],
  };

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const body = (card as unknown as MockEl).children[0].children[1];
  const pair = body.children[0];
  const rowFrom = pair.children[1]; // Alpha.md (current open note)
  const headingLink = rowFrom.children[2]; // "# Core Principle" anchor link

  assert.equal(headingLink.textContent, "# Core Principle");

  headingLink.onclick?.({ preventDefault: () => {} } as any);

  // Verifies leaf focus was requested
  assert.equal(plugin.calls.activeLeafCalls.length, 1);
  assert.equal(plugin.calls.activeLeafCalls[0].params.focus, true);

  // Verifies editor was scrolled directly to heading line 2
  assert.ok(scrolledTo !== null);
  assert.deepEqual(scrolledTo.range, { from: { line: 2, ch: 0 }, to: { line: 2, ch: 0 } });
  assert.equal(scrolledTo.center, true);

  // Verifies cursor was positioned at the heading
  assert.deepEqual(cursorSetTo, { line: 2, ch: 0 });

  // Did not need openLinkText since already open
  assert.equal(plugin.calls.openLinkCalls.length, 0);
});

test("clicking section heading with bold markdown formatting (e.g. **5. Service contains ...) resolves heading line", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap({
    matched_chunks: [
      {
        source_chunk_id: "chunk-a",
        target_chunk_id: "chunk-b",
        source_chunk_text: "# CI CD > ## **5. Service contains ...**\nDocker container services configured here.",
        target_chunk_text: "# Docker > ## container lifecycle\nLifecycle overview.",
        similarity: 0.9,
        source_heading: "**5. Service contains ...**",
        target_heading: "container lifecycle",
      },
    ],
  });

  let scrolledTo: any = null;
  let cursorSetTo: any = null;

  const view = new MarkdownView(null as any);
  view.file = { path: "Notes/Alpha.md", extension: "md" } as any;
  view.editor = {
    getValue: () => "# CI CD\nIntro\n## **5. Service contains a set of tasks**\nDocker container services configured here.",
    offsetToPos: (off: number) => ({ line: 2, ch: off }),
    scrollIntoView: (range: any, center: boolean) => {
      scrolledTo = { range, center };
    },
    setCursor: (pos: any) => {
      cursorSetTo = pos;
    },
  } as any;
  plugin.leaves.push({ view });

  // Notice Obsidian cache stripped the asterisks: "5. Service contains a set of tasks"
  plugin.fileCaches["Notes/Alpha.md"] = {
    headings: [
      { heading: "CI CD", level: 1, position: { start: { line: 0, col: 0, offset: 0 } } },
      { heading: "5. Service contains a set of tasks", level: 2, position: { start: { line: 2, col: 0, offset: 15 } } },
    ],
  };

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const body = (card as unknown as MockEl).children[0].children[1];
  const pair = body.children[0];
  const rowFrom = pair.children[1];
  const headingLink = rowFrom.children[2];

  headingLink.onclick?.({ preventDefault: () => {} } as any);

  assert.equal(plugin.calls.activeLeafCalls.length, 1);
  assert.ok(scrolledTo !== null);
  assert.deepEqual(scrolledTo.range, { from: { line: 2, ch: 0 }, to: { line: 2, ch: 0 } });
  assert.deepEqual(cursorSetTo, { line: 2, ch: 0 });
});

test("hovering over link triggers hover-link workspace event for Page Preview", () => {
  const targetEl = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();

  attachHoverPreview(plugin.app, targetEl, "Notes/Beta.md#Applications", "Notes/Alpha.md");

  (targetEl as unknown as MockEl).dispatchEvent?.("mouseover", { clientX: 10, clientY: 20 });

  assert.equal(plugin.calls.triggeredEvents.length, 1);
  assert.equal(plugin.calls.triggeredEvents[0].name, "hover-link");
  const payload = plugin.calls.triggeredEvents[0].data[0];
  assert.equal(payload.linktext, "Notes/Beta.md#Applications");
  assert.equal(payload.sourcePath, "Notes/Alpha.md");
});

test("short passage renders without expand toggle", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap();

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const body = (card as unknown as MockEl).children[0].children[1];
  const pair = body.children[0];
  const rowFrom = pair.children[1]; // Short passage
  const textContainer = rowFrom.children[3]; // Container for passage

  assert.equal(textContainer.className, "pkmrag-evidence-text");
  // Only the text span, no toggle button
  assert.equal(textContainer.children.length, 1);
  assert.equal(textContainer.children[0].textContent, "This is a short chunk.");
});

test("long passage renders with toggle button that expands and collapses in-place", () => {
  const card = createMockEl() as unknown as HTMLElement;
  const plugin = createMockPlugin();
  const gap = createSampleGap();

  renderEvidence(card, plugin, gap, "Notes/Alpha.md");

  const body = (card as unknown as MockEl).children[0].children[1];
  const pair = body.children[0];
  const rowTo = pair.children[2]; // Long passage
  const textContainer = rowTo.children[3]; // Container for passage

  assert.equal(textContainer.className, "pkmrag-evidence-text");
  assert.equal(textContainer.children.length, 2);

  const textSpan = textContainer.children[0];
  const toggleBtn = textContainer.children[1];

  assert.equal(toggleBtn.className, "pkmrag-evidence-toggle");
  assert.equal(toggleBtn.textContent, "▾ more");
  assert.ok(textSpan.textContent.endsWith("…"));

  // Click toggle to expand
  let stopped = false;
  toggleBtn.onclick?.({ stopPropagation: () => { stopped = true; } } as any);
  assert.equal(stopped, true);
  assert.equal(toggleBtn.textContent, "▴ less");
  assert.ok(!textSpan.textContent.endsWith("…"));
  assert.ok(textSpan.textContent.length > EXCERPT_LENGTH_THRESHOLD);

  // Click toggle again to collapse
  toggleBtn.onclick?.({ stopPropagation: () => {} } as any);
  assert.equal(toggleBtn.textContent, "▾ more");
  assert.ok(textSpan.textContent.endsWith("…"));
});

test("clicking passage in current note scrolls editor directly if open in source mode", async () => {
  const plugin = createMockPlugin();
  let scrolledTo: any = null;

  const view = new MarkdownView(null as any);
  view.file = { path: "Notes/Alpha.md", extension: "md" } as any;
  view.editor = {
    getValue: () => "Leading text.\nThis is a short chunk.\nTrailing text.",
    offsetToPos: (off: number) => ({ line: 1, ch: off }),
    scrollIntoView: (range: any, center: boolean) => {
      scrolledTo = { range, center };
    },
    setCursor: (_pos: any) => {},
  } as any;
  plugin.leaves.push({ view });

  await navigateToEvidence(
    plugin,
    "Notes/Alpha.md",
    "Core Principle",
    "This is a short chunk.",
    "Notes/Alpha.md"
  );

  assert.ok(scrolledTo !== null);
  assert.equal(scrolledTo.center, true);
  // Does not need to open another tab/leaf
  assert.equal(plugin.calls.openLinkCalls.length, 0);
});
