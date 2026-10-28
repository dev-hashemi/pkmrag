/**
 * Unit tests for inferred relationships rendering, timestamps, and estimate modal.
 */

import test from "node:test";
import assert from "node:assert/strict";

import { collectText, createMockEl, findByClass } from "./mock_dom.js";
import { renderInferencesSection } from "../src/view_inferences.js";
import { DiscoveryEstimateModal } from "../src/modal_estimate.js";
import { DEFAULT_SETTINGS, NoteContext } from "../src/types.js";

function makeMockPlugin(overrides: Record<string, unknown> = {}): any {
  return {
    app: {},
    settings: { ...DEFAULT_SETTINGS },
    activeJob: null,
    client: {
      estimateDiscover: async () => ({
        candidate_count: 2,
        evaluated_count: 2,
        estimated_prompt_tokens: 1500,
        estimated_completion_tokens: 240,
        total_tokens: 1740,
        provider: "openai",
        model: "gpt-4o-mini",
        candidate_pairs: [],
      }),
      triggerDiscover: async () => ({ status: "started", message: "ok" }),
    },
    ...overrides,
  };
}

test("renderInferencesSection renders empty state with actionable button when no inferences exist", () => {
  const container = createMockEl();
  const plugin = makeMockPlugin();
  const context: NoteContext = {
    path: "Concepts/Quantum.md",
    title: "Quantum",
    tags: [],
    outgoing_links: [],
    backlinks: [],
    neighbors_2hop: [],
    inferred_relationships: [],
  };

  renderInferencesSection(container as any, plugin, context, () => {});

  const sub = findByClass(container, "pkmrag-timestamp");
  assert.ok(sub);
  assert.equal(sub.textContent, "Not analyzed yet");

  const btn = findByClass(container, "pkmrag-empty-state-actionable");
  assert.ok(btn);
  const text = collectText(btn);
  assert.ok(text.includes("Discover for this note"));
});

test("renderInferencesSection displays last discovered relative timestamp and cards", () => {
  const container = createMockEl();
  const plugin = makeMockPlugin();
  const past = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
  const context: NoteContext = {
    path: "Concepts/Quantum.md",
    title: "Quantum",
    tags: [],
    outgoing_links: [],
    backlinks: [],
    neighbors_2hop: [],
    last_discovered_at: past,
    inferred_relationships: [
      {
        source_path: "Concepts/Quantum.md",
        target_path: "Concepts/Qubits.md",
        rel_type: "EXTENDS",
        confidence: 0.92,
        reason: "Quantum explains physical foundation of qubits",
        model: "gpt-4o-mini",
        created_at: past,
      },
    ],
  };

  renderInferencesSection(container as any, plugin, context, () => {});

  const timestamp = findByClass(container, "pkmrag-timestamp");
  assert.ok(timestamp);
  assert.ok(timestamp.textContent.includes("Last discovered: 2h ago"));

  const card = findByClass(container, "pkmrag-card");
  assert.ok(card);
  const text = collectText(card);
  assert.ok(text.includes("EXTENDS"));
  assert.ok(text.includes("92% confidence"));
  assert.ok(text.includes("2h ago"));
  assert.ok(text.includes("gpt-4o-mini"));
});

test("renderInferencesSection renders in-section progress when active discover job matches note", () => {
  const container = createMockEl();
  const plugin = makeMockPlugin({
    activeJob: {
      type: "discover",
      phase: "discovery",
      cur: 1,
      total: 3,
      percent: 33,
      message: "Analyzing Quantum ↔ Qubits",
      note_path: "Concepts/Quantum.md",
    },
  });
  const context: NoteContext = {
    path: "Concepts/Quantum.md",
    title: "Quantum",
    tags: [],
    outgoing_links: [],
    backlinks: [],
    neighbors_2hop: [],
    inferred_relationships: [],
  };

  renderInferencesSection(container as any, plugin, context, () => {});

  const prog = findByClass(container, "pkmrag-in-section-progress");
  assert.ok(prog);
  const text = collectText(prog);
  assert.ok(text.includes("33%"));
  assert.ok(text.includes("Analyzing Quantum ↔ Qubits"));
});

test("DiscoveryEstimateModal renders token metrics without dollar cost", () => {
  const modal = new DiscoveryEstimateModal({} as any, {
    estimate: {
      candidate_count: 2,
      evaluated_count: 2,
      estimated_prompt_tokens: 1500,
      estimated_completion_tokens: 240,
      total_tokens: 1740,
      provider: "openai",
      model: "gpt-4o-mini",
      candidate_pairs: [
        {
          source_path: "A.md",
          target_path: "B.md",
          source_title: "A",
          target_title: "B",
          similarity: 0.84,
        },
      ],
    },
    notePath: "A.md",
    noteTitle: "A",
    onConfirm: async () => {},
  });

  modal.open();
  const text = collectText(modal.contentEl as any);
  assert.ok(text.includes("1,740"));
  assert.ok(text.includes("Est. Total Tokens"));
  assert.ok(text.includes("Candidate Pairs"));
  assert.ok(text.includes("84% similar"));
  // Ensure NO dollar cost is included per user requirement
  assert.ok(!text.includes("$"));
});
