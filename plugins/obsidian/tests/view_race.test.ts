/**
 * Tests for the insights view: out-of-order responses and request fault isolation.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { PkmragInsightsView } from "../src/view.js";
import { renderGapsSection } from "../src/view_gaps.js";
import { DEFAULT_SETTINGS, NoteContext } from "../src/types.js";
import { createMockEl, collectText } from "./mock_dom.js";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeContext(path: string): NoteContext {
  return {
    path,
    title: path.replace(/\.md$/, ""),
    tags: [],
    outgoing_links: [],
    backlinks: [],
    neighbors_2hop: [],
    is_unresolved: false,
    inferred_relationships: [],
  };
}

type Pending = {
  context: Deferred<NoteContext | null>;
  gaps: Deferred<any[]>;
};

function createView(): { view: PkmragInsightsView; pending: Map<string, Pending>; plugin: any } {
  const pending = new Map<string, Pending>();

  const plugin = {
    settings: { ...DEFAULT_SETTINGS },
    isServerConnected: true,
    isVaultIndexed: true,
    activeJob: null,
    lastTaskError: null,
    vaultStats: null,
    client: {
      getNoteContext: (path: string) => {
        const entry: Pending = { context: deferred(), gaps: deferred() };
        pending.set(path, entry);
        return entry.context.promise;
      },
      getGaps: (path: string) => {
        const entry = pending.get(path);
        if (!entry) throw new Error("gaps requested before context");
        return entry.gaps.promise;
      },
    },
    setActiveInsights: () => {},
    updateStatusBar: () => {},
    daemonManager: { isBinaryAvailable: () => true, start: async () => true },
    app: { workspace: { openLinkText: () => {} } },
  } as any;

  const view = new PkmragInsightsView({ app: plugin.app } as any, plugin);
  return { view, pending, plugin };
}

test("a stale response does not overwrite the current note", async () => {
  const { view, pending } = createView();

  const first = view.loadInsightsForNote("A.md");
  const second = view.loadInsightsForNote("B.md");

  // B answers first, then the older A request answers late.
  pending.get("B.md")!.context.resolve(makeContext("B.md"));
  pending.get("B.md")!.gaps.resolve([]);
  await second;

  pending.get("A.md")!.context.resolve(makeContext("A.md"));
  pending.get("A.md")!.gaps.resolve([]);
  await first;

  const state = view as any;
  assert.equal(state.currentNotePath, "B.md");
  assert.equal(state.context.path, "B.md");
});

test("a stale failure does not mark a healthy daemon as offline", async () => {
  const { view, pending, plugin } = createView();

  const first = view.loadInsightsForNote("A.md");
  const second = view.loadInsightsForNote("B.md");

  pending.get("B.md")!.context.resolve(makeContext("B.md"));
  pending.get("B.md")!.gaps.resolve([]);
  await second;

  // The abandoned request fails after the user already moved on.
  pending.get("A.md")!.context.reject(new Error("Connection refused"));
  pending.get("A.md")!.gaps.reject(new Error("Connection refused"));
  await first;

  const state = view as any;
  assert.equal(state.isOffline, false);
  assert.equal(plugin.isServerConnected, true);
  assert.equal(state.context.path, "B.md");
});

test("a failing suggestions request keeps the graph context", async () => {
  const { view, pending, plugin } = createView();

  const loading = view.loadInsightsForNote("A.md");

  pending.get("A.md")!.context.resolve(makeContext("A.md"));
  pending.get("A.md")!.gaps.reject(new Error("Gaps fetch failed with HTTP 500"));
  await loading;

  const state = view as any;
  assert.equal(state.context.path, "A.md");
  assert.equal(state.isOffline, false);
  assert.equal(plugin.isServerConnected, true);
  assert.equal(state.gapsError, "Gaps fetch failed with HTTP 500");
});

test("a failing context request marks the panel offline", async () => {
  const { view, pending, plugin } = createView();

  const loading = view.loadInsightsForNote("A.md");

  pending.get("A.md")!.context.reject(new Error("Connection refused"));
  pending.get("A.md")!.gaps.resolve([]);
  await loading;

  const state = view as any;
  assert.equal(state.isOffline, true);
  assert.equal(plugin.isServerConnected, false);
});

test("an unindexed vault is reported as unindexed, not offline", async () => {
  const { view, pending, plugin } = createView();

  const loading = view.loadInsightsForNote("A.md");

  pending.get("A.md")!.context.reject(new Error("VAULT_UNINDEXED"));
  pending.get("A.md")!.gaps.reject(new Error("VAULT_UNINDEXED"));
  await loading;

  const state = view as any;
  assert.equal(state.isUnindexed, true);
  assert.equal(state.isOffline, false);
  assert.equal(plugin.isVaultIndexed, false);
});

test("the missing links section shows a placeholder while loading", () => {
  const container = createMockEl();
  const plugin = { settings: { ...DEFAULT_SETTINGS, dismissedSuggestions: {} } } as any;

  renderGapsSection(container as any, plugin, [], "A.md", () => {}, { loading: true });

  const text = collectText(container);
  assert.ok(text.includes("Missing Links"));
  assert.ok(text.includes("Scanning vault for related notes..."));
  assert.ok(!text.includes("No unlinked semantic gaps detected."));
});

test("the missing links section surfaces a load failure", () => {
  const container = createMockEl();
  const plugin = { settings: { ...DEFAULT_SETTINGS, dismissedSuggestions: {} } } as any;

  renderGapsSection(container as any, plugin, [], "A.md", () => {}, { error: "HTTP 500" });

  const text = collectText(container);
  assert.ok(text.includes("Could not load suggestions: HTTP 500"));
});
