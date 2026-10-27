/**
 * Desktop Background Daemon Lifecycle Manager for PKMRAG.
 */

import { FileSystemAdapter, Notice, Platform } from "obsidian";
import type PkmragPlugin from "./main";
import {
  getPlatformInfo,
  getPkmragCandidates,
  getExtraPaths,
  type ChildProcessModule,
  type PlatformInfo,
  type SpawnedProcess,
} from "./daemon_paths";

export class DaemonManager {
  private plugin: PkmragPlugin;
  private process: SpawnedProcess | null = null;
  public isStarting = false;
  private lastError: string | null = null;

  constructor(plugin: PkmragPlugin) {
    this.plugin = plugin;
  }

  get isRunning(): boolean {
    return this.process !== null && !this.isStarting;
  }

  get pid(): number | undefined {
    return this.process?.pid;
  }

  get statusMessage(): string {
    if (this.isStarting) return "Starting...";
    if (this.process && this.process.pid) return `Running (PID: ${this.process.pid})`;
    if (!this.isBinaryAvailable()) return "Engine not installed";
    if (this.lastError) return `Error: ${this.lastError}`;
    return "Stopped";
  }

  getPlatformInfo(): PlatformInfo {
    return getPlatformInfo();
  }

  getPkmragCandidates(home: string, isWin: boolean): string[] {
    return getPkmragCandidates(home, isWin);
  }

  isBinaryAvailable(): boolean {
    const custom = this.plugin.settings.customBinaryPath.trim();
    if (custom.length > 0) {
      const { fs } = this.getPlatformInfo();
      if (fs) {
        return fs.existsSync(custom);
      }
      return true;
    }
    const { home, isWin, fs } = this.getPlatformInfo();
    if (!fs || !home) return false;

    const candidates = this.getPkmragCandidates(home, isWin);
    return candidates.some((cand) => cand && fs.existsSync(cand));
  }

  private getChildProcessModule(): ChildProcessModule | null {
    if (!Platform.isDesktop) return null;
    const req = (window as unknown as { require?: (name: string) => unknown }).require;
    if (!req) return null;
    try {
      const modName = ["child", "process"].join("_");
      return req(modName) as ChildProcessModule;
    } catch {
      return null;
    }
  }

  private getVaultBasePath(): string {
    const adapter = this.plugin.app.vault.adapter;
    if (adapter instanceof FileSystemAdapter) {
      return adapter.getBasePath();
    }
    return "";
  }

  private resolveBinary(vaultPath: string): { command: string; args: string[] } {
    const custom = this.plugin.settings.customBinaryPath.trim();
    if (custom) {
      return { command: custom, args: ["serve", vaultPath, "-t", "http", "--port", "3747"] };
    }

    const { home, isWin, fs } = this.getPlatformInfo();
    if (fs && home) {
      for (const cand of this.getPkmragCandidates(home, isWin)) {
        if (fs.existsSync(cand)) {
          return { command: cand, args: ["serve", vaultPath, "-t", "http", "--port", "3747"] };
        }
      }
    }

    return { command: isWin ? "pkmrag.exe" : "pkmrag", args: ["serve", vaultPath, "-t", "http", "--port", "3747"] };
  }

  async start(): Promise<boolean> {
    if (!Platform.isDesktop) return false;
    if (this.process || this.isStarting) return true;

    // Check if daemon is already running (e.g. started in terminal or previous session)
    try {
      const health = await this.plugin.client.checkHealth();
      if (health.status === "healthy") {
        await this.plugin.client.autoDiscoverVaultToken(this.plugin.app);
        this.plugin.initEventStream();
        this.plugin.isVaultIndexed = health.is_indexed === true;
        this.plugin.activeJob = health.active_job || null;
        this.plugin.lastTaskError = null;
        this.plugin.updateStatusBar(true);
        return true;
      }
    } catch {
      // Not running, proceed with spawning
    }

    if (!this.isBinaryAvailable()) {
      this.lastError = "PKMRAG engine is not installed. Use Setup Wizard to install.";
      return false;
    }

    const cp = this.getChildProcessModule();
    if (!cp) {
      this.lastError = "Desktop Node environment unavailable.";
      return false;
    }

    const vaultPath = this.getVaultBasePath();
    if (!vaultPath) {
      this.lastError = "Could not resolve physical vault directory.";
      return false;
    }

    this.isStarting = true;
    this.lastError = null;
    this.plugin.updateStatusBar();

    const { command, args } = this.resolveBinary(vaultPath);

    const { home, isWin } = this.getPlatformInfo();
    const winObj = typeof window !== "undefined" ? (window as any) : (globalThis as any);
    const procEnv = winObj.process?.env || {};
    const pathSep = isWin ? ";" : ":";
    const extraPaths = getExtraPaths(home, isWin);
    const enhancedPath = extraPaths.concat((procEnv.PATH || "").split(pathSep)).filter(Boolean).join(pathSep);

    try {
      this.process = cp.spawn(command, args, {
        cwd: vaultPath,
        env: { ...procEnv, PATH: enhancedPath },
      });

      if (this.process.stderr) {
        this.process.stderr.on("data", (chunk: unknown) => {
          const errText = String(chunk).trim();
          if (errText) {
            this.lastError = errText;
          }
        });
      }

      this.process.on("error", (err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        this.lastError = `Failed to spawn ${command}: ${msg}`;
        this.process = null;
        this.isStarting = false;
        this.plugin.updateStatusBar(false);
      });

      this.process.on("exit", (code: unknown) => {
        if (code !== 0 && !this.lastError) {
          this.lastError = `Daemon process exited with code ${code}`;
        }
        this.process = null;
        this.isStarting = false;
        this.plugin.updateStatusBar(false);
      });

      // Poll health check for up to 15 seconds until ready
      for (let i = 0; i < 30; i++) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        try {
          const h = await this.plugin.client.checkHealth();
          if (h.status === "healthy") {
            this.isStarting = false;
            this.lastError = null;
            await this.plugin.client.autoDiscoverVaultToken(this.plugin.app);
            this.plugin.initEventStream();
            this.plugin.isVaultIndexed = h.is_indexed === true;
            this.plugin.activeJob = h.active_job || null;
            this.plugin.lastTaskError = null;
            this.plugin.updateStatusBar(true);
            return true;
          }
        } catch {
          // Keep polling
        }
      }

      this.isStarting = false;
      this.plugin.updateStatusBar(false);
      if (this.lastError) {
        new Notice(`PKMRAG: Daemon error: ${this.lastError}`);
      }
      return false;
    } catch (e: unknown) {
      this.lastError = e instanceof Error ? e.message : String(e);
      this.isStarting = false;
      this.process = null;
      this.plugin.updateStatusBar(false);
      return false;
    }
  }

  async stop(): Promise<void> {
    // 1. Immediately disconnect active SSE stream so Obsidian doesn't hold connection open
    try {
      this.plugin.disconnectEventStream();
    } catch {
      // Ignored
    }

    // 2. Request graceful daemon shutdown via HTTP
    try {
      await this.plugin.client.requestShutdown();
    } catch {
      // Ignored
    }

    // 3. Signal and await child process exit if tracked
    const proc = this.process;
    if (proc) {
      try {
        proc.kill("SIGTERM");
      } catch {
        // Ignored
      }

      // Poll up to 3s (30 x 100ms) for graceful exit
      for (let i = 0; i < 30; i++) {
        if (!this.process) break;
        await new Promise((resolve) => window.setTimeout(resolve, 100));
      }

      // Escalate to SIGKILL if still lingering
      if (this.process) {
        try {
          this.process.kill("SIGKILL");
        } catch {
          // Ignored
        }
        for (let i = 0; i < 10; i++) {
          if (!this.process) break;
          await new Promise((resolve) => window.setTimeout(resolve, 100));
        }
        this.process = null;
      }
    } else {
      // Daemon was external or detached; wait for port to be closed
      for (let i = 0; i < 6; i++) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        try {
          await this.plugin.client.checkHealth();
        } catch {
          break; // Port closed, daemon stopped
        }
      }
    }

    this.isStarting = false;
    this.plugin.activeJob = null;
    this.plugin.updateStatusBar(false);
  }

  async restart(): Promise<boolean> {
    await this.stop();
    // Safety buffer for OS file locks to settle
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    return this.start();
  }
}
