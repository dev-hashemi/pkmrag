/**
 * Tests for the stage-aware progress rendering of the insights panel.
 */

import test from "node:test";
import assert from "node:assert/strict";
import {
  formatBytes,
  hasByteProgress,
  isModelDownload,
  jobDetail,
  renderJobProgressView,
  renderProgressBanner,
} from "../src/view_progress.js";
import { ActiveJobState } from "../src/types.js";
import { renderStatusBar } from "../src/status_bar.js";
import { createMockEl, collectText } from "./mock_dom.js";

function makeJob(overrides: Partial<ActiveJobState> = {}): ActiveJobState {
  return {
    type: "ingest",
    stage: "graph",
    unit: "items",
    phase: "Ingesting graph notes",
    cur: 1,
    total: 2,
    percent: 50,
    message: "Ingesting graph notes (1/2)",
    ...overrides,
  };
}

test("the structured stage decides whether the model is downloading", () => {
  assert.equal(isModelDownload(makeJob({ stage: "model_download" })), true);
  assert.equal(isModelDownload(makeJob({ stage: "graph" })), false);
  assert.equal(isModelDownload(makeJob({ stage: "vector" })), false);
  assert.equal(isModelDownload(makeJob({ stage: "scan" })), false);
});

test("the phase text is only used as a fallback for older servers", () => {
  const legacy = makeJob({ stage: undefined, phase: "Downloading/loading embedding model" });
  assert.equal(isModelDownload(legacy), true);

  const legacyIndexing = makeJob({ stage: undefined, phase: "Ingesting graph notes" });
  assert.equal(isModelDownload(legacyIndexing), false);
});

test("byte progress is only used when the server reports bytes", () => {
  assert.equal(hasByteProgress(makeJob({ unit: "bytes", total: 100 })), true);
  assert.equal(hasByteProgress(makeJob({ unit: "bytes", total: 0 })), false);
  assert.equal(hasByteProgress(makeJob({ unit: "items", total: 100 })), false);
});

test("byte counts are rendered in human readable units", () => {
  assert.equal(formatBytes(0), "0 MB");
  assert.equal(formatBytes(32 * 1024 * 1024), "32.0 MB");
  assert.equal(formatBytes(512 * 1024), "512 KB");
});

test("the detail line prefers byte progress over the message", () => {
  const job = makeJob({
    stage: "model_download",
    unit: "bytes",
    cur: 32 * 1024 * 1024,
    total: 64 * 1024 * 1024,
    percent: 50,
    message: "Downloading embedding model (BAAI/bge-small-en-v1.5) (32.0 MB / 64.0 MB)",
  });
  assert.equal(jobDetail(job, "fallback"), "32.0 MB / 64.0 MB");
});

test("the download card is shown for the model download stage", () => {
  const container = createMockEl();
  const plugin = {} as any;

  renderJobProgressView(
    container as any,
    plugin,
    makeJob({ stage: "model_download", unit: "bytes", cur: 0, total: 0, percent: 0 })
  );

  const text = collectText(container);
  assert.ok(text.includes("Downloading Local Embedding Model"));
  assert.ok(!text.includes("Vault Indexing & Property Graph"));
});

test("the indexing card is shown for the graph and vector stages", () => {
  for (const stage of ["scan", "graph", "vector"]) {
    const container = createMockEl();
    renderJobProgressView(container as any, {} as any, makeJob({ stage }));
    const text = collectText(container);
    assert.ok(text.includes("Vault Indexing & Property Graph"), `stage ${stage}`);
    assert.ok(!text.includes("Downloading Local Embedding Model"), `stage ${stage}`);
  }
});

test("the download card shows the byte percentage once the size is known", () => {
  const container = createMockEl();
  renderJobProgressView(
    container as any,
    {} as any,
    makeJob({
      stage: "model_download",
      unit: "bytes",
      cur: 32 * 1024 * 1024,
      total: 64 * 1024 * 1024,
      percent: 50,
    })
  );

  const text = collectText(container);
  assert.ok(text.includes("Step 1/2: 50%"));
  assert.ok(text.includes("32.0 MB / 64.0 MB"));
});

test("the banner labels the model download and the indexing stages", () => {
  const download = createMockEl();
  renderProgressBanner(download as any, makeJob({ stage: "model_download", unit: "bytes" }));
  assert.ok(collectText(download).includes("Downloading Embedding Model"));

  const indexing = createMockEl();
  renderProgressBanner(indexing as any, makeJob({ stage: "vector" }));
  const text = collectText(indexing);
  assert.ok(text.includes("Vault Indexing"));
  assert.ok(!text.includes("Downloading Embedding Model"));
});

test("the status bar names the model download instead of the indexing job", () => {
  const statusBar = createMockEl();
  const plugin = {
    installer: undefined,
    daemonManager: { isStarting: false, isBinaryAvailable: () => true },
    isServerConnected: true,
    isVaultIndexed: false,
    activateView: () => {},
    app: { workspace: {} },
    activeJob: makeJob({ stage: "model_download", unit: "bytes", cur: 0, total: 0 }),
  } as any;

  renderStatusBar(statusBar as any, plugin);
  const text = collectText(statusBar);
  assert.ok(text.includes("Downloading Model"));
  assert.ok(!text.includes("Indexing"));
});
