/**
 * Setup Wizard view rendered when PKMRAG engine executable is not installed on the system.
 */

import { Notice, setIcon } from "obsidian";
import type PkmragPlugin from "./main";

export function renderSetupWizardView(
  container: HTMLElement,
  plugin: PkmragPlugin,
  onConnected: () => void
): void {
  const wrapper = container.createDiv({ cls: "pkmrag-offline-container pkmrag-wizard-container" });

  const iconEl = wrapper.createDiv({ cls: "pkmrag-offline-icon" });
  setIcon(iconEl, "pkmrag-ribbon");

  wrapper.createEl("h3", { text: "PKMRAG Engine Setup Required", cls: "pkmrag-offline-title" });

  wrapper.createEl("p", {
    cls: "pkmrag-offline-desc",
    text: "PKMRAG's local Hybrid GraphRAG engine needs to be installed on your machine. Install the companion CLI package using pipx (recommended) or uv tool:",
  });

  // Step 1: Install command snippet
  const step1Box = wrapper.createDiv({ cls: "pkmrag-wizard-step" });
  step1Box.createDiv({ cls: "pkmrag-wizard-step-title", text: "Step 1: Install via Terminal" });

  const codeBox = step1Box.createDiv({ cls: "pkmrag-code-box" });
  const cmd = "pipx install pkmrag";
  codeBox.createEl("code", { text: cmd });

  const copyBtn = codeBox.createEl("button", { cls: "pkmrag-copy-btn", text: "Copy" });
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(cmd);
    new Notice("Copied 'pipx install pkmrag' to clipboard!");
  };

  // Alternative uv tool note
  step1Box.createDiv({
    cls: "pkmrag-wizard-hint",
    text: "Using uv? You can also run: uv tool install pkmrag",
  });

  // Step 2: Connect & Verify
  const step2Box = wrapper.createDiv({ cls: "pkmrag-wizard-step" });
  step2Box.createDiv({ cls: "pkmrag-wizard-step-title", text: "Step 2: Verify & Connect" });

  const actions = step2Box.createDiv({ cls: "pkmrag-offline-actions" });
  const verifyBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "🔍 Verify & Start Engine",
  });

  verifyBtn.onclick = async () => {
    verifyBtn.setText("Searching for engine...");
    verifyBtn.setAttribute("disabled", "true");
    const ok = await plugin.daemonManager.start();
    if (ok) {
      new Notice("PKMRAG: Engine detected and connected!");
      onConnected();
    } else {
      verifyBtn.setText("🔍 Verify & Start Engine");
      verifyBtn.removeAttribute("disabled");
      new Notice("Could not detect pkmrag binary. Ensure pipx install finished or enter path in Settings.");
    }
  };

  const settingsBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };
}
