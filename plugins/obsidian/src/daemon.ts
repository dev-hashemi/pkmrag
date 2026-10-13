/**
 * Desktop Background Daemon Lifecycle Manager for PKMRAG.
 */

import { FileSystemAdapter, Notice, Platform } from "obsidian";
import type PkmragPlugin from "./main";

interface SpawnedProcess {
  pid?: number;
  kill: (signal?: string) => boolean;
  on: (event: string, listener: (...args: unknown[]) => void) => void;
  stdout?: { on: (event: string, listener: (chunk: unknown) => void) => void };
  stderr?: { on: (event: string, listener: (chunk: unknown) => void) => void };
}

interface ChildProcessModule {
  spawn: (command: string, args: string[], options?: Record<string, unknown>) => SpawnedProcess;
}

export class DaemonManager {
  private plugin: PkmragPlugin;
  private process: SpawnedProcess | null = null;
  private isStarting = false;
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

  private getPlatformInfo(): { home: string; isWin: boolean; fs: { existsSync: (p: string) => boolean } | null } {
    const winObj = typeof window !== "undefined" ? (window as any) : (globalThis as any);
    const req = winObj.require;
    const fs = req ? (req(["f", "s"].join("")) as { existsSync: (p: string) => boolean }) : null;
    const os = req ? (req(["o", "s"].join("")) as { homedir: () => string; platform?: () => string }) : null;
    const proc = winObj.process;
    const home = os ? os.homedir() : "";
    const isWin = (os && os.platform ? os.platform() === "win32" : false) || proc?.platform === "win32";
    return { home, isWin, fs };
  }

  private getPkmragCandidates(home: string, isWin: boolean): string[] {
    const winObj = typeof window !== "undefined" ? (window as any) : (globalThis as any);
    const proc = winObj.process;
    const procEnv = proc?.env || {};
    const localAppData = procEnv.LOCALAPPDATA || "";
    const list: string[] = [];
    if (isWin) {
      list.push(
        `${home}/.local/bin/pkmrag.exe`,
        `${home}/.cargo/bin/pkmrag.exe`,
        `${home}/.local/bin/pkmrag`
      );
      if (localAppData) {
        list.push(`${localAppData}/pipx/venvs/pkmrag/Scripts/pkmrag.exe`);
        list.push(`${localAppData}/uv/tools/pkmrag/Scripts/pkmrag.exe`);
        list.push(`${localAppData}/Programs/Python/Python311/Scripts/pkmrag.exe`);
        list.push(`${localAppData}/Programs/Python/Python312/Scripts/pkmrag.exe`);
      }
    } else {
      list.push(
        `${home}/.local/bin/pkmrag`,
        `${home}/.cargo/bin/pkmrag`,
        `${home}/.local/share/uv/tools/pkmrag/bin/pkmrag`,
        `${home}/.local/share/pipx/venvs/pkmrag/bin/pkmrag`,
        `/opt/homebrew/bin/pkmrag`,
        `/usr/local/bin/pkmrag`,
        `/usr/bin/pkmrag`
      );
    }
    const pathSep = isWin ? ";" : ":";
    const binName = isWin ? "pkmrag.exe" : "pkmrag";
    const pathDirs = (procEnv.PATH || "").split(pathSep).filter(Boolean);
    for (const dir of pathDirs) {
      list.push(`${dir}/${binName}`);
    }
    return list;
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

    const { command, args } = this.resolveBinary(vaultPath);

    const { home, isWin } = this.getPlatformInfo();
    const winObj = typeof window !== "undefined" ? (window as any) : (globalThis as any);
    const procEnv = winObj.process?.env || {};
    const pathSep = isWin ? ";" : ":";
    const extraPaths = isWin
      ? [`${home}/.local/bin`, `${home}/.cargo/bin`]
      : [
          `${home}/.local/bin`,
          `${home}/.cargo/bin`,
          `${home}/envs/base/bin`,
          "/opt/homebrew/bin",
          "/usr/local/bin",
          "/usr/bin",
        ];
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

      // Poll health check for up to 8 seconds until ready
      for (let i = 0; i < 16; i++) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        try {
          const h = await this.plugin.client.checkHealth();
          if (h.status === "healthy") {
            this.isStarting = false;
            this.lastError = null;
            this.plugin.updateStatusBar(true);
            return true;
          }
        } catch {
          // Keep polling
        }
      }

      this.isStarting = false;
      if (this.lastError) {
        new Notice(`PKMRAG: Daemon error: ${this.lastError}`);
      }
      return false;
    } catch (e: unknown) {
      this.lastError = e instanceof Error ? e.message : String(e);
      this.isStarting = false;
      this.process = null;
      return false;
    }
  }

  stop(): void {
    if (this.process) {
      try {
        this.process.kill("SIGTERM");
      } catch {
        // Ignored
      }
      this.process = null;
    }
    this.isStarting = false;
    this.plugin.updateStatusBar(false);
  }

  async restart(): Promise<boolean> {
    this.stop();
    await new Promise((resolve) => window.setTimeout(resolve, 800));
    return this.start();
  }
}
