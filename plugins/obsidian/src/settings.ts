/**
 * Configuration and Settings Tab for PKMRAG Insights Plugin.
 */

import { App, Notice, PluginSettingTab, Setting } from "obsidian";
import type PkmragPlugin from "./main";
import { renderLlmSection } from "./settings_llm";

export class PkmragSettingTab extends PluginSettingTab {
  plugin: PkmragPlugin;

  constructor(app: App, plugin: PkmragPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "PKMRAG Knowledge Engine Settings" });

    // 1. Daemon Management Section
    this.renderDaemonSection(containerEl);

    // 2. Custom LLM Configuration Section (Modular)
    renderLlmSection(containerEl, this.plugin, () => this.display());

    // 3. Search & Embedding Models Section
    this.renderEmbeddingsSection(containerEl);

    // 4. Connection & Behavior Section
    this.renderBehaviorSection(containerEl);

    // 5. Index Maintenance & Governance Section
    this.renderMaintenanceSection(containerEl);
  }

  private renderDaemonSection(containerEl: HTMLElement): void {
    containerEl.createEl("h3", { text: "Local Search Engine (Zero-Terminal)" });

    new Setting(containerEl)
      .setName("Auto-Start Local Engine")
      .setDesc("Automatically start the local PKMRAG engine on Obsidian launch (Desktop only)")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.autoStartDaemon).onChange(async (val) => {
          this.plugin.settings.autoStartDaemon = val;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Custom Executable / uv Path")
      .setDesc("Optional absolute path to 'pkmrag' or 'uv' executable (leave blank for system auto-detection)")
      .addText((text) =>
        text
          .setPlaceholder("e.g. ~/.local/bin/pkmrag")
          .setValue(this.plugin.settings.customBinaryPath)
          .onChange(async (val) => {
            this.plugin.settings.customBinaryPath = val.trim();
            await this.plugin.saveSettings();
          })
      )
      .addButton((btn) =>
        btn.setButtonText("Auto-Detect").onClick(() => {
          const avail = this.plugin.daemonManager.isBinaryAvailable();
          if (avail) {
            new Notice("PKMRAG executable detected!");
          } else {
            new Notice("PKMRAG executable not found. Open Insights panel to run 1-click install.");
          }
        })
      );

    const daemonStatusSetting = new Setting(containerEl)
      .setName("Engine Status")
      .setDesc(`Current Status: ${this.plugin.daemonManager.statusMessage}`);

    if (!this.plugin.daemonManager.isBinaryAvailable()) {
      daemonStatusSetting.addButton((btn) =>
        btn
          .setButtonText("⚡ Install Engine")
          .setCta()
          .onClick(() => {
            this.plugin.activateView();
          })
      );
    }

    const env = this.plugin.installer.detectEnvironment();
    const envDesc = env.hasUv
      ? "uv detected on system"
      : env.hasPipx
      ? "pipx detected on system"
      : "standalone bootstrap mode";

    new Setting(containerEl)
      .setName("Upgrade / Reinstall Engine")
      .setDesc(`Reinstall or upgrade PKMRAG package from PyPI (${envDesc})`)
      .addButton((btn) =>
        btn.setButtonText("Upgrade Engine").onClick(async () => {
          btn.setDisabled(true);
          new Notice("Upgrading PKMRAG engine in background...");
          const ok = await this.plugin.installer.install({
            onPhase: () => {},
            onLog: () => {},
            onSuccess: async () => {
              new Notice("PKMRAG Engine upgraded successfully!");
              await this.plugin.daemonManager.restart();
              btn.setDisabled(false);
              this.display();
            },
            onError: (err) => {
              new Notice(`Upgrade failed: ${err}`);
              btn.setDisabled(false);
            },
          });
          if (!ok) btn.setDisabled(false);
        })
      );
  }

  private renderEmbeddingsSection(containerEl: HTMLElement): void {
    containerEl.createEl("h3", { text: "Search & Local Embeddings" });

    new Setting(containerEl)
      .setName("Active Embedding Model")
      .setDesc("BAAI/bge-small-en-v1.5 (384 dimensions). Runs fully local via FastEmbed & ONNX Runtime (zero API costs).")
      .addButton((btn) =>
        btn.setButtonText("Verify Model").onClick(() => {
          new Notice("Active: BAAI/bge-small-en-v1.5 (384-dim, FastEmbed local ONNX)");
        })
      );
  }

  private renderBehaviorSection(containerEl: HTMLElement): void {
    containerEl.createEl("h3", { text: "Behavior & Retrieval Thresholds" });

    new Setting(containerEl)
      .setName("Auto-Sync on Save")
      .setDesc("Incrementally re-index note into LadybugDB & LanceDB after file modifications")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.autoSyncOnSave).onChange(async (val) => {
          this.plugin.settings.autoSyncOnSave = val;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Auto-Refresh on Note Open")
      .setDesc("Automatically refresh sidebar insights when switching active markdown note")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.autoRefreshOnNoteOpen).onChange(async (val) => {
          this.plugin.settings.autoRefreshOnNoteOpen = val;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Similarity Threshold")
      .setDesc("Minimum cosine similarity for unlinked semantic gap recommendations (0.50 - 0.95)")
      .addSlider((slider) =>
        slider
          .setLimits(0.5, 0.95, 0.05)
          .setValue(this.plugin.settings.similarityThreshold)
          .setDynamicTooltip()
          .onChange(async (val) => {
            this.plugin.settings.similarityThreshold = val;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Max Suggestions")
      .setDesc("Maximum missing link cards displayed per note (1 - 20)")
      .addSlider((slider) =>
        slider
          .setLimits(1, 20, 1)
          .setValue(this.plugin.settings.maxSuggestions)
          .setDynamicTooltip()
          .onChange(async (val) => {
            this.plugin.settings.maxSuggestions = val;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Show Inline Heading Indicators")
      .setDesc("Display subtle link/contradiction indicators next to Markdown headings in editor")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.showInlineIndicators).onChange(async (val) => {
          this.plugin.settings.showInlineIndicators = val;
          await this.plugin.saveSettings();
        })
      );
  }

  private renderMaintenanceSection(containerEl: HTMLElement): void {
    containerEl.createEl("h3", { text: "Vault Maintenance & Governance" });

    new Setting(containerEl)
      .setName("Rebuild Full Vault Index")
      .setDesc("Re-index all notes, wikilinks, tags, and embeddings from scratch in background")
      .addButton((btn) =>
        btn.setButtonText("Rebuild Index").onClick(async () => {
          btn.setDisabled(true);
          try {
            await this.plugin.client.triggerIngest({ rebuild: true });
            await this.plugin.syncJobState();
            new Notice("PKMRAG: Full index rebuild started in background.");
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            new Notice(`Rebuild failed: ${msg}`);
          } finally {
            btn.setDisabled(false);
          }
        })
      );

    const dismissedCount = Object.keys(this.plugin.settings.dismissedSuggestions || {}).length;
    new Setting(containerEl)
      .setName("Dismissed Suggestions Memory")
      .setDesc(`${dismissedCount} suggestion${dismissedCount === 1 ? "" : "s"} hidden by negative feedback`)
      .addButton((btn) =>
        btn.setButtonText("Reset All Dismissed").onClick(async () => {
          this.plugin.settings.dismissedSuggestions = {};
          await this.plugin.saveSettings();
          new Notice("Reset all dismissed suggestions.");
          this.display();
        })
      );
  }
}
