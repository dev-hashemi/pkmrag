/**
 * Friendly offline recovery screen rendered when PKMRAG daemon is unreachable.
 */

import { Notice, setIcon } from "obsidian";
import type PkmragPlugin from "./main";

export function renderOfflineView(
  container: HTMLElement,
  plugin: PkmragPlugin,
  onRetry: () => void
): void {
  const wrapper = container.createDiv({ cls: "pkmrag-offline-container" });

  const iconEl = wrapper.createDiv({ cls: "pkmrag-offline-icon" });
  setIcon(iconEl, "pkmrag-ribbon");
  wrapper.createEl("h3", { text: "PKMRAG Daemon Offline", cls: "pkmrag-offline-title" });

  wrapper.createEl("p", {
    cls: "pkmrag-offline-desc",
    text: `PKMRAG daemon is not reachable at ${plugin.settings.serverUrl}. Start the local daemon to inspect graph insights, missing links, and AI suggestions:`,
  });

  // Actions
  const btnRow = wrapper.createDiv({ cls: "pkmrag-offline-actions" });

  const startBtn = btnRow.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "🚀 Start Daemon",
  });
  startBtn.onclick = async () => {
    startBtn.setText("Starting...");
    startBtn.setAttribute("disabled", "true");
    const ok = await plugin.daemonManager.start();
    if (ok) {
      new Notice("PKMRAG: Daemon started successfully.");
      onRetry();
    } else {
      startBtn.setText("🚀 Start Daemon");
      startBtn.removeAttribute("disabled");
      new Notice("Could not auto-start daemon. Check settings or executable path.");
    }
  };

  const retryBtn = btnRow.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Retry Connection",
  });
  retryBtn.onclick = () => {
    retryBtn.setText("Connecting...");
    retryBtn.setAttribute("disabled", "true");
    onRetry();
  };

  const settingsBtn = btnRow.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };

  // Advanced / manual command info
  const codeBox = wrapper.createDiv({ cls: "pkmrag-code-box" });
  const cmd = `uv run pkmrag serve . -t http --port 3747`;
  codeBox.createEl("code", { text: cmd });

  const copyBtn = codeBox.createEl("button", { cls: "pkmrag-copy-btn", text: "Copy" });
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(cmd);
    new Notice("Copied command to clipboard!");
  };
}
