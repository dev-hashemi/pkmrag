/**
 * Semantic gaps (missing links) section renderer for PKMRAG Insights sidebar.
 */

import type PkmragPlugin from "./main";
import { SemanticGapCandidate } from "./types";
import { renderDismissedDrawer } from "./view_inferences";
import {
  displayTitle,
  excerpt,
  formatBridgePath,
  formatGapDistance,
  gapCounterpart,
  noteStem,
  searchAnchor,
  splitChunkHeading,
} from "./format";

/** Loading / failure state of the missing-links section. */
export interface GapsSectionState {
  loading?: boolean;
  error?: string | null;
}

export function renderGapsSection(
  container: HTMLElement,
  plugin: PkmragPlugin,
  gaps: SemanticGapCandidate[],
  currentNotePath: string | null,
  onUpdate: () => void,
  state: GapsSectionState = {}
): void {
  const dismissed = plugin.settings.dismissedSuggestions || {};
  const visibleGaps = gaps.filter(
    (g) => !dismissed[`${g.source_path}::${g.target_path}`]
  );

  const sec = container.createDiv({ cls: "pkmrag-section" });
  sec.createDiv({
    cls: "pkmrag-section-header",
    text: state.loading ? "Missing Links" : `Missing Links (${visibleGaps.length})`,
  });

  if (state.loading) {
    sec.createDiv({
      cls: "pkmrag-empty-state",
      text: "Scanning vault for related notes...",
    });
  } else if (state.error) {
    sec.createDiv({
      cls: "pkmrag-empty-state",
      text: `Could not load suggestions: ${state.error}`,
    });
  } else if (visibleGaps.length === 0) {
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
  const counterpart = gapCounterpart(gap, currentNotePath);
  const otherTitle = counterpart.title;
  const otherPath = counterpart.path;

  const card = sec.createDiv({ cls: "pkmrag-card" });
  const cardHead = card.createDiv({ cls: "pkmrag-card-header" });
  const targetLink = cardHead.createEl("a", {
    cls: "pkmrag-card-target",
    text: otherTitle,
  });
  targetLink.onclick = () => plugin.app.workspace.openLinkText(otherPath, "");

  const pct = Math.round(gap.similarity * 100);
  cardHead.createSpan({ cls: "pkmrag-badge", text: `${pct}% similar` });

  card.createDiv({
    cls: "pkmrag-card-reason",
    text: `Graph distance: ${formatGapDistance(gap.hops)}.`,
  });

  if (gap.bridge_path.length > 0) {
    const bridge = card.createDiv({ cls: "pkmrag-bridge" });
    bridge.setAttribute("title", formatBridgePath(gap.bridge_path));
    bridge.createSpan({ cls: "pkmrag-bridge-label", text: "Bridge" });
    const chain = bridge.createSpan({ cls: "pkmrag-bridge-chain" });
    gap.bridge_path.forEach((step, idx) => {
      if (idx > 0) {
        chain.createSpan({ cls: "pkmrag-bridge-sep", text: "→" });
      }
      const stepLink = chain.createEl("a", {
        cls: "pkmrag-bridge-step",
        text: noteStem(step),
      });
      stepLink.onclick = () => plugin.app.workspace.openLinkText(step, "");
    });
  }

  renderEvidence(card, gap);

  const actions = card.createDiv({ cls: "pkmrag-card-actions" });
  const insertBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "+ Link",
  });
  insertBtn.onclick = () => plugin.insertLink(noteStem(otherPath));

  const dismissBtn = actions.createEl("button", { cls: "pkmrag-btn-sm", text: "Dismiss" });
  dismissBtn.onclick = async () => {
    const key = `${gap.source_path}::${gap.target_path}`;
    if (!plugin.settings.dismissedSuggestions) {
      plugin.settings.dismissedSuggestions = {};
    }
    plugin.settings.dismissedSuggestions[key] = {
      sourcePath: gap.source_path,
      targetPath: gap.target_path,
      targetTitle: displayTitle(otherPath, otherTitle),
      dismissedAt: Date.now(),
    };
    await plugin.saveSettings();
    onUpdate();
  };
}

/** Render the matching passages that justify the similarity score. */
function renderEvidence(card: HTMLElement, gap: SemanticGapCandidate): void {
  const details = card.createEl("details", { cls: "pkmrag-evidence" });
  const summary = details.createEl("summary", {
    cls: "pkmrag-evidence-summary",
    text: "Why are these similar?",
  });
  summary.setAttribute("title", "Matching passages from both notes");

  const body = details.createDiv({ cls: "pkmrag-evidence-body" });
  const sides: Array<[string, string, string]> = [
    ["From", gap.source_path, gap.source_chunk_text],
    ["To", gap.target_path, gap.target_chunk_text],
  ];

  for (const [label, path, text] of sides) {
    const { heading, body: passage } = splitChunkHeading(text);
    const row = body.createDiv({ cls: "pkmrag-evidence-row" });
    row.createSpan({ cls: "pkmrag-evidence-label", text: label });
    row.createSpan({ cls: "pkmrag-evidence-note", text: displayTitle(path) });
    const section = searchAnchor(heading);
    if (section) {
      row.createSpan({ cls: "pkmrag-evidence-heading", text: section });
    }
    if (passage) {
      row.createDiv({ cls: "pkmrag-evidence-text", text: excerpt(passage, 240) });
    }
  }
}
