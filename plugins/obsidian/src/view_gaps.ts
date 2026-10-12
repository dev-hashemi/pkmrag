/**
 * Semantic gaps (missing links) section renderer for PKMRAG Insights sidebar.
 */

import type PkmragPlugin from "./main";
import { SemanticGapCandidate } from "./types";
import { renderDismissedDrawer } from "./view_inferences";

export function renderGapsSection(
  container: HTMLElement,
  plugin: PkmragPlugin,
  gaps: SemanticGapCandidate[],
  currentNotePath: string | null,
  onUpdate: () => void
): void {
  const dismissed = plugin.settings.dismissedSuggestions || {};
  const visibleGaps = gaps.filter(
    (g) => !dismissed[`${g.source_path}::${g.target_path}`]
  );

  const sec = container.createDiv({ cls: "pkmrag-section" });
  sec.createDiv({
    cls: "pkmrag-section-header",
    text: `Missing Links (${visibleGaps.length})`,
  });

  if (visibleGaps.length === 0) {
    sec.createDiv({ cls: "pkmrag-empty-state", text: "No unlinked semantic gaps detected." });
  } else {
    for (const gap of visibleGaps) {
      renderGapCard(sec, plugin, gap, currentNotePath, onUpdate);
    }
  }

  // Dismissed Drawer
  renderDismissedDrawer(sec, plugin, currentNotePath, onUpdate);
}

function renderGapCard(
  sec: HTMLElement,
  plugin: PkmragPlugin,
  gap: SemanticGapCandidate,
  currentNotePath: string | null,
  onUpdate: () => void
): void {
  const isTarget = gap.source_path === currentNotePath;
  const otherTitle = isTarget ? gap.target_title : gap.source_title;
  const otherPath = isTarget ? gap.target_path : gap.source_path;

  const card = sec.createDiv({ cls: "pkmrag-card" });
  const cardHead = card.createDiv({ cls: "pkmrag-card-header" });
  const targetLink = cardHead.createEl("a", {
    cls: "pkmrag-card-target",
    text: otherTitle || otherPath.replace(/\.md$/, ""),
  });
  targetLink.onclick = () => plugin.app.workspace.openLinkText(otherPath, "");

  const pct = Math.round(gap.similarity * 100);
  cardHead.createSpan({ cls: "pkmrag-badge", text: `${pct}% similar` });

  card.createDiv({
    cls: "pkmrag-card-reason",
    text: `Graph distance: ${gap.hops} hops away with high semantic proximity.`,
  });

  const actions = card.createDiv({ cls: "pkmrag-card-actions" });
  const insertBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "+ Link",
  });
  insertBtn.onclick = () => plugin.insertLink(otherTitle || otherPath.replace(/\.md$/, ""));

  const dismissBtn = actions.createEl("button", { cls: "pkmrag-btn-sm", text: "Dismiss" });
  dismissBtn.onclick = async () => {
    const key = `${gap.source_path}::${gap.target_path}`;
    if (!plugin.settings.dismissedSuggestions) {
      plugin.settings.dismissedSuggestions = {};
    }
    plugin.settings.dismissedSuggestions[key] = {
      sourcePath: gap.source_path,
      targetPath: gap.target_path,
      targetTitle: otherTitle,
      dismissedAt: Date.now(),
    };
    await plugin.saveSettings();
    onUpdate();
  };
}
