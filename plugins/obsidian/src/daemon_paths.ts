/**
 * System path discovery and platform resolution helpers for PKMRAG daemon.
 */

export interface PlatformInfo {
  home: string;
  isWin: boolean;
  fs: { existsSync: (p: string) => boolean } | null;
}

export interface SpawnedProcess {
  pid?: number;
  kill: (signal?: string) => boolean;
  on: (event: string, listener: (...args: unknown[]) => void) => void;
  stdout?: { on: (event: string, listener: (chunk: unknown) => void) => void };
  stderr?: { on: (event: string, listener: (chunk: unknown) => void) => void };
}

export interface ChildProcessModule {
  spawn: (command: string, args: string[], options?: Record<string, unknown>) => SpawnedProcess;
}

export function getPlatformInfo(): PlatformInfo {
  const winObj = typeof window !== "undefined" ? (window as any) : undefined;
  const req = winObj?.require ?? (typeof require !== "undefined" ? require : null);
  const fs = req ? (req("fs") as { existsSync: (p: string) => boolean }) : null;
  const os = req ? (req("os") as { homedir: () => string; platform?: () => string }) : null;
  const proc = winObj?.process ?? (typeof process !== "undefined" ? process : undefined);
  const home = os ? os.homedir() : "";
  const isWin = (os && os.platform ? os.platform() === "win32" : false) || proc?.platform === "win32";
  return { home, isWin, fs };
}

export function getPkmragCandidates(home: string, isWin: boolean): string[] {
  const winObj = typeof window !== "undefined" ? (window as any) : undefined;
  const proc = winObj?.process ?? (typeof process !== "undefined" ? process : undefined);
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

export function getExtraPaths(home: string, isWin: boolean): string[] {
  if (isWin) {
    return [`${home}/.local/bin`, `${home}/.cargo/bin`];
  }
  return [
    `${home}/.local/bin`,
    `${home}/.cargo/bin`,
    `${home}/envs/base/bin`,
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
  ];
}
