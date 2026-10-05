/**
 * Orbit Insights Obsidian Plugin Entry Point.
 */

import { MarkdownView, Notice, Plugin, TFile, WorkspaceLeaf } from "obsidian";
import { OrbitClient } from "./client";
import { createOrbitEditorExtension } from "./extension";
import { OrbitSettingTab } from "./settings";
import {
  DEFAULT_SETTINGS,
  InferredRelationship,
  OrbitPluginSettings,
  SemanticGapCandidate,
} from "./types";
import { OrbitInsightsView, VIEW_TYPE_ORBIT_INSIGHTS } from "./view";

export default class OrbitInsightsPlugin extends Plugin {
  settings: OrbitPluginSettings = DEFAULT_SETTINGS;
  client!: OrbitClient;
  private statusBarEl!: HTMLElement;
  private eventSource: EventSource | null = null;
  private debounceMap: Map<string, ReturnJS_Timeout> = new Map();
  private activeInsights: Map<string, { gapsCount: number; hasContradiction: boolean }> =
    new Map();

  async onload(): Promise<void> {
    await this.loadSettings();
    this.client = new OrbitClient(this.settings);

    // Auto-discover vault token if not set
    if (!this.settings.authToken) {
      await this.client.autoDiscoverVaultToken(this.app);
    }

    // Register Sidebar View
    this.registerView(
      VIEW_TYPE_ORBIT_INSIGHTS,
      (leaf: WorkspaceLeaf) => new OrbitInsightsView(leaf, this)
    );

    // Ribbon Icon (Crosshair / Satellite)
    this.addRibbonIcon("crosshair", "Orbit Insights", () => {
      this.activateView();
    });

    // Status Bar Item
    this.statusBarEl = this.addStatusBarItem();
    this.updateStatusBar(false);
    this.checkConnection();

    // Register Commands
    this.addCommand({
      id: "open-orbit-insights",
      name: "Open Insights Sidebar",
      callback: () => this.activateView(),
    });

    this.addCommand({
      id: "refresh-orbit-insights",
      name: "Refresh Insights for Active Note",
      callback: () => this.refreshActiveView(),
    });

    // Register CodeMirror 6 Editor Extension
    this.registerEditorExtension(createOrbitEditorExtension(this));

    this.addCommand({
      id: "sync-orbit-vault",
      name: "Sync Vault Index (Incremental)",
      callback: async () => {
        new Notice("Orbit: Synchronizing vault delta...");
        try {
          const results = await this.client.syncVault();
          new Notice(`Orbit: Synchronized ${results.length} notes.`);
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          new Notice(`Orbit Sync Failed: ${msg}`);
        }
      },
    });

    this.addCommand({
      id: "toggle-orbit-inline-indicators",
      name: "Toggle Inline Heading Indicators",
      callback: async () => {
        this.settings.showInlineIndicators = !this.settings.showInlineIndicators;
        await this.saveSettings();
        new Notice(
          `Orbit: Inline indicators ${this.settings.showInlineIndicators ? "enabled" : "disabled"}`
        );
        this.app.workspace.updateOptions();
      },
    });

    this.addCommand({
      id: "clear-orbit-dismissed",
      name: "Clear Dismissed Suggestions",
      callback: async () => {
        this.settings.dismissedSuggestions = {};
        await this.saveSettings();
        new Notice("Orbit: Cleared all dismissed suggestions.");
        this.refreshActiveView();
      },
    });

    // Auto-Sync on Save (debounced 1500ms)
    this.registerEvent(
      this.app.vault.on("modify", (file) => {
        if (!this.settings.autoSyncOnSave || !(file instanceof TFile) || file.extension !== "md") {
          return;
        }
        const timer = this.debounceMap.get(file.path);
        if (timer) window.clearTimeout(timer);

        const newTimer = window.setTimeout(async () => {
          this.debounceMap.delete(file.path);
          try {
            await this.client.reindexNote(file.path);
          } catch (err) {
            console.warn(`[Orbit] Reindex failed for ${file.path}:`, err);
          }
        }, 1500);

        this.debounceMap.set(file.path, newTimer);
      })
    );

    // Auto-Refresh on Active Note Change
    this.registerEvent(
      this.app.workspace.on("file-open", (file) => {
        if (!this.settings.autoRefreshOnNoteOpen || !file || file.extension !== "md") {
          return;
        }
        this.refreshActiveView(file.path);
      })
    );

    // Register Settings Tab
    this.addSettingTab(new OrbitSettingTab(this.app, this));

    // Connect SSE Stream
    this.initEventStream();
  }

  onunload(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    for (const timer of this.debounceMap.values()) {
      window.clearTimeout(timer);
    }
    this.debounceMap.clear();
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
    this.client.settings = this.settings;
    this.checkConnection();
    this.initEventStream();
  }

  async activateView(): Promise<void> {
    const { workspace } = this.app;
    let leaf: WorkspaceLeaf | null = null;
    const leaves = workspace.getLeavesOfType(VIEW_TYPE_ORBIT_INSIGHTS);

    if (leaves.length > 0) {
      leaf = leaves[0];
    } else {
      leaf = workspace.getRightLeaf(false);
      if (leaf) {
        await leaf.setViewState({ type: VIEW_TYPE_ORBIT_INSIGHTS, active: true });
      }
    }

    if (leaf) {
      workspace.revealLeaf(leaf);
      const activeFile = workspace.getActiveFile();
      if (activeFile && activeFile.extension === "md") {
        const view = leaf.view as OrbitInsightsView;
        await view.loadInsightsForNote(activeFile.path);
      }
    }
  }

  refreshActiveView(notePath?: string): void {
    const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_ORBIT_INSIGHTS);
    if (leaves.length === 0) return;
    const view = leaves[0].view as OrbitInsightsView;
    const path = notePath || this.app.workspace.getActiveFile()?.path;
    if (path) {
      view.loadInsightsForNote(path);
    }
  }

  insertLink(targetTitle: string): void {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (!view || !view.editor) {
      new Notice(`No active markdown editor to insert [[${targetTitle}]].`);
      return;
    }
    const editor = view.editor;
    const wikilink = `[[${targetTitle}]]`;
    editor.replaceSelection(wikilink);
    new Notice(`Inserted link to ${wikilink}`);
  }

  setActiveInsights(
    path: string,
    gaps: SemanticGapCandidate[],
    inferences: InferredRelationship[]
  ): void {
    const dismissed = this.settings.dismissedSuggestions || {};
    const visibleCount = gaps.filter(
      (g) => !dismissed[`${g.source_path}::${g.target_path}`]
    ).length;
    const hasContra = inferences.some((i) => i.rel_type === "CONTRADICTS");
    this.activeInsights.set(path, { gapsCount: visibleCount, hasContradiction: hasContra });
    this.app.workspace.updateOptions();
  }

  getActiveGapsCount(path: string): number {
    return this.activeInsights.get(path)?.gapsCount || 0;
  }

  hasActiveContradiction(path: string): boolean {
    return this.activeInsights.get(path)?.hasContradiction || false;
  }

  private async checkConnection(): Promise<void> {
    try {
      await this.client.checkHealth();
      this.updateStatusBar(true);
    } catch {
      this.updateStatusBar(false);
    }
  }

  private updateStatusBar(connected: boolean): void {
    if (!this.statusBarEl) return;
    this.statusBarEl.empty();
    const text = connected ? "🛰️ Orbit: Connected" : "🛰️ Orbit: Offline";
    this.statusBarEl.createSpan({
      text,
      cls: connected ? "orbit-status-connected" : "orbit-status-disconnected",
    });
    this.statusBarEl.onclick = () => this.activateView();
  }

  private initEventStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.eventSource = this.client.connectEvents((event, data) => {
      const activeFile = this.app.workspace.getActiveFile();
      if (!activeFile) return;

      if (event === "reindex") {
        const reindexed = data.note_path as string;
        if (reindexed && activeFile.path.endsWith(reindexed)) {
          this.refreshActiveView(activeFile.path);
        }
      } else if (event === "sync") {
        this.refreshActiveView(activeFile.path);
      }
    });
  }
}

type ReturnJS_Timeout = number;
