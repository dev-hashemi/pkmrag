/**
 * "PKMRAG Insights" Sidebar Panel View implementation for Obsidian.
 */

import { ItemView, Notice, WorkspaceLeaf } from "obsidian";

import type PkmragPlugin from "./main";
import { NoteContext, SemanticGapCandidate } from "./types";
import { renderOfflineView } from "./view_offline";
import { renderUnindexedView } from "./view_unindexed";
import { renderSetupWizardView } from "./view_setup_wizard";
import { renderProgressBanner, renderJobProgressView, renderTaskErrorCard } from "./view_progress";
import { renderGapsSection } from "./view_gaps";
import { ProximitySearchDrawer } from "./view_search";
import { renderInferencesSection } from "./view_inferences";


export const VIEW_TYPE_PKMRAG_INSIGHTS = "pkmrag-insights-view";


export class PkmragInsightsView extends ItemView {
  plugin: PkmragPlugin;
  private currentNotePath: string | null = null;
  private context: NoteContext | null = null;
  private gaps: SemanticGapCandidate[] = [];
  private lastUpdated: Date | null = null;
  private isLoading = false;
  private isUnindexed = false;
  private isOffline = false;
  private errorMessage: string | null = null;
  private showDismissed = false;

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
    this.currentNotePath = notePath;
    if (!this.plugin.isServerConnected || !this.plugin.isVaultIndexed) {
      this.render();
      return;
    }
    this.isLoading = true;
    this.errorMessage = null;
    this.isUnindexed = false;
    this.isOffline = false;
    this.render();

    try {
      const [ctx, gaps] = await Promise.all([
        this.plugin.client.getNoteContext(notePath),
        this.plugin.client.getGaps(notePath),
      ]);
      this.context = ctx;
      this.gaps = gaps;
      this.lastUpdated = new Date();
      this.plugin.isServerConnected = true;
      this.plugin.isVaultIndexed = true;
      this.plugin.setActiveInsights(notePath, gaps, ctx?.inferred_relationships || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes("VAULT_UNINDEXED")) {
        this.isUnindexed = true;
        this.plugin.isVaultIndexed = false;
      } else {
        this.isOffline = true;
        this.plugin.isServerConnected = false;
        this.errorMessage = message;
      }
    } finally {
      this.isLoading = false;
      this.plugin.updateStatusBar();
      this.render();
    }
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
      ? this.currentNotePath.replace(/\.md$/, "")
      : "No Note Active";
    topRow.createDiv({ cls: "pkmrag-header-title", text: title });

    const actions = topRow.createDiv({ cls: "pkmrag-header-actions" });

    const discoverBtn = actions.createEl("button", {
      cls: "pkmrag-btn-sm",
      text: "⚡",
    });
    discoverBtn.title = "Run AI Gap Discovery & Relationship Inference";
    discoverBtn.onclick = async () => {
      discoverBtn.disabled = true;
      try {
        new Notice("PKMRAG: AI Discovery started in background...");
        await this.plugin.client.triggerDiscover();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        new Notice(`Discovery failed: ${msg}`);
      } finally {
        discoverBtn.disabled = false;
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
      });
      return;
    }

    if (this.plugin.lastTaskError) {
      renderTaskErrorCard(container, this.plugin, this.plugin.lastTaskError, async () => {
        try {
          this.plugin.lastTaskError = null;
          this.plugin.activeJob = {
            type: "ingest",
            phase: "initializing",
            cur: 0,
            total: 100,
            percent: 0,
            message: "Retrying vault indexing...",
          };
          this.plugin.updateStatusBar();
          this.render();
          await this.plugin.client.autoDiscoverVaultToken(this.plugin.app);
          this.plugin.initEventStream();
          await this.plugin.client.triggerIngest({ rebuild: true });
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          this.plugin.lastTaskError = {
            type: "ingest",
            message: msg,
            timestamp: new Date(),
          };
          this.render();
        }
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

    if (!this.context) {
      const noteCard = container.createDiv({ cls: "pkmrag-card" });
      noteCard.createDiv({ cls: "pkmrag-card-target", text: "Note Not Indexed Yet" });
      noteCard.createDiv({
        cls: "pkmrag-card-reason",
        text: "This note has not been parsed into LadybugDB yet.",
      });
      const reindexBtn = noteCard.createEl("button", {
        cls: "pkmrag-btn-sm mod-cta",
        text: "Index This Note",
      });
      reindexBtn.onclick = async () => {
        reindexBtn.setText("Indexing...");
        reindexBtn.setAttribute("disabled", "true");
        try {
          await this.plugin.client.reindexNote(this.currentNotePath!);
          await this.loadInsightsForNote(this.currentNotePath!);
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          new Notice(`Reindex failed: ${msg}`);
          reindexBtn.setText("Index This Note");
          reindexBtn.removeAttribute("disabled");
        }
      };
      return;
    }

    // 1. Missing Links Section (Semantic Gaps)
    renderGapsSection(container, this.plugin, this.gaps, this.currentNotePath, () => {
      this.render();
    });

    // 2. Contradictions & AI Inferences Section
    renderInferencesSection(container, this.context, (path) => {
      this.app.workspace.openLinkText(path, "");
    });

    // 3. Graph Context Section
    this.renderContextSection(container);
  }

  private renderContextSection(container: HTMLElement): void {

    const sec = container.createDiv({ cls: "pkmrag-section" });
    sec.createDiv({ cls: "pkmrag-section-header", text: "Graph Context" });

    const tags = this.context?.tags || [];
    if (tags.length > 0) {
      const tagChips = sec.createDiv({ cls: "pkmrag-chip-container", attr: { style: "margin-bottom: 8px;" } });
      for (const t of tags) {
        tagChips.createSpan({ cls: "pkmrag-chip", text: `#${t}` });
      }
    }

    const backlinks = this.context?.backlinks || [];
    sec.createDiv({
      cls: "pkmrag-card-reason",
      text: `Backlinks: ${backlinks.length}  |  Outgoing: ${
        this.context?.outgoing_links?.length || 0
      }  |  2-Hop Cluster: ${this.context?.neighbors_2hop?.length || 0}`,
    });
  }
}
