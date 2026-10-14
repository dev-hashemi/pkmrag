/**
 * Interactive Setup Wizard view rendered when PKMRAG engine executable is not installed.
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

  wrapper.createEl("h3", { text: "PKMRAG Engine Setup", cls: "pkmrag-offline-title" });

  wrapper.createEl("p", {
    cls: "pkmrag-offline-desc",
    text: "PKMRAG requires a local companion engine to power deterministic graph queries, semantic vector search, and AI discovery on your notes.",
  });

  const env = plugin.installer.detectEnvironment();

  // 1. One-Click Automated Installer Card
  const installerCard = wrapper.createDiv({ cls: "pkmrag-installer-card" });

  const badgeText = env.hasUv
    ? "Fast Install (uv detected)"
    : env.hasPipx
    ? "Standard Install (pipx detected)"
    : "Zero-Dependency Bootstrap";
  installerCard.createDiv({ cls: "pkmrag-installer-badge", text: badgeText });

  const descText = env.hasUv
    ? "Installs PKMRAG into an isolated environment using uv in seconds."
    : env.hasPipx
    ? "Installs PKMRAG into an isolated virtual environment using pipx."
    : "No Python or package manager needed. Automatically bootstraps standalone uv and installs PKMRAG.";
  installerCard.createDiv({ cls: "pkmrag-installer-desc", text: descText });

  const cardActions = installerCard.createDiv({ cls: "pkmrag-offline-actions" });
  const installBtn = cardActions.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "⚡ Install PKMRAG Engine (One-Click)",
  });

  // State containers (log, progress, confirm)
  const confirmBox = installerCard.createDiv({ cls: "pkmrag-installer-confirm pkmrag-hidden" });
  const logBox = installerCard.createDiv({ cls: "pkmrag-installer-log pkmrag-hidden" });
  const cancelBtn = installerCard.createEl("button", {
    cls: "pkmrag-btn-sm pkmrag-hidden",
    text: "Cancel",
  });

  installBtn.onclick = () => {
    installBtn.addClass("pkmrag-hidden");
    confirmBox.removeClass("pkmrag-hidden");
    confirmBox.empty();

    const toolName = env.hasUv ? "uv" : env.hasPipx ? "pipx" : "standalone uv";
    confirmBox.createEl("p", {
      text: `Install PKMRAG using ${toolName}? This will install the package into your user directory (~/.local/bin) without modifying system files.`,
    });

    const confirmActions = confirmBox.createDiv({ cls: "pkmrag-offline-actions" });
    const proceedBtn = confirmActions.createEl("button", {
      cls: "pkmrag-btn-sm mod-cta",
      text: "Proceed with Install",
    });
    const abortBtn = confirmActions.createEl("button", {
      cls: "pkmrag-btn-sm",
      text: "Cancel",
    });

    abortBtn.onclick = () => {
      confirmBox.addClass("pkmrag-hidden");
      installBtn.removeClass("pkmrag-hidden");
    };

    proceedBtn.onclick = async () => {
      confirmBox.addClass("pkmrag-hidden");
      logBox.removeClass("pkmrag-hidden");
      cancelBtn.removeClass("pkmrag-hidden");
      logBox.empty();
      plugin.activeJob = null;
      plugin.lastTaskError = null;

      cancelBtn.onclick = () => {
        plugin.installer.cancel();
        logBox.createDiv({ text: "\nInstallation cancelled by user." });
        cancelBtn.addClass("pkmrag-hidden");
        installBtn.removeClass("pkmrag-hidden");
      };

      const success = await plugin.installer.install({
        onPhase: (phase) => {
          logBox.createDiv({ text: `>>> ${phase}` });
          logBox.scrollTop = logBox.scrollHeight;
        },
        onLog: (line) => {
          logBox.createDiv({ text: line });
          logBox.scrollTop = logBox.scrollHeight;
        },
        onSuccess: async () => {
          logBox.createDiv({ text: "\n>>> Launching PKMRAG background daemon..." });
          logBox.scrollTop = logBox.scrollHeight;
          cancelBtn.addClass("pkmrag-hidden");
          plugin.activeJob = null;
          plugin.lastTaskError = null;
          const ok = await plugin.daemonManager.start();
          if (ok) {
            logBox.createDiv({ text: ">>> ✓ Daemon connected successfully!" });
            logBox.scrollTop = logBox.scrollHeight;
            new Notice("PKMRAG Engine installed and connected!");
            onConnected();
          } else {
            logBox.createDiv({ text: "\n>>> PKMRAG Engine installed. Click below to verify and connect:" });
            const startBtn = logBox.createEl("button", {
              cls: "pkmrag-btn-sm mod-cta",
              text: "🚀 Verify & Start Engine",
            });
            startBtn.onclick = async () => {
              startBtn.setText("Connecting...");
              startBtn.setAttribute("disabled", "true");
              const retryOk = await plugin.daemonManager.start();
              if (retryOk) {
                new Notice("PKMRAG Engine connected!");
                onConnected();
              } else {
                startBtn.setText("🚀 Verify & Start Engine");
                startBtn.removeAttribute("disabled");
                new Notice("Engine is not ready yet. Check logs or Settings.");
              }
            };
          }
        },
        onError: (err) => {
          new Notice(`Installation error: ${err}`);
          logBox.createDiv({ text: `\n[ERROR] ${err}` });
          cancelBtn.addClass("pkmrag-hidden");
          installBtn.removeClass("pkmrag-hidden");
          installBtn.setText("Retry Install");
        },
      });

      if (!success) {
        installBtn.removeClass("pkmrag-hidden");
      }
    };
  };

  // 2. Expandable Advanced / Manual Section
  const toggle = wrapper.createDiv({ cls: "pkmrag-installer-toggle", text: "▶ Advanced: Manual Installation" });
  const manualBox = wrapper.createDiv({ cls: "pkmrag-wizard-step pkmrag-hidden" });

  toggle.onclick = () => {
    const isHidden = manualBox.hasClass("pkmrag-hidden");
    if (isHidden) {
      manualBox.removeClass("pkmrag-hidden");
      toggle.setText("▼ Advanced: Manual Installation");
    } else {
      manualBox.addClass("pkmrag-hidden");
      toggle.setText("▶ Advanced: Manual Installation");
    }
  };

  manualBox.createDiv({ cls: "pkmrag-wizard-step-title", text: "Run via Terminal:" });
  const codeBox = manualBox.createDiv({ cls: "pkmrag-code-box" });
  const cmd = "pipx install pkmrag";
  codeBox.createEl("code", { text: cmd });

  const copyBtn = codeBox.createEl("button", { cls: "pkmrag-copy-btn", text: "Copy" });
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(cmd);
    new Notice("Copied 'pipx install pkmrag' to clipboard!");
  };

  manualBox.createDiv({
    cls: "pkmrag-wizard-hint",
    text: "Using uv? You can also run: uv tool install pkmrag",
  });

  // Verify and Settings Buttons
  const footerActions = wrapper.createDiv({ cls: "pkmrag-offline-actions" });
  const verifyBtn = footerActions.createEl("button", {
    cls: "pkmrag-btn-sm",
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
      new Notice("Could not detect pkmrag binary. Install using button above or check Settings.");
    }
  };

  const settingsBtn = footerActions.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };
}
