/**
 * Semantic gaps (missing links) section renderer for Orbit Insights sidebar.
 */

import type OrbitInsightsPlugin from "./main";
import { SemanticGapCandidate } from "./types";
import { renderDismissedDrawer } from "./view_inferences";

export function renderGapsSection(
  container: HTMLElement,
  plugin: OrbitInsightsPlugin,
  gaps: SemanticGapCandidate[],
  currentNotePath: string | null,
  onUpdate: () => void
): void {
  const dismissed = plugin.settings.dismissedSuggestions || {};
  const visibleGaps = gaps.filter(
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
      renderGapCard(sec, plugin, gap, currentNotePath, onUpdate);
    }
  }

  // Dismissed Drawer
  renderDismissedDrawer(sec, plugin, currentNotePath, onUpdate);
}

function renderGapCard(
  sec: HTMLElement,
  plugin: OrbitInsightsPlugin,
  gap: SemanticGapCandidate,
  currentNotePath: string | null,
  onUpdate: () => void
): void {
  const isTarget = gap.source_path === currentNotePath;
  const otherTitle = isTarget ? gap.target_title : gap.source_title;
  const otherPath = isTarget ? gap.target_path : gap.source_path;

  const card = sec.createDiv({ cls: "orbit-card" });
  const cardHead = card.createDiv({ cls: "orbit-card-header" });
  const targetLink = cardHead.createEl("a", {
    cls: "orbit-card-target",
    text: otherTitle || otherPath.replace(/\.md$/, ""),
  });
  targetLink.onclick = () => plugin.app.workspace.openLinkText(otherPath, "");

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
  insertBtn.onclick = () => plugin.insertLink(otherTitle || otherPath.replace(/\.md$/, ""));

  const dismissBtn = actions.createEl("button", { cls: "orbit-btn-sm", text: "Dismiss" });
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
