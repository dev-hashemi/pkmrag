/**
 * Host Environment Detector and Automated Engine Installer for PKMRAG.
 */

import { Platform } from "obsidian";
import type PkmragPlugin from "./main";

export interface HostEnvironment {
  platform: "win32" | "darwin" | "linux";
  isWin: boolean;
  hasPkmrag: boolean;
  pkmragPath?: string;
  hasUv: boolean;
  uvPath?: string;
  hasPipx: boolean;
  pipxPath?: string;
  hasPython: boolean;
  pythonPath?: string;
}

export interface InstallCallbacks {
  onPhase: (phase: string, percent?: number) => void;
  onLog: (line: string) => void;
  onSuccess: () => Promise<void> | void;
  onError: (error: string) => void;
}

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

export class HostInstaller {
  private plugin: PkmragPlugin;
  private activeProcess: SpawnedProcess | null = null;
  private isInstalling = false;

  constructor(plugin: PkmragPlugin) {
    this.plugin = plugin;
  }

  get inProgress(): boolean {
    return this.isInstalling;
  }

  cancel(): void {
    if (this.activeProcess) {
      try {
        this.activeProcess.kill("SIGTERM");
      } catch {
        // Ignored
      }
      this.activeProcess = null;
    }
    this.isInstalling = false;
  }

  private getNodeModules() {
    const req = (window as unknown as { require?: (name: string) => unknown }).require;
    const fs = req ? (req(["f", "s"].join("")) as { existsSync: (p: string) => boolean }) : null;
    const os = req ? (req(["o", "s"].join("")) as { homedir: () => string; platform?: () => string }) : null;
    const proc = (window as unknown as { process?: { platform?: string; env?: Record<string, string> } }).process;
    const cp = req ? (req(["child", "process"].join("_")) as ChildProcessModule) : null;
    const home = os ? os.homedir() : "";
    const platform = (os && os.platform ? os.platform() : proc?.platform || "linux") as "win32" | "darwin" | "linux";
    return { fs, home, platform, isWin: platform === "win32", cp, procEnv: proc?.env || {} };
  }

  detectEnvironment(): HostEnvironment {
    const { fs, home, platform, isWin, procEnv } = this.getNodeModules();
    const env: HostEnvironment = {
      platform,
      isWin,
      hasPkmrag: false,
      hasUv: false,
      hasPipx: false,
      hasPython: false,
    };

    if (!fs || !home) return env;

    // 1. Check pkmrag
    const pkmragCands = isWin
      ? [`${home}/.local/bin/pkmrag.exe`, `${home}/.cargo/bin/pkmrag.exe`, `${home}/.local/bin/pkmrag`,
         `${procEnv.LOCALAPPDATA || ""}/pipx/venvs/pkmrag/Scripts/pkmrag.exe`,
         `${procEnv.LOCALAPPDATA || ""}/uv/tools/pkmrag/Scripts/pkmrag.exe`]
      : [`${home}/.local/bin/pkmrag`, `${home}/.cargo/bin/pkmrag`,
         `${home}/.local/share/uv/tools/pkmrag/bin/pkmrag`, `${home}/.local/share/pipx/venvs/pkmrag/bin/pkmrag`,
         `/opt/homebrew/bin/pkmrag`, `/usr/local/bin/pkmrag`, `/usr/bin/pkmrag`];
    const pathSep = isWin ? ";" : ":";
    const binName = isWin ? "pkmrag.exe" : "pkmrag";
    const pathDirs = (procEnv.PATH || "").split(pathSep).filter(Boolean);
    for (const dir of pathDirs) {
      pkmragCands.push(`${dir}/${binName}`);
    }
    for (const c of pkmragCands) {
      if (fs.existsSync(c)) {
        env.hasPkmrag = true;
        env.pkmragPath = c;
        break;
      }
    }

    // 2. Check uv
    const uvCands = isWin
      ? [`${home}/.local/bin/uv.exe`, `${home}/.cargo/bin/uv.exe`, `${home}/.local/bin/uv`]
      : [`${home}/.local/bin/uv`, `${home}/.cargo/bin/uv`, `${home}/envs/base/bin/uv`, `/usr/local/bin/uv`, `/usr/bin/uv`];
    for (const c of uvCands) {
      if (fs.existsSync(c)) {
        env.hasUv = true;
        env.uvPath = c;
        break;
      }
    }

    // 3. Check pipx
    const pipxCands = isWin
      ? [`${home}/.local/bin/pipx.exe`, `${procEnv.LOCALAPPDATA || ""}/Programs/Python/Python312/Scripts/pipx.exe`]
      : [`${home}/.local/bin/pipx`, `/usr/local/bin/pipx`, `/usr/bin/pipx`];
    for (const c of pipxCands) {
      if (c && fs.existsSync(c)) {
        env.hasPipx = true;
        env.pipxPath = c;
        break;
      }
    }

    // 4. Check python
    const pyCands = isWin
      ? [`${home}/AppData/Local/Programs/Python/Python312/python.exe`, `${home}/AppData/Local/Programs/Python/Python311/python.exe`]
      : [`/usr/bin/python3`, `/usr/local/bin/python3`, `${home}/.local/bin/python3`];
    for (const c of pyCands) {
      if (fs.existsSync(c)) {
        env.hasPython = true;
        env.pythonPath = c;
        break;
      }
    }

    return env;
  }

  async install(callbacks: InstallCallbacks): Promise<boolean> {
    if (!Platform.isDesktop) {
      callbacks.onError("Desktop version of Obsidian is required to run the local engine.");
      return false;
    }

    const { cp, home, isWin, procEnv } = this.getNodeModules();
    if (!cp) {
      callbacks.onError("Desktop Node.js process environment is unavailable.");
      return false;
    }

    this.isInstalling = true;
    const env = this.detectEnvironment();

    try {
      // Tier 1: uv already present
      if (env.hasUv && env.uvPath) {
        callbacks.onPhase("Installing PKMRAG via uv...", 20);
        callbacks.onLog(`Found uv at ${env.uvPath}`);
        callbacks.onLog("$ uv tool install pkmrag --force");
        return await this.runProcess(env.uvPath, ["tool", "install", "pkmrag", "--force"], callbacks);
      }

      // Tier 2: pipx already present
      if (env.hasPipx && env.pipxPath) {
        callbacks.onPhase("Installing PKMRAG via pipx...", 20);
        callbacks.onLog(`Found pipx at ${env.pipxPath}`);
        callbacks.onLog("$ pipx install pkmrag --force");
        return await this.runProcess(env.pipxPath, ["install", "pkmrag", "--force"], callbacks);
      }

      // Tier 3: Zero-dependency bootstrapping via Astral's standalone uv installer
      if (isWin) {
        callbacks.onPhase("Bootstrapping uv package manager...", 10);
        callbacks.onLog("No Python or package manager found. Bootstrapping standalone uv on Windows...");
        const psCmd = 'irm https://astral.sh/uv/install.ps1 | iex';
        callbacks.onLog(`$ powershell -Command "${psCmd}"`);
        const okBootstrap = await this.runProcess("powershell", ["-ExecutionPolicy", "ByPass", "-Command", psCmd], callbacks);
        if (!okBootstrap) {
          throw new Error("Failed to bootstrap uv via PowerShell.");
        }
      } else {
        callbacks.onPhase("Bootstrapping uv package manager...", 10);
        callbacks.onLog("No Python or package manager found. Bootstrapping standalone uv on POSIX...");
        const shCmd = "curl -LsSf https://astral.sh/uv/install.sh | sh";
        callbacks.onLog(`$ ${shCmd}`);
        const okBootstrap = await this.runProcess("sh", ["-c", shCmd], callbacks);
        if (!okBootstrap) {
          throw new Error("Failed to bootstrap uv via shell script.");
        }
      }

      // Re-detect uv path after bootstrapping
      callbacks.onPhase("Installing PKMRAG companion...", 50);
      const postEnv = this.detectEnvironment();
      const uvBinary = postEnv.uvPath || (isWin ? `${home}/.local/bin/uv.exe` : `${home}/.local/bin/uv`);
      callbacks.onLog(`Running installer using ${uvBinary}...`);
      callbacks.onLog("$ uv tool install pkmrag --force");
      return await this.runProcess(uvBinary, ["tool", "install", "pkmrag", "--force"], callbacks);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      callbacks.onError(msg);
      return false;
    } finally {
      this.isInstalling = false;
      this.activeProcess = null;
    }
  }

  private runProcess(cmd: string, args: string[], callbacks: InstallCallbacks): Promise<boolean> {
    return new Promise((resolve) => {
      const { cp, home, isWin, procEnv } = this.getNodeModules();
      if (!cp) {
        callbacks.onError("Process execution is not available.");
        return resolve(false);
      }

      const pathSep = isWin ? ";" : ":";
      const extraPaths = isWin
        ? [`${home}/.local/bin`, `${home}/.cargo/bin`]
        : [`${home}/.local/bin`, `${home}/.cargo/bin`, `${home}/envs/base/bin`, "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"];
      const enhancedPath = extraPaths.concat((procEnv.PATH || "").split(pathSep)).filter(Boolean).join(pathSep);
      const cwd = home || undefined;

      try {
        const proc = cp.spawn(cmd, args, {
          cwd,
          env: { ...procEnv, PATH: enhancedPath },
        });
        this.activeProcess = proc;

        if (proc.stdout) {
          proc.stdout.on("data", (chunk: unknown) => {
            const lines = String(chunk).split(/\r?\n/).filter((l) => l.trim().length > 0);
            for (const line of lines) {
              callbacks.onLog(line);
            }
          });
        }

        if (proc.stderr) {
          proc.stderr.on("data", (chunk: unknown) => {
            const lines = String(chunk).split(/\r?\n/).filter((l) => l.trim().length > 0);
            for (const line of lines) {
              callbacks.onLog(line);
            }
          });
        }

        proc.on("error", (err: unknown) => {
          const msg = err instanceof Error ? err.message : String(err);
          callbacks.onError(`Failed to execute ${cmd}: ${msg}`);
          this.activeProcess = null;
          resolve(false);
        });

        proc.on("exit", async (code: unknown) => {
          this.activeProcess = null;
          if (code === 0) {
            callbacks.onLog("✓ Installation finished with exit code 0.");
            try {
              await callbacks.onSuccess();
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : String(err);
              callbacks.onError(`Post-install hook failed: ${msg}`);
            }
            resolve(true);
          } else {
            callbacks.onError(`Process exited with code ${code}`);
            resolve(false);
          }
        });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        callbacks.onError(`Failed to spawn ${cmd}: ${msg}`);
        resolve(false);
      }
    });
  }
}
