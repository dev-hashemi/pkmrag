/**
 * Orbit Insights Obsidian Plugin Entry Point.
 */

import { MarkdownView, Notice, Plugin, TFile, WorkspaceLeaf, addIcon } from "obsidian";
import { OrbitClient } from "./client";
import { DaemonManager } from "./daemon";
import { registerPluginCommands } from "./commands";
import { createOrbitEditorExtension } from "./extension";
import { OrbitSettingTab } from "./settings";
import { renderStatusBar, setupEventStream } from "./status_bar";

import {
  ActiveJobState,
  DEFAULT_SETTINGS,
  InferredRelationship,
  OrbitPluginSettings,
  SemanticGapCandidate,
} from "./types";
import { OrbitInsightsView, VIEW_TYPE_ORBIT_INSIGHTS } from "./view";

export default class OrbitInsightsPlugin extends Plugin {
  settings: OrbitPluginSettings = DEFAULT_SETTINGS;
  client!: OrbitClient;
  daemonManager!: DaemonManager;
  activeJob: ActiveJobState | null = null;
  isVaultIndexed = true;
  isServerConnected = false;
  private statusBarEl!: HTMLElement;
  private eventSource: EventSource | null = null;
  private debounceMap: Map<string, ReturnJS_Timeout> = new Map();
  private activeInsights: Map<string, { gapsCount: number; hasContradiction: boolean }> =
    new Map();

  async onload(): Promise<void> {
    await this.loadSettings();
    this.client = new OrbitClient(this.settings);
    this.daemonManager = new DaemonManager(this);

    // Auto-discover vault token if not set
    if (!this.settings.authToken) {
      await this.client.autoDiscoverVaultToken(this.app);
    }

    // Auto-start daemon on desktop if enabled
    if (this.settings.autoStartDaemon) {
      this.daemonManager.start();
    }

    // Register custom PKMRAG ribbon icon
    addIcon(
      "pkmrag-ribbon",
      `<circle cx="50" cy="22" r="10" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="22" cy="78" r="10" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="78" cy="78" r="10" fill="none" stroke="currentColor" stroke-width="8"/><line x1="44" y1="34" x2="28" y2="66" stroke="currentColor" stroke-width="8" stroke-linecap="round"/><line x1="34" y1="78" x2="66" y2="78" stroke="currentColor" stroke-width="8" stroke-linecap="round"/><line x1="56" y1="34" x2="72" y2="66" stroke="currentColor" stroke-width="8" stroke-dasharray="4 6" stroke-linecap="round"/>`
    );

    // Register Sidebar View
    this.registerView(
      VIEW_TYPE_ORBIT_INSIGHTS,
      (leaf: WorkspaceLeaf) => new OrbitInsightsView(leaf, this)
    );

    // Ribbon Icon
    this.addRibbonIcon("pkmrag-ribbon", "PKMRAG Insights", () => {
      this.activateView();
    });

    // Status Bar Item
    this.statusBarEl = this.addStatusBarItem();
    this.updateStatusBar();
    this.checkConnection();

    // Register Commands
    registerPluginCommands(this);

    // Register CodeMirror 6 Editor Extension

    this.registerEditorExtension(createOrbitEditorExtension(this));

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
            console.warn(`[PKMRAG] Reindex failed for ${file.path}:`, err);
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
    this.daemonManager.stop();
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
    const wikilink = `[[${targetTitle}]]`;
    view.editor.replaceSelection(wikilink);
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

  updateStatusBar(connected?: boolean): void {
    if (typeof connected === "boolean") {
      this.isServerConnected = connected;
    }
    if (!this.statusBarEl) return;
    renderStatusBar(this.statusBarEl, this);
  }

  async checkConnection(): Promise<void> {
    try {
      const health = await this.client.checkHealth();
      this.isServerConnected = true;
      this.isVaultIndexed = health.is_indexed !== false;
      this.activeJob = health.active_job || null;
    } catch {
      this.isServerConnected = false;
    }
    this.updateStatusBar();
  }

  private initEventStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.eventSource = setupEventStream(this);
  }
}

type ReturnJS_Timeout = number;
