/**
 * Unit tests for DaemonManager binary detection and lifecycle.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { DaemonManager } from "../src/daemon.js";
import { HostInstaller } from "../src/installer.js";
import { renderJobProgressView, renderTaskErrorCard } from "../src/view_progress.js";
import { DEFAULT_SETTINGS } from "../src/types.js";

function createMockPlugin(customBinaryPath = "") {
  return {
    settings: {
      ...DEFAULT_SETTINGS,
      customBinaryPath,
    },
    client: {
      checkHealth: async () => {
        throw new Error("Connection refused");
      },
    },
    updateStatusBar: () => {},
  } as any;
}

test("DaemonManager: isBinaryAvailable returns false when pkmrag is absent even if uv exists", () => {
  const plugin = createMockPlugin();
  const daemon = new DaemonManager(plugin);

  // Mock getPlatformInfo: pretend uv exists but pkmrag does not
  (daemon as any).getPlatformInfo = () => ({
    home: "/home/mockuser",
    isWin: false,
    fs: {
      existsSync: (path: string) => {
        // uv binary exists, but pkmrag binary does NOT
        if (path.endsWith("/uv") || path.endsWith("/uv.exe")) return true;
        return false;
      },
    },
  });

  assert.equal(daemon.isBinaryAvailable(), false);
  assert.equal(daemon.statusMessage, "Engine not installed");
});

test("DaemonManager: isBinaryAvailable returns true when pkmrag exists in candidate paths", () => {
  const plugin = createMockPlugin();
  const daemon = new DaemonManager(plugin);

  (daemon as any).getPlatformInfo = () => ({
    home: "/home/mockuser",
    isWin: false,
    fs: {
      existsSync: (path: string) => path === "/home/mockuser/.local/bin/pkmrag",
    },
  });

  assert.equal(daemon.isBinaryAvailable(), true);
  assert.equal(daemon.statusMessage, "Stopped");
});

test("DaemonManager: isBinaryAvailable honors valid customBinaryPath", () => {
  const plugin = createMockPlugin("/opt/custom/pkmrag");
  const daemon = new DaemonManager(plugin);

  (daemon as any).getPlatformInfo = () => ({
    home: "/home/mockuser",
    isWin: false,
    fs: {
      existsSync: (path: string) => path === "/opt/custom/pkmrag",
    },
  });

  assert.equal(daemon.isBinaryAvailable(), true);
});

test("DaemonManager: isBinaryAvailable returns false for non-existent customBinaryPath", () => {
  const plugin = createMockPlugin("/opt/custom/nonexistent-pkmrag");
  const daemon = new DaemonManager(plugin);

  (daemon as any).getPlatformInfo = () => ({
    home: "/home/mockuser",
    isWin: false,
    fs: {
      existsSync: () => false,
    },
  });

  assert.equal(daemon.isBinaryAvailable(), false);
});

test("HostInstaller: detectEnvironment detects uv without claiming hasPkmrag", () => {
  const plugin = createMockPlugin();
  const installer = new HostInstaller(plugin);

  (installer as any).getNodeModules = () => ({
    home: "/home/mockuser",
    platform: "linux",
    isWin: false,
    procEnv: { PATH: "/usr/bin:/bin" },
    fs: {
      existsSync: (path: string) => path === "/home/mockuser/.local/bin/uv",
    },
  });

  const env = installer.detectEnvironment();
  assert.equal(env.hasUv, true);
  assert.equal(env.hasPkmrag, false);
});

function createMockEl(): any {
  const children: any[] = [];
  const el: any = {
    children,
    textContent: "",
    style: {},
    className: "",
    createDiv: (opts?: any) => {
      const child = createMockEl();
      if (opts?.cls) child.className = opts.cls;
      if (opts?.text) child.textContent = opts.text;
      children.push(child);
      return child;
    },
    createSpan: (opts?: any) => {
      const child = createMockEl();
      if (opts?.cls) child.className = opts.cls;
      if (opts?.text) child.textContent = opts.text;
      children.push(child);
      return child;
    },
    createEl: (tag: string, opts?: any) => {
      const child = createMockEl();
      child.tag = tag;
      if (opts?.cls) child.className = opts.cls;
      if (opts?.text) child.textContent = opts.text;
      children.push(child);
      return child;
    },
    setText: (t: string) => {
      el.textContent = t;
    },
    setAttribute: () => {},
    addClass: (cls: string) => {
      el.className = (el.className + " " + cls).trim();
    },
    removeClass: (cls: string) => {
      el.className = el.className.replace(cls, "").trim();
    },
  };
  return el;
}

test("renderJobProgressView: renders model download view with percentage and label", () => {
  const container = createMockEl();
  const plugin = createMockPlugin();

  renderJobProgressView(container, plugin, {
    type: "ingest",
    phase: "downloading model",
    cur: 0,
    total: 1,
    percent: 35,
    message: "Downloading model weights (~130 MB)...",
  });

  const allText = JSON.stringify(container);
  assert.ok(allText.includes("Downloading Local Embedding Model"));
  assert.ok(allText.includes("Step 1/2: Downloading"));
  assert.ok(allText.includes("Downloading model weights (~130 MB)..."));
});

test("renderTaskErrorCard: renders network diagnostic and invokes onRetry", () => {
  const container = createMockEl();
  const plugin = createMockPlugin();
  let retryCalled = false;

  renderTaskErrorCard(
    container,
    plugin,
    {
      type: "ingest",
      message: "urllib.error.URLError: <urlopen error [Errno 110] Connection timed out>",
      timestamp: new Date(),
    },
    () => {
      retryCalled = true;
    }
  );

  const allText = JSON.stringify(container);
  assert.ok(allText.includes("Vault Indexing Failed"));
  assert.ok(allText.includes("Network problem detected"));
  assert.ok(allText.includes("Connection timed out"));

  // Find the retry button in the mock tree and invoke click
  function findRetryBtn(node: any): any {
    if (node.textContent === "🔄 Retry Indexing" && node.onclick) return node;
    for (const child of node.children || []) {
      const found = findRetryBtn(child);
      if (found) return found;
    }
    return null;
  }

  const btn = findRetryBtn(container);
  assert.ok(btn !== null);
  btn.onclick();
  assert.equal(retryCalled, true);
});
