/**
 * Configuration and Settings Tab for Orbit Insights Plugin.
 */

import { App, Notice, PluginSettingTab, Setting } from "obsidian";
import type OrbitInsightsPlugin from "./main";
import { renderLlmSection } from "./settings_llm";

export class OrbitSettingTab extends PluginSettingTab {
  plugin: OrbitInsightsPlugin;

  constructor(app: App, plugin: OrbitInsightsPlugin) {
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
    containerEl.createEl("h3", { text: "Background Daemon (Zero-Terminal)" });

    new Setting(containerEl)
      .setName("Auto-Start Background Daemon")
      .setDesc("Automatically start the local PKMRAG engine daemon on Obsidian launch (Desktop only)")
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
            new Notice("PKMRAG executable detected in standard PATH (~/.local/bin/pkmrag)!");
          } else {
            new Notice("PKMRAG executable not found. Install via: pipx install pkmrag");
          }
        })
      );

    const daemonStatusSetting = new Setting(containerEl)
      .setName("Daemon Process Control")
      .setDesc(`Current Status: ${this.plugin.daemonManager.statusMessage}`);

    daemonStatusSetting.addButton((btn) =>
      btn.setButtonText("Start").onClick(async () => {
        btn.setDisabled(true);
        const ok = await this.plugin.daemonManager.start();
        new Notice(ok ? "PKMRAG Daemon started!" : "Failed to start daemon.");
        btn.setDisabled(false);
        this.display();
      })
    );

    daemonStatusSetting.addButton((btn) =>
      btn.setButtonText("Restart").onClick(async () => {
        btn.setDisabled(true);
        const ok = await this.plugin.daemonManager.restart();
        new Notice(ok ? "PKMRAG Daemon restarted!" : "Failed to restart daemon.");
        btn.setDisabled(false);
        this.display();
      })
    );

    daemonStatusSetting.addButton((btn) =>
      btn.setButtonText("Stop").onClick(() => {
        this.plugin.daemonManager.stop();
        new Notice("PKMRAG Daemon stopped.");
        this.display();
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
