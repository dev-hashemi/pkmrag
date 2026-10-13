/**
 * Unit tests for DaemonManager binary detection and lifecycle.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { DaemonManager } from "../src/daemon.js";
import { HostInstaller } from "../src/installer.js";
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
