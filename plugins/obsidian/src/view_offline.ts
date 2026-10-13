/**
 * Friendly offline recovery screen rendered when PKMRAG daemon is unreachable.
 */

import { Notice, setIcon } from "obsidian";
import type PkmragPlugin from "./main";
import { renderSetupWizardView } from "./view_setup_wizard";

export function renderOfflineView(
  container: HTMLElement,
  plugin: PkmragPlugin,
  onRetry: () => void
): void {
  if (!plugin.daemonManager.isBinaryAvailable()) {
    renderSetupWizardView(container, plugin, onRetry);
    return;
  }

  const wrapper = container.createDiv({ cls: "pkmrag-offline-container" });

  const iconEl = wrapper.createDiv({ cls: "pkmrag-offline-icon" });
  setIcon(iconEl, "pkmrag-ribbon");
  wrapper.createEl("h3", { text: "PKMRAG Background Engine Stopped", cls: "pkmrag-offline-title" });

  wrapper.createEl("p", {
    cls: "pkmrag-offline-desc",
    text: "The local PKMRAG engine daemon is not running. Click 'Start Engine' below to launch the background process automatically (no terminal required):",
  });

  // Actions
  const btnRow = wrapper.createDiv({ cls: "pkmrag-offline-actions" });

  const startBtn = btnRow.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "🚀 Start Engine",
  });
  startBtn.onclick = async () => {
    startBtn.setText("Starting engine...");
    startBtn.setAttribute("disabled", "true");
    const ok = await plugin.daemonManager.start();
    if (ok) {
      new Notice("PKMRAG: Engine started successfully.");
      onRetry();
    } else {
      startBtn.setText("🚀 Start Engine");
      startBtn.removeAttribute("disabled");
      if (!plugin.daemonManager.isBinaryAvailable()) {
        new Notice("PKMRAG engine is not installed. Switching to Setup Wizard...");
        container.empty();
        renderSetupWizardView(container, plugin, onRetry);
      } else {
        new Notice("Could not auto-start engine. Ensure engine is installed or check Settings.");
      }
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
}
