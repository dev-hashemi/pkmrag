#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const pluginDir = path.resolve(import.meta.dirname, "..");
const repoRoot = path.resolve(pluginDir, "../..");

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const content = fs.readFileSync(filePath, "utf8");
  const env = {};
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx !== -1) {
      const key = trimmed.slice(0, eqIdx).trim();
      let val = trimmed.slice(eqIdx + 1).trim();
      if (
        (val.startsWith('"') && val.endsWith('"')) ||
        (val.startsWith("'") && val.endsWith("'"))
      ) {
        val = val.slice(1, -1);
      }
      env[key] = val;
    }
  }
  return env;
}

const env = {
  ...loadEnvFile(path.join(repoRoot, ".env")),
  ...loadEnvFile(path.join(pluginDir, ".env")),
  ...process.env,
};

const args = process.argv.slice(2);
const symlink = args.includes("--symlink") || args.includes("-s");
const nonFlagArgs = args.filter((a) => !a.startsWith("-"));

let rawVaultPath =
  nonFlagArgs[0] || env.PKMRAG_VAULT_PATH || env.VAULT_PATH || env.OBSIDIAN_VAULT_PATH;

if (!rawVaultPath) {
  console.error("\x1b[31mError: Vault path not specified.\x1b[0m");
  console.error(
    "Define \x1b[36mPKMRAG_VAULT_PATH\x1b[0m in your \x1b[32m.env\x1b[0m file, or pass it as an argument:"
  );
  console.error("  \x1b[90mnpm run install-vault -- /path/to/your/vault\x1b[0m\n");
  process.exit(1);
}

if (rawVaultPath.startsWith("~/") || rawVaultPath === "~") {
  rawVaultPath = path.join(os.homedir(), rawVaultPath.slice(1));
}
const vaultPath = path.resolve(rawVaultPath);

if (!fs.existsSync(vaultPath) || !fs.statSync(vaultPath).isDirectory()) {
  console.error(
    `\x1b[31mError: Vault path does not exist or is not a directory:\x1b[0m ${vaultPath}`
  );
  process.exit(1);
}

const manifestPath = path.join(pluginDir, "manifest.json");
if (!fs.existsSync(manifestPath)) {
  console.error(`\x1b[31mError: manifest.json not found in\x1b[0m ${pluginDir}`);
  process.exit(1);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const pluginId = manifest.id || "pkmrag";

const targetDir = path.join(vaultPath, ".obsidian", "plugins", pluginId);
fs.mkdirSync(targetDir, { recursive: true });

const filesToInstall = ["manifest.json", "main.js"];
if (fs.existsSync(path.join(pluginDir, "styles.css"))) {
  filesToInstall.push("styles.css");
}
if (fs.existsSync(path.join(pluginDir, "icon.svg"))) {
  filesToInstall.push("icon.svg");
}


for (const file of filesToInstall) {
  const src = path.join(pluginDir, file);
  const dst = path.join(targetDir, file);
  if (!fs.existsSync(src)) {
    console.error(`\x1b[31mError: Required file missing:\x1b[0m ${src}. Run npm run build first.`);
    process.exit(1);
  }
  try {
    fs.rmSync(dst, { force: true });
  } catch {}
  if (symlink) {
    fs.symlinkSync(path.resolve(src), dst);
  } else {
    fs.copyFileSync(src, dst);
  }
}

const obsidianDir = path.join(vaultPath, ".obsidian");
const communityPluginsFile = path.join(obsidianDir, "community-plugins.json");
let enabled = false;
try {
  let pluginsList = [];
  if (fs.existsSync(communityPluginsFile)) {
    pluginsList = JSON.parse(fs.readFileSync(communityPluginsFile, "utf8"));
  }
  if (Array.isArray(pluginsList)) {
    if (!pluginsList.includes(pluginId)) {
      pluginsList.push(pluginId);
      fs.writeFileSync(communityPluginsFile, JSON.stringify(pluginsList, null, 2) + "\n", "utf8");
    }
    enabled = true;
  }
} catch (err) {
  console.warn(`Could not update community-plugins.json: ${err.message}`);
}

console.log(`\n\x1b[32m✓ PKMRAG Obsidian Plugin Installed\x1b[0m (\x1b[36m${pluginId}\x1b[0m)`);
console.log(`  Vault:        ${vaultPath}`);
console.log(`  Plugin Path:  ${targetDir}`);
console.log(`  Install Mode: ${symlink ? "\x1b[33mSymlinked\x1b[0m" : "\x1b[32mCopied\x1b[0m"}`);
console.log(`  Files:        ${filesToInstall.join(", ")}`);
console.log(
  `  Status:       ${enabled ? "\x1b[32mEnabled in community-plugins.json\x1b[0m" : "Manual enable needed"}\n`
);
console.log("Next Steps:");
console.log("  1. In Obsidian: Press Ctrl/Cmd + R to reload plugins.");
console.log("  2. Open Settings → Community Plugins to verify PKMRAG is active.");
console.log(`  3. Start PKMRAG daemon:`);
console.log(`     \x1b[32muv run pkmrag serve "${vaultPath}" -t http --port 3747\x1b[0m\n`);
