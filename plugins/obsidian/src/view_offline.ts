/**
 * Friendly offline recovery screen rendered when Orbit daemon is unreachable.
 */

import { Notice } from "obsidian";
import type OrbitInsightsPlugin from "./main";

export function renderOfflineView(
  container: HTMLElement,
  plugin: OrbitInsightsPlugin,
  onRetry: () => void
): void {
  const wrapper = container.createDiv({ cls: "orbit-offline-container" });

  const iconEl = wrapper.createDiv({ cls: "orbit-offline-icon", text: "📡" });
  wrapper.createEl("h3", { text: "Orbit Daemon Offline", cls: "orbit-offline-title" });

  wrapper.createEl("p", {
    cls: "orbit-offline-desc",
    text: `Orbit daemon is not reachable at ${plugin.settings.serverUrl}. Start the daemon to inspect graph insights, missing links, and contradictions:`,
  });

  // Code snippet with click-to-copy
  const codeBox = wrapper.createDiv({ cls: "orbit-code-box" });
  const cmd = `uv run orbit serve . -t http --port 3747`;
  codeBox.createEl("code", { text: cmd });

  const copyBtn = codeBox.createEl("button", { cls: "orbit-copy-btn", text: "Copy" });
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(cmd);
    new Notice("Copied command to clipboard!");
  };

  // Actions
  const btnRow = wrapper.createDiv({ cls: "orbit-offline-actions" });
  const retryBtn = btnRow.createEl("button", {
    cls: "orbit-btn-sm mod-cta",
    text: "Retry Connection",
  });
  retryBtn.onclick = () => {
    retryBtn.setText("Connecting...");
    retryBtn.setAttribute("disabled", "true");
    onRetry();
  };

  const settingsBtn = btnRow.createEl("button", {
    cls: "orbit-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    // Open settings tab
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };
}
