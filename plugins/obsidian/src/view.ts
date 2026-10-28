/**
 * "PKMRAG Insights" Sidebar Panel View implementation for Obsidian.
 */

import { ItemView, Notice, WorkspaceLeaf } from "obsidian";

import type PkmragPlugin from "./main";
import { NoteContext, SemanticGapCandidate } from "./types";
import { renderOfflineView } from "./view_offline";
import { renderUnindexedView, renderUnindexedNoteCard } from "./view_unindexed";
import { renderSetupWizardView } from "./view_setup_wizard";
import {
  renderProgressBanner,
  renderJobProgressView,
  renderTaskErrorCard,
  retryFailedTask,
} from "./view_progress";
import { renderGapsSection } from "./view_gaps";
import { ProximitySearchDrawer } from "./view_search";
import { renderInferencesSection } from "./view_inferences";
import { renderContextSection, renderVaultStats } from "./view_context";
import { classifyRequestError, displayTitle } from "./format";
import { DiscoveryEstimateModal } from "./modal_estimate";


export const VIEW_TYPE_PKMRAG_INSIGHTS = "pkmrag-insights-view";


export class PkmragInsightsView extends ItemView {
  plugin: PkmragPlugin;
  private currentNotePath: string | null = null;
  private context: NoteContext | null = null;
  private gaps: SemanticGapCandidate[] = [];
  private lastUpdated: Date | null = null;
  private isLoading = false;
  private isGapsLoading = false;
  private gapsError: string | null = null;
  private isUnindexed = false;
  private isOffline = false;
  private errorMessage: string | null = null;
  /** Monotonic token identifying the newest note load; older responses are discarded. */
  private requestSeq = 0;

  constructor(leaf: WorkspaceLeaf, plugin: PkmragPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_PKMRAG_INSIGHTS;
  }

  getDisplayText(): string {
    return "PKMRAG Insights";
  }

  getIcon(): string {
    return "pkmrag-ribbon";
  }

  async onOpen(): Promise<void> {
    const activeFile = this.app.workspace.getActiveFile();
    if (activeFile && activeFile.extension === "md") {
      await this.loadInsightsForNote(activeFile.path);
    } else {
      this.render();
    }
  }

  async loadInsightsForNote(notePath: string): Promise<void> {
    const seq = ++this.requestSeq;
    this.currentNotePath = notePath;
    if (!this.plugin.isServerConnected || !this.plugin.isVaultIndexed) {
      this.render();
      return;
    }
    this.isLoading = true;
    this.isGapsLoading = true;
    this.gapsError = null;
    this.errorMessage = null;
    this.isUnindexed = false;
    this.isOffline = false;
    this.context = null;
    this.gaps = [];
    this.render();

    await Promise.all([this.loadContext(seq, notePath), this.loadGaps(seq, notePath)]);
  }

  /** Load the graph context for a note. A superseded response is discarded. */
  private async loadContext(seq: number, notePath: string): Promise<void> {
    try {
      const ctx = await this.plugin.client.getNoteContext(notePath);
      if (seq !== this.requestSeq) return;
      this.context = ctx;
      this.plugin.isServerConnected = true;
      this.plugin.isVaultIndexed = true;
    } catch (err: unknown) {
      if (seq !== this.requestSeq) return;
      const message = err instanceof Error ? err.message : String(err);
      if (classifyRequestError(message) === "unindexed") {
        this.isUnindexed = true;
        this.plugin.isVaultIndexed = false;
      } else {
        this.isOffline = true;
        this.plugin.isServerConnected = false;
        this.errorMessage = message;
      }
    }
    if (seq !== this.requestSeq) return;
    this.isLoading = false;
    this.applyLoadedState(notePath);
  }

  /** Load the missing-link suggestions for a note. A failure here stays local. */
  private async loadGaps(seq: number, notePath: string): Promise<void> {
    try {
      const gaps = await this.plugin.client.getGaps(notePath);
      if (seq !== this.requestSeq) return;
      this.gaps = gaps;
    } catch (err: unknown) {
      if (seq !== this.requestSeq) return;
      // A failing suggestions request must not discard the graph context and must
      // not mark a healthy daemon as offline.
      this.gapsError = err instanceof Error ? err.message : String(err);
    }
    if (seq !== this.requestSeq) return;
    this.isGapsLoading = false;
    this.applyLoadedState(notePath);
  }

  /** Publish the freshly loaded state and repaint the panel. */
  private applyLoadedState(notePath: string): void {
    this.lastUpdated = new Date();
    this.plugin.setActiveInsights(
      notePath,
      this.gaps,
      this.context?.inferred_relationships || []
    );
    this.plugin.updateStatusBar();
    this.render();
  }

  public render(): void {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("pkmrag-insights-container");

    // Live Background Job Banner (rendered at top if active on indexed vault)
    if (this.plugin.activeJob && this.plugin.isVaultIndexed) {
      renderProgressBanner(container, this.plugin.activeJob);
    }

    // Header
    const headerEl = container.createDiv({ cls: "pkmrag-header" });
    const topRow = headerEl.createDiv({ cls: "pkmrag-header-top" });
    const title = this.currentNotePath
      ? this.context?.title || displayTitle(this.currentNotePath)
      : "No Note Active";
    topRow.createDiv({ cls: "pkmrag-header-title", text: title });

    const actions = topRow.createDiv({ cls: "pkmrag-header-actions" });

    const discoverBtn = actions.createEl("button", {
      cls: "pkmrag-btn-sm",
      text: "⚡ Discover",
    });
    discoverBtn.title = "Run AI Gap Discovery & Relationship Inference";
    discoverBtn.onclick = async () => {
      discoverBtn.disabled = true;
      discoverBtn.setText("Estimating...");
      try {
        const estimate = await this.plugin.client.estimateDiscover({
          note_path: this.currentNotePath || undefined,
        });
        new DiscoveryEstimateModal(this.app, {
          estimate,
          notePath: this.currentNotePath,
          noteTitle: this.context?.title,
          onConfirm: async () => {
            new Notice("PKMRAG: AI Discovery started in background...");
            await this.plugin.client.triggerDiscover({
              note_path: this.currentNotePath || undefined,
            });
          },
        }).open();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        new Notice(`Discovery estimation failed: ${msg}`);
      } finally {
        discoverBtn.disabled = false;
        discoverBtn.setText("⚡ Discover");
      }
    };

    const refreshBtn = actions.createEl("button", { cls: "pkmrag-btn-sm", text: "⟳" });
    refreshBtn.title = "Refresh Insights";
    refreshBtn.onclick = () => {
      if (this.currentNotePath) this.loadInsightsForNote(this.currentNotePath);
    };

    const statusText = this.isLoading
      ? "Scanning vault..."
      : this.lastUpdated
      ? `Updated ${this.lastUpdated.toLocaleTimeString()}`
      : "Idle";
    headerEl.createDiv({ cls: "pkmrag-sync-status", text: statusText });

    if (!this.plugin.isServerConnected || this.isOffline) {
      if (!this.plugin.daemonManager.isBinaryAvailable()) {
        renderSetupWizardView(container, this.plugin, () => {
          this.isOffline = false;
          if (this.plugin.isVaultIndexed && this.currentNotePath) {
            this.loadInsightsForNote(this.currentNotePath);
          } else {
            this.render();
          }
        });
        return;
      }
      renderOfflineView(container, this.plugin, () => {
        this.isOffline = false;
        if (this.plugin.isVaultIndexed && this.currentNotePath) {
          this.loadInsightsForNote(this.currentNotePath);
        } else {
          this.render();
        }
      }, this.errorMessage);
      return;
    }

    if (this.plugin.lastTaskError) {
      renderTaskErrorCard(container, this.plugin, this.plugin.lastTaskError, () => {
        void retryFailedTask(this.plugin, () => this.render());
      });
      return;
    }

    if (!this.plugin.isVaultIndexed || this.isUnindexed) {
      if (this.plugin.activeJob) {
        renderJobProgressView(container, this.plugin, this.plugin.activeJob);
        return;
      }
      renderUnindexedView(container, this.plugin, () => {
        this.render();
      });
      return;
    }

    if (!this.currentNotePath) {
      container.createDiv({
        cls: "pkmrag-empty-state",
        text: "Open a markdown note to inspect graph context and suggestions.",
      });
      new ProximitySearchDrawer(container, this.plugin, () => null);
      return;
    }

    // Proximity Concept Explorer Search Drawer
    new ProximitySearchDrawer(container, this.plugin, () => this.currentNotePath);

    if (!this.context && !this.isLoading) {
      renderUnindexedNoteCard(container, this.plugin, this.currentNotePath, async () => {
        await this.loadInsightsForNote(this.currentNotePath!);
      });
      return;
    }

    // 1. Missing Links Section (loads independently of the graph context)
    renderGapsSection(
      container,
      this.plugin,
      this.gaps,
      this.currentNotePath,
      () => {
        this.render();
      },
      { loading: this.isGapsLoading, error: this.gapsError }
    );

    if (!this.context) {
      container.createDiv({ cls: "pkmrag-empty-state", text: "Loading graph context..." });
      return;
    }

    // 2. Contradictions & AI Inferences Section
    renderInferencesSection(container, this.plugin, this.context, (path) => {
      this.app.workspace.openLinkText(path, "");
    });

    // 3. Graph Context Section
    renderContextSection(container, this.context, (path) => {
      this.app.workspace.openLinkText(path, "");
    });

    // 4. Vault-wide graph statistics
    renderVaultStats(container, this.plugin.vaultStats);
  }
}
