/**
 * PKMRAG Insights Obsidian Plugin Entry Point.
 */

import { Plugin, TFile, WorkspaceLeaf, addIcon } from "obsidian";
import { PkmragClient } from "./client";
import { DaemonManager } from "./daemon";
import { HostInstaller } from "./installer";
import { registerPluginCommands } from "./commands";
import { createPkmragEditorExtension } from "./extension";
import { PkmragSettingTab } from "./settings";
import { notifySidebar, renderStatusBar, setupEventStream } from "./status_bar";

import {
  ActiveJobState,
  DEFAULT_SETTINGS,
  InferredRelationship,
  PkmragPluginSettings,
  SemanticGapCandidate,
  TaskErrorState,
} from "./types";
import { PkmragInsightsView, VIEW_TYPE_PKMRAG_INSIGHTS } from "./view";

export default class PkmragPlugin extends Plugin {
  settings: PkmragPluginSettings = DEFAULT_SETTINGS;
  client!: PkmragClient;
  daemonManager!: DaemonManager;
  installer!: HostInstaller;
  activeJob: ActiveJobState | null = null;
  lastTaskError: TaskErrorState | null = null;
  isVaultIndexed = false;
  isServerConnected = false;
  vaultStats: { notes: number; links: number; tags: number } | null = null;
  private statusBarEl!: HTMLElement;
  private eventSource: EventSource | null = null;
  private debounceMap: Map<string, ReturnJS_Timeout> = new Map();
  private activeInsights: Map<string, { gapsCount: number; hasContradiction: boolean }> =
    new Map();

  async onload(): Promise<void> {
    this.activeJob = null;
    this.lastTaskError = null;
    await this.loadSettings();
    this.client = new PkmragClient(this.settings, this.app);
    this.daemonManager = new DaemonManager(this);
    this.installer = new HostInstaller(this);

    // Auto-discover vault token if not set
    if (!this.settings.authToken) {
      await this.client.autoDiscoverVaultToken(this.app);
    }

    // Auto-start daemon on desktop if enabled and binary is available
    if (this.settings.autoStartDaemon && this.daemonManager.isBinaryAvailable()) {
      this.daemonManager.start();
    }

    // Register custom PKMRAG ribbon icon
    addIcon(
      "pkmrag-ribbon",
      `<circle cx="50" cy="22" r="10" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="22" cy="78" r="10" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="78" cy="78" r="10" fill="none" stroke="currentColor" stroke-width="8"/><line x1="44" y1="34" x2="28" y2="66" stroke="currentColor" stroke-width="8" stroke-linecap="round"/><line x1="34" y1="78" x2="66" y2="78" stroke="currentColor" stroke-width="8" stroke-linecap="round"/><line x1="56" y1="34" x2="72" y2="66" stroke="currentColor" stroke-width="8" stroke-dasharray="4 6" stroke-linecap="round"/>`
    );

    // Register Sidebar View
    this.registerView(
      VIEW_TYPE_PKMRAG_INSIGHTS,
      (leaf: WorkspaceLeaf) => new PkmragInsightsView(leaf, this)
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

    this.registerEditorExtension(createPkmragEditorExtension(this));

    // Auto-Sync on Save (debounced 1500ms)
    this.registerEvent(
      this.app.vault.on("modify", (file) => {
        if (!this.settings.autoSyncOnSave || !this.isVaultIndexed || !(file instanceof TFile) || file.extension !== "md") {
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
    this.addSettingTab(new PkmragSettingTab(this.app, this));

    // Connect SSE Stream
    this.initEventStream();
  }

  onunload(): void {
    this.installer?.cancel();
    void this.daemonManager.stop();
    this.disconnectEventStream();
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
    const leaves = workspace.getLeavesOfType(VIEW_TYPE_PKMRAG_INSIGHTS);

    if (leaves.length > 0) {
      leaf = leaves[0];
    } else {
      leaf = workspace.getRightLeaf(false);
      if (leaf) {
        await leaf.setViewState({ type: VIEW_TYPE_PKMRAG_INSIGHTS, active: true });
      }
    }

    if (leaf) {
      workspace.revealLeaf(leaf);
      const activeFile = workspace.getActiveFile();
      if (activeFile && activeFile.extension === "md") {
        const view = leaf.view as PkmragInsightsView;
        await view.loadInsightsForNote(activeFile.path);
      }
    }
  }

  refreshActiveView(notePath?: string): void {
    const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_PKMRAG_INSIGHTS);
    if (leaves.length === 0) return;
    const view = leaves[0].view as PkmragInsightsView;
    const path = notePath || this.app.workspace.getActiveFile()?.path;
    if (path) {
      view.loadInsightsForNote(path);
    }
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
      this.isVaultIndexed = health.is_indexed === true;
      this.activeJob = health.active_job || null;
      this.vaultStats = health.stats || null;
    } catch {
      this.isServerConnected = false;
    }
    this.updateStatusBar();
  }

  /**
   * Pull the authoritative job state from the health endpoint.
   *
   * The first progress events of a job can race the SSE connection and be
   * dropped, so the plugin reads the current stage once the job was accepted.
   * A job that already finished never clears the locally tracked state.
   */
  async syncJobState(): Promise<void> {
    try {
      const health = await this.client.checkHealth();
      this.isServerConnected = true;
      this.isVaultIndexed = health.is_indexed === true;
      if (health.active_job) {
        this.activeJob = health.active_job;
      }
      this.vaultStats = health.stats || null;
    } catch {
      this.isServerConnected = false;
    }
    this.updateStatusBar();
    notifySidebar(this);
  }

  disconnectEventStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  initEventStream(): void {
    this.disconnectEventStream();
    this.eventSource = setupEventStream(this);
  }
}

type ReturnJS_Timeout = number;
