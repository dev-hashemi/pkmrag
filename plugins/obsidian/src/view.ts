/**
 * "Orbit Insights" Sidebar Panel View implementation for Obsidian.
 */

import { ItemView, WorkspaceLeaf } from "obsidian";
import type OrbitInsightsPlugin from "./main";
import { NoteContext, SemanticGapCandidate } from "./types";
import { renderOfflineView } from "./view_offline";
import { ProximitySearchDrawer } from "./view_search";

export const VIEW_TYPE_ORBIT_INSIGHTS = "orbit-insights-view";

export class OrbitInsightsView extends ItemView {
  plugin: OrbitInsightsPlugin;
  private currentNotePath: string | null = null;
  private context: NoteContext | null = null;
  private gaps: SemanticGapCandidate[] = [];
  private lastUpdated: Date | null = null;
  private isLoading = false;
  private errorMessage: string | null = null;
  private showDismissed = false;

  constructor(leaf: WorkspaceLeaf, plugin: OrbitInsightsPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_ORBIT_INSIGHTS;
  }

  getDisplayText(): string {
    return "Orbit Insights";
  }

  getIcon(): string {
    return "crosshair";
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
    this.isLoading = true;
    this.errorMessage = null;
    this.render();

    try {
      const [ctx, gaps] = await Promise.all([
        this.plugin.client.getNoteContext(notePath),
        this.plugin.client.getGaps(notePath),
      ]);
      this.context = ctx;
      this.gaps = gaps;
      this.lastUpdated = new Date();
      this.plugin.setActiveInsights(notePath, gaps, ctx?.inferred_relationships || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this.errorMessage = message;
    } finally {
      this.isLoading = false;
      this.render();
    }
  }

  private render(): void {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("orbit-insights-container");

    // Header
    const headerEl = container.createDiv({ cls: "orbit-header" });
    const topRow = headerEl.createDiv({ cls: "orbit-header-top" });
    const title = this.currentNotePath
      ? this.currentNotePath.replace(/\.md$/, "")
      : "No Note Active";
    topRow.createDiv({ cls: "orbit-header-title", text: title });

    const actions = topRow.createDiv({ cls: "orbit-header-actions" });
    const refreshBtn = actions.createEl("button", { cls: "orbit-btn-sm", text: "⟳" });
    refreshBtn.onclick = () => {
      if (this.currentNotePath) this.loadInsightsForNote(this.currentNotePath);
    };

    const statusText = this.isLoading
      ? "Scanning vault..."
      : this.lastUpdated
      ? `Updated ${this.lastUpdated.toLocaleTimeString()}`
      : "Idle";
    headerEl.createDiv({ cls: "orbit-sync-status", text: statusText });

    if (this.errorMessage) {
      renderOfflineView(container, this.plugin, () => {
        if (this.currentNotePath) this.loadInsightsForNote(this.currentNotePath);
      });
      return;
    }

    if (!this.currentNotePath) {
      container.createDiv({
        cls: "orbit-empty-state",
        text: "Open a markdown note to inspect graph context and suggestions.",
      });
      return;
    }

    // Proximity Concept Explorer Search Drawer
    new ProximitySearchDrawer(container, this.plugin, () => this.currentNotePath);

    // 1. Missing Links Section (Semantic Gaps)
    this.renderGapsSection(container);

    // 2. Contradictions & AI Inferences Section
    this.renderInferencesSection(container);

    // 3. Graph Context Section
    this.renderContextSection(container);
  }

  private renderGapsSection(container: HTMLElement): void {
    const dismissed = this.plugin.settings.dismissedSuggestions || {};
    const visibleGaps = this.gaps.filter(
      (g) => !dismissed[`${g.source_path}::${g.target_path}`]
    );

    const sec = container.createDiv({ cls: "orbit-section" });
    sec.createDiv({
      cls: "orbit-section-header",
      text: `Missing Links (${visibleGaps.length})`,
    });

    if (visibleGaps.length === 0) {
      sec.createDiv({ cls: "orbit-empty-state", text: "No unlinked semantic gaps detected." });
    } else {
      for (const gap of visibleGaps) {
        this.renderGapCard(sec, gap);
      }
    }

    // Dismissed Drawer
    this.renderDismissedDrawer(sec);
  }

  private renderGapCard(sec: HTMLElement, gap: SemanticGapCandidate): void {
    const isTarget = gap.source_path === this.currentNotePath;
    const otherTitle = isTarget ? gap.target_title : gap.source_title;
    const otherPath = isTarget ? gap.target_path : gap.source_path;

    const card = sec.createDiv({ cls: "orbit-card" });
    const cardHead = card.createDiv({ cls: "orbit-card-header" });
    const targetLink = cardHead.createEl("a", {
      cls: "orbit-card-target",
      text: otherTitle || otherPath.replace(/\.md$/, ""),
    });
    targetLink.onclick = () => this.app.workspace.openLinkText(otherPath, "");

    const pct = Math.round(gap.similarity * 100);
    cardHead.createSpan({ cls: "orbit-badge", text: `${pct}% similar` });

    card.createDiv({
      cls: "orbit-card-reason",
      text: `Graph distance: ${gap.hops} hops away with high semantic proximity.`,
    });

    const actions = card.createDiv({ cls: "orbit-card-actions" });
    const insertBtn = actions.createEl("button", {
      cls: "orbit-btn-sm mod-cta",
      text: "+ Link",
    });
    insertBtn.onclick = () => this.plugin.insertLink(otherTitle || otherPath.replace(/\.md$/, ""));

    const dismissBtn = actions.createEl("button", { cls: "orbit-btn-sm", text: "Dismiss" });
    dismissBtn.onclick = async () => {
      const key = `${gap.source_path}::${gap.target_path}`;
      if (!this.plugin.settings.dismissedSuggestions) {
        this.plugin.settings.dismissedSuggestions = {};
      }
      this.plugin.settings.dismissedSuggestions[key] = {
        sourcePath: gap.source_path,
        targetPath: gap.target_path,
        targetTitle: otherTitle,
        dismissedAt: Date.now(),
      };
      await this.plugin.saveSettings();
      this.render();
    };
  }

  private renderDismissedDrawer(sec: HTMLElement): void {
    const dismissed = this.plugin.settings.dismissedSuggestions || {};
    const noteDismissed = Object.entries(dismissed).filter(([_, item]) =>
      this.currentNotePath && (item.sourcePath === this.currentNotePath || item.targetPath === this.currentNotePath)
    );

    if (noteDismissed.length === 0) return;

    const drawer = sec.createDiv({ cls: "orbit-dismissed-drawer" });
    const toggleBtn = drawer.createEl("a", {
      cls: "orbit-dismissed-toggle",
      text: `${this.showDismissed ? "▾ Hide" : "▸ Show"} ${noteDismissed.length} dismissed`,
    });
    toggleBtn.onclick = () => {
      this.showDismissed = !this.showDismissed;
      this.render();
    };

    if (this.showDismissed) {
      const listEl = drawer.createDiv({ cls: "orbit-dismissed-list" });
      for (const [key, item] of noteDismissed) {
        const row = listEl.createDiv({ cls: "orbit-dismissed-row" });
        row.createSpan({ cls: "orbit-dismissed-title", text: item.targetTitle || item.targetPath });
        const restoreBtn = row.createEl("button", { cls: "orbit-btn-sm", text: "Restore" });
        restoreBtn.onclick = async () => {
          delete this.plugin.settings.dismissedSuggestions[key];
          await this.plugin.saveSettings();
          this.render();
        };
      }
    }
  }

  private renderInferencesSection(container: HTMLElement): void {
    const infs = this.context?.inferred_relationships || [];
    const sec = container.createDiv({ cls: "orbit-section" });
    sec.createDiv({
      cls: "orbit-section-header",
      text: `Inferred Relationships (${infs.length})`,
    });

    if (infs.length === 0) {
      sec.createDiv({ cls: "orbit-empty-state", text: "No AI inferences for this note." });
      return;
    }

    for (const rel of infs) {
      const isContra = rel.rel_type === "CONTRADICTS";
      const card = sec.createDiv({
        cls: `orbit-card ${isContra ? "orbit-card-contradiction" : ""}`,
      });
      const cardHead = card.createDiv({ cls: "orbit-card-header" });

      const targetTitle = rel.target_path.replace(/\.md$/, "");
      const link = cardHead.createEl("a", { cls: "orbit-card-target", text: targetTitle });
      link.onclick = () => this.app.workspace.openLinkText(rel.target_path, "");

      const badgeCls = isContra ? "orbit-badge orbit-badge-warning" : "orbit-badge orbit-badge-accent";
      cardHead.createSpan({ cls: badgeCls, text: rel.rel_type });

      if (rel.reason) {
        card.createDiv({ cls: "orbit-card-reason", text: `"${rel.reason}"` });
      }
    }
  }

  private renderContextSection(container: HTMLElement): void {
    const sec = container.createDiv({ cls: "orbit-section" });
    sec.createDiv({ cls: "orbit-section-header", text: "Graph Context" });

    const tags = this.context?.tags || [];
    if (tags.length > 0) {
      const tagChips = sec.createDiv({ cls: "orbit-chip-container", attr: { style: "margin-bottom: 8px;" } });
      for (const t of tags) {
        tagChips.createSpan({ cls: "orbit-chip", text: `#${t}` });
      }
    }

    const backlinks = this.context?.backlinks || [];
    sec.createDiv({
      cls: "orbit-card-reason",
      text: `Backlinks: ${backlinks.length}  |  Outgoing: ${
        this.context?.outgoing_links?.length || 0
      }  |  2-Hop Cluster: ${this.context?.neighbors_2hop?.length || 0}`,
    });
  }
}
