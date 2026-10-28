#!/usr/bin/env node
/**
 * Standalone Obsidian Plugin Repository Exporter.
 *
 * Prepares an independent, submission-ready repository for publishing
 * to the official Obsidian Community Plugins directory (obsidianmd/obsidian-releases).
 *
 * Usage:
 *   node scripts/export_standalone.mjs [target_path]
 * Example:
 *   node scripts/export_standalone.mjs ../obsidian-pkmrag
 */

import { existsSync, mkdirSync, cpSync, writeFileSync, readFileSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(PLUGIN_ROOT, "../..");

const targetDir = process.argv[2]
  ? resolve(process.cwd(), process.argv[2])
  : resolve(REPO_ROOT, "../obsidian-pkmrag");

console.log(`Exporting standalone Obsidian plugin to: ${targetDir}`);

if (!existsSync(targetDir)) {
  mkdirSync(targetDir, { recursive: true });
}

// 1. Files to copy from plugins/obsidian/
const filesToCopy = [
  "manifest.json",
  "package.json",
  "tsconfig.json",
  "esbuild.config.mjs",
  "styles.css",
  "icon.svg",
  "versions.json",
  "README.md",
];

for (const file of filesToCopy) {
  const src = join(PLUGIN_ROOT, file);
  const dest = join(targetDir, file);
  if (existsSync(src)) {
    cpSync(src, dest, { recursive: true });
  }
}

// 2. Directories to copy
for (const dir of ["src", "tests", "assets"]) {
  const src = join(PLUGIN_ROOT, dir);
  const dest = join(targetDir, dir);
  if (existsSync(src)) {
    cpSync(src, dest, { recursive: true });
  }
}

// 3. Copy LICENSE from monorepo root
const rootLicense = join(REPO_ROOT, "LICENSE");
if (existsSync(rootLicense)) {
  cpSync(rootLicense, join(targetDir, "LICENSE"));
}

// 4. Create standalone GitHub Actions workflow
const workflowsDir = join(targetDir, ".github", "workflows");
mkdirSync(workflowsDir, { recursive: true });

const releaseWorkflow = `name: Release Obsidian Plugin

on:
  push:
    tags:
      - "*"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Typecheck
        run: npm run typecheck

      - name: Test
        run: npm test

      - name: Build plugin
        run: npm run build

      - name: Create Release
        uses: softprops/action-gh-release@v2
        if: startsWith(github.ref, 'refs/tags/')
        with:
          files: |
            main.js
            manifest.json
            styles.css
`;

writeFileSync(join(workflowsDir, "release.yml"), releaseWorkflow, "utf8");

// 5. Create .gitignore if not present
const gitignore = `node_modules/
dist/
main.js
.DS_Store
`;
writeFileSync(join(targetDir, ".gitignore"), gitignore, "utf8");

console.log("✓ Standalone plugin repository prepared successfully!");
console.log(`\nNext steps for publication:\n`);
console.log(`  1. cd ${targetDir}`);
console.log(`  2. git init && git add . && git commit -m "feat: initial standalone release"`);
console.log(`  3. gh repo create dev-hashemi/obsidian-pkmrag --public --source=. --push`);
console.log(`  4. git tag 0.10.0 && git push origin 0.10.0`);
console.log(`  5. Submit PR to obsidianmd/obsidian-releases adding to community-plugins.json`);
