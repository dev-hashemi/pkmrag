/**
 * Proximity concept search bar and result renderer for PKMRAG sidebar.
 */

import type PkmragPlugin from "./main";
import { SearchResult } from "./types";

export class ProximitySearchDrawer {
  private containerEl!: HTMLElement;
  private resultsEl!: HTMLElement;
  private inputEl!: HTMLInputElement;
  private searchTimer: number | null = null;
  private isOpen = false;

  constructor(
    private parentEl: HTMLElement,
    private plugin: PkmragPlugin,
    private getCurrentNotePath: () => string | null
  ) {
    this.render();
  }

  private render(): void {
    this.containerEl = this.parentEl.createDiv({ cls: "pkmrag-search-container" });

    const toggleRow = this.containerEl.createDiv({ cls: "pkmrag-search-toggle" });
    const toggleBtn = toggleRow.createEl("button", {
      cls: "pkmrag-btn-sm pkmrag-search-btn",
      text: "🔍 Concept Explorer",
    });

    const searchBox = this.containerEl.createDiv({
      cls: "pkmrag-search-box pkmrag-hidden",
    });

    toggleBtn.onclick = () => {
      this.isOpen = !this.isOpen;
      searchBox.toggleClass("pkmrag-hidden", !this.isOpen);
      if (this.isOpen) {
        this.inputEl.focus();
      } else {
        this.resultsEl.empty();
        this.inputEl.value = "";
      }
    };

    this.inputEl = searchBox.createEl("input", {
      type: "text",
      placeholder: "Search concepts near this note...",
      cls: "pkmrag-search-input",
    });

    this.inputEl.oninput = () => {
      if (this.searchTimer) window.clearTimeout(this.searchTimer);
      const query = this.inputEl.value.trim();
      if (!query) {
        this.resultsEl.empty();
        return;
      }

      this.searchTimer = window.setTimeout(() => this.executeSearch(query), 350);
    };

    this.resultsEl = searchBox.createDiv({ cls: "pkmrag-search-results" });
  }

  private async executeSearch(query: string): Promise<void> {
    this.resultsEl.empty();
    const loadingEl = this.resultsEl.createDiv({
      cls: "pkmrag-empty-state",
      text: "Searching graph...",
    });

    try {
      const near = this.getCurrentNotePath() || undefined;
      const results = await this.plugin.client.searchVault(query, near, 4);
      loadingEl.remove();

      if (results.length === 0) {
        this.resultsEl.createDiv({
          cls: "pkmrag-empty-state",
          text: `No matching chunks found for "${query}".`,
        });
        return;
      }

      for (const res of results) {
        this.renderResultCard(res);
      }
    } catch (err: unknown) {
      loadingEl.setText(err instanceof Error ? err.message : String(err));
    }
  }

  private renderResultCard(res: SearchResult): void {
    const card = this.resultsEl.createDiv({ cls: "pkmrag-card pkmrag-search-card" });
    const head = card.createDiv({ cls: "pkmrag-card-header" });

    const titleEl = head.createEl("a", {
      cls: "pkmrag-card-target",
      text: res.title || res.path.replace(/\.md$/, ""),
    });
    titleEl.onclick = () => this.plugin.app.workspace.openLinkText(res.path, "");

    if (res.heading) {
      head.createSpan({ cls: "pkmrag-badge", text: `# ${res.heading}` });
    }

    const excerpt = res.content.length > 120 ? res.content.slice(0, 120) + "..." : res.content;
    card.createDiv({ cls: "pkmrag-card-reason", text: excerpt });

    const actions = card.createDiv({ cls: "pkmrag-card-actions" });
    const insertBtn = actions.createEl("button", {
      cls: "pkmrag-btn-sm",
      text: "+ Insert Ref",
    });
    insertBtn.onclick = () => {
      const linkText = res.heading
        ? `${res.title || res.path.replace(/\.md$/, "")}#${res.heading}`
        : res.title || res.path.replace(/\.md$/, "");
      this.plugin.insertLink(linkText);
    };
  }
}
