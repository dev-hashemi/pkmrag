/**
 * Helper utilities for Obsidian compliance & quality gate tests.
 */

import assert from "node:assert";
import { readdirSync, readFileSync, existsSync, statSync } from "node:fs";
import { join, relative } from "node:path";

let dir = import.meta.dirname;
let repoDir = dir;
let obsidianPkg = dir;

let curr = dir;
let foundMonorepo = false;
while (curr !== join(curr, "..")) {
  if (existsSync(join(curr, "pyproject.toml"))) {
    repoDir = curr;
    obsidianPkg = join(curr, "plugins", "obsidian");
    foundMonorepo = true;
    break;
  }
  curr = join(curr, "..");
}

if (!foundMonorepo) {
  curr = dir;
  while (curr !== join(curr, "..")) {
    if (existsSync(join(curr, "manifest.json"))) {
      repoDir = curr;
      obsidianPkg = curr;
      break;
    }
    curr = join(curr, "..");
  }
}

export const REPO = repoDir;
export const OBSIDIAN_PKG = obsidianPkg;
export const OBSIDIAN_SRC = join(OBSIDIAN_PKG, "src");

export function collectTsFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules") continue;
      collectTsFiles(full, out);
    } else if (/\.tsx?$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

export function srcFiles(): { path: string; rel: string; code: string }[] {
  return collectTsFiles(OBSIDIAN_SRC).map((path) => ({
    path,
    rel: relative(REPO, path),
    code: readFileSync(path, "utf8"),
  }));
}

export function assertNoMatch(
  files: { rel: string; code: string }[],
  pattern: RegExp,
  message: string,
  allowlist: string[] = []
): void {
  const hits: string[] = [];
  for (const f of files) {
    const stripped = f.code
      .split("\n")
      .filter((line) => !line.trim().startsWith("*") && !line.trim().startsWith("//"))
      .join("\n");
    pattern.lastIndex = 0;
    if (pattern.test(stripped) && !allowlist.includes(f.rel)) {
      hits.push(f.rel);
    }
  }
  assert.deepStrictEqual(hits, [], `${message}: ${hits.join(", ")}`);
}
