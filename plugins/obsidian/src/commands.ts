/**
 * Command palette registrations for PKMRAG Obsidian Plugin.
 */

import { Notice } from "obsidian";
import type PkmragPlugin from "./main";

export function registerPluginCommands(plugin: PkmragPlugin): void {
  plugin.addCommand({
    id: "open-insights",
    name: "Open Insights Sidebar",
    callback: () => plugin.activateView(),
  });

  plugin.addCommand({
    id: "setup-engine",
    name: "Install / Setup Engine",
    callback: () => plugin.activateView(),
  });

  plugin.addCommand({
    id: "refresh-insights",
    name: "Refresh Insights for Active Note",
    callback: () => plugin.refreshActiveView(),
  });

  plugin.addCommand({
    id: "run-discover",
    name: "Run AI Gap Discovery",
    callback: async () => {
      new Notice("PKMRAG: AI Gap Discovery started in background...");
      try {
        await plugin.client.triggerDiscover();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        new Notice(`PKMRAG Discovery failed: ${msg}`);
      }
    },
  });

  plugin.addCommand({
    id: "rebuild-index",
    name: "Rebuild Vault Index (Full)",
    callback: async () => {
      new Notice("PKMRAG: Full index rebuild started in background...");
      try {
        await plugin.client.triggerIngest({ rebuild: true });
        await plugin.syncJobState();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        new Notice(`PKMRAG Rebuild failed: ${msg}`);
      }
    },
  });

  plugin.addCommand({
    id: "restart-daemon",
    name: "Restart Local Engine",
    callback: async () => {
      new Notice("PKMRAG: Restarting engine...");
      const ok = await plugin.daemonManager.restart();
      new Notice(ok ? "PKMRAG: Engine restarted." : "Failed to restart engine.");
    },
  });

  plugin.addCommand({
    id: "sync-vault",
    name: "Sync Vault Index (Incremental)",
    callback: async () => {
      new Notice("PKMRAG: Synchronizing vault delta...");
      try {
        const results = await plugin.client.syncVault();
        new Notice(`PKMRAG: Synchronized ${results.length} notes.`);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        new Notice(`PKMRAG Sync Failed: ${msg}`);
      }
    },
  });

  plugin.addCommand({
    id: "toggle-inline-indicators",
    name: "Toggle Inline Heading Indicators",
    callback: async () => {
      plugin.settings.showInlineIndicators = !plugin.settings.showInlineIndicators;
      await plugin.saveSettings();
      new Notice(
        `PKMRAG: Inline indicators ${plugin.settings.showInlineIndicators ? "enabled" : "disabled"}`
      );
      plugin.app.workspace.updateOptions();
    },
  });

  plugin.addCommand({
    id: "clear-dismissed",
    name: "Clear Dismissed Suggestions",
    callback: async () => {
      plugin.settings.dismissedSuggestions = {};
      await plugin.saveSettings();
      new Notice("PKMRAG: Cleared all dismissed suggestions.");
      plugin.refreshActiveView();
    },
  });
}
