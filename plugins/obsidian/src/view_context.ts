/**
 * Structural graph context and vault summary rendering for the PKMRAG Insights sidebar.
 */

import { NoteContext } from "./types";
import { displayTitle } from "./format";

/** Number of related notes listed before the "show more" toggle appears. */
const CONTEXT_VISIBLE_LINKS = 5;

export interface VaultStats {
  notes: number;
  links: number;
  tags: number;
}

/** Render the graph context section: tags, backlinks, outgoing links, 2-hop cluster. */
export function renderContextSection(
  container: HTMLElement,
  context: NoteContext | null,
  onOpenLink: (path: string) => void
): void {
  const sec = container.createDiv({ cls: "pkmrag-section" });
  sec.createDiv({ cls: "pkmrag-section-header", text: "Graph Context" });

  if (context?.is_unresolved) {
    sec.createDiv({
      cls: "pkmrag-card-reason",
      text: "Ghost note: linked to, but no file on disk yet.",
    });
  }

  const tags = context?.tags || [];
  if (tags.length > 0) {
    const tagChips = sec.createDiv({
      cls: "pkmrag-chip-container",
      attr: { style: "margin-bottom: 8px;" },
    });
    for (const t of tags) {
      tagChips.createSpan({ cls: "pkmrag-chip", text: `#${t}` });
    }
  }

  renderLinkGroup(sec, "Backlinks", context?.backlinks || [], onOpenLink);
  renderLinkGroup(sec, "Outgoing Links", context?.outgoing_links || [], onOpenLink);
  renderLinkGroup(sec, "2-Hop Cluster", context?.neighbors_2hop || [], onOpenLink);
}

/** Render a group of related notes as clickable links, collapsing long lists. */
function renderLinkGroup(
  sec: HTMLElement,
  label: string,
  paths: string[],
  onOpenLink: (path: string) => void
): void {
  const group = sec.createDiv({ cls: "pkmrag-context-group" });
  const head = group.createDiv({ cls: "pkmrag-context-group-head" });
  head.createSpan({ cls: "pkmrag-context-group-label", text: label });
  head.createSpan({ cls: "pkmrag-context-group-count", text: String(paths.length) });

  if (paths.length === 0) {
    group.createDiv({ cls: "pkmrag-empty-state", text: "None" });
    return;
  }

  const list = group.createDiv({ cls: "pkmrag-link-list" });
  paths.forEach((path, idx) => {
    const row = list.createDiv({
      cls: idx >= CONTEXT_VISIBLE_LINKS ? "pkmrag-link-row pkmrag-extra" : "pkmrag-link-row",
    });
    const link = row.createEl("a", { cls: "pkmrag-link", text: displayTitle(path) });
    link.onclick = () => onOpenLink(path);
    row.createSpan({ cls: "pkmrag-link-path", text: path });
  });

  if (paths.length > CONTEXT_VISIBLE_LINKS) {
    const toggle = group.createEl("a", {
      cls: "pkmrag-context-toggle",
      text: `▸ Show ${paths.length - CONTEXT_VISIBLE_LINKS} more`,
    });
    toggle.onclick = () => {
      const expanded = group.hasClass("pkmrag-expanded");
      group.toggleClass("pkmrag-expanded", !expanded);
      toggle.setText(
        expanded ? `▸ Show ${paths.length - CONTEXT_VISIBLE_LINKS} more` : "▾ Show less"
      );
    };
  }
}

/** Render the vault-wide graph statistics footer. */
export function renderVaultStats(container: HTMLElement, stats: VaultStats | null): void {
  if (!stats) return;
  const footer = container.createDiv({ cls: "pkmrag-vault-stats" });
  footer.createSpan({ text: `${stats.notes} notes` });
  footer.createSpan({ text: `${stats.links} links` });
  footer.createSpan({ text: `${stats.tags} tags` });
}
