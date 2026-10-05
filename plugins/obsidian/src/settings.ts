/**
 * Configuration and Settings Tab for Orbit Insights Plugin.
 */

import { App, Notice, PluginSettingTab, Setting } from "obsidian";
import type OrbitInsightsPlugin from "./main";

export class OrbitSettingTab extends PluginSettingTab {
  plugin: OrbitInsightsPlugin;

  constructor(app: App, plugin: OrbitInsightsPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "Orbit Knowledge Engine Settings" });

    // 1. Connection Section
    new Setting(containerEl)
      .setName("Server URL")
      .setDesc("Base address of Orbit HTTP/SSE daemon (default: http://127.0.0.1:3747)")
      .addText((text) =>
        text
          .setPlaceholder("http://127.0.0.1:3747")
          .setValue(this.plugin.settings.serverUrl)
          .onChange(async (val) => {
            this.plugin.settings.serverUrl = val;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Authentication Token")
      .setDesc("Bearer token for server access (auto-detected from .orbit/server_token)")
      .addText((text) =>
        text
          .setPlaceholder("Auto-detected or custom token")
          .setValue(this.plugin.settings.authToken)
          .onChange(async (val) => {
            this.plugin.settings.authToken = val;
            await this.plugin.saveSettings();
          })
      )
      .addButton((btn) =>
        btn.setButtonText("Auto-Detect").onClick(async () => {
          const tok = await this.plugin.client.autoDiscoverVaultToken(this.app);
          if (tok) {
            new Notice(`Found Orbit token in vault!`);
            await this.plugin.saveSettings();
            this.display();
          } else {
            new Notice(`No .orbit/server_token file found in vault.`);
          }
        })
      );

    // Connection Health Verification Button
    new Setting(containerEl)
      .setName("Server Status")
      .setDesc("Verify communication with local Orbit daemon")
      .addButton((btn) =>
        btn.setButtonText("Test Connection").onClick(async () => {
          btn.setDisabled(true);
          try {
            const health = await this.plugin.client.checkHealth();
            new Notice(`Orbit Connected! Vault: '${health.vault}', Version: v${health.version}`);
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            new Notice(`Connection failed: ${msg}`);
          } finally {
            btn.setDisabled(false);
          }
        })
      );

    containerEl.createEl("h3", { text: "Behavior & Thresholds" });

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
  }
}
