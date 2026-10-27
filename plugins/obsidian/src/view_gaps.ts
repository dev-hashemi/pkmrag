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
    const initialLimit = plugin.settings.maxSuggestions || 5;
    const initialGaps = visibleGaps.slice(0, initialLimit);
    const remainingGaps = visibleGaps.slice(initialLimit);

    for (const gap of initialGaps) {
      renderGapCard(sec, plugin, gap, currentNotePath, onUpdate);
    }

    if (remainingGaps.length > 0) {
      const moreContainer = sec.createDiv({ cls: "pkmrag-more-gaps pkmrag-hidden" });
      for (const gap of remainingGaps) {
        renderGapCard(moreContainer, plugin, gap, currentNotePath, onUpdate);
      }
      const showMoreBtn = sec.createEl("button", {
        cls: "pkmrag-btn-sm pkmrag-btn-show-more",
        text: `▾ Show ${remainingGaps.length} more related notes`,
      });
      showMoreBtn.onclick = () => {
        const isHidden = moreContainer.hasClass("pkmrag-hidden");
        moreContainer.toggleClass("pkmrag-hidden", !isHidden);
        showMoreBtn.setText(
          isHidden ? "▴ Show less" : `▾ Show ${remainingGaps.length} more related notes`
        );
      };
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

  const docPct = Math.round(gap.similarity * 100);
  let badgeLabel = `${docPct}% similar`;
  if (gap.relationship_type === "DEEP_OVERLAP") {
    badgeLabel = "Deep Overlap";
  } else if (gap.relationship_type === "CONTAINMENT") {
    badgeLabel = "Topic Included";
  } else if (gap.relationship_type === "SHARED_CONCEPT") {
    badgeLabel = "Shared Concept";
  }
  cardHead.createSpan({ cls: "pkmrag-badge", text: badgeLabel });

  if (gap.ui_summary) {
    card.createDiv({
      cls: "pkmrag-card-summary",
      text: gap.ui_summary,
    });
  }

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

  const matches =
    gap.matched_chunks && gap.matched_chunks.length > 0
      ? gap.matched_chunks
      : [
          {
            source_chunk_id: gap.source_chunk_id,
            target_chunk_id: gap.target_chunk_id,
            source_chunk_text: gap.source_chunk_text,
            target_chunk_text: gap.target_chunk_text,
            similarity: gap.chunk_similarity || gap.similarity,
          },
        ];

  const headerLabel =
    matches.length > 1
      ? `Why are these similar? (${matches.length} matching sections)`
      : `Why are these similar? (${Math.round((matches[0].similarity || gap.chunk_similarity || gap.similarity) * 100)}% section match)`;

  const summary = details.createEl("summary", {
    cls: "pkmrag-evidence-summary",
    text: headerLabel,
  });
  summary.setAttribute("title", "Matching passages from both notes with section similarity scores");

  const body = details.createDiv({ cls: "pkmrag-evidence-body" });

  const initialSectionLimit = 2;
  const initialMatches = matches.slice(0, initialSectionLimit);
  const remainingMatches = matches.slice(initialSectionLimit);

  const renderMatch = (parentEl: HTMLElement, m: (typeof matches)[0], idx: number) => {
    const chunkPct = Math.round(m.similarity * 100);
    const chunkContainer = parentEl.createDiv({ cls: "pkmrag-evidence-pair" });
    const sectionTitle =
      matches.length > 1
        ? `Match ${idx + 1} · ${chunkPct}% section similarity`
        : `Section similarity: ${chunkPct}%`;

    chunkContainer.createDiv({
      cls: "pkmrag-evidence-section-header",
      text: sectionTitle,
    });

    const sides: Array<[string, string, string, string | undefined]> = [
      ["From", gap.source_path, m.source_chunk_text, m.source_heading],
      ["To", gap.target_path, m.target_chunk_text, m.target_heading],
    ];

    for (const [label, path, text, headingOverride] of sides) {
      const { heading: parsedHeading, body: passage } = splitChunkHeading(text);
      const heading = headingOverride || parsedHeading;
      const row = chunkContainer.createDiv({ cls: "pkmrag-evidence-row" });
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
  };

  initialMatches.forEach((m, idx) => renderMatch(body, m, idx));

  if (remainingMatches.length > 0) {
    const moreSectionsContainer = body.createDiv({ cls: "pkmrag-more-sections pkmrag-hidden" });
    remainingMatches.forEach((m, idx) =>
      renderMatch(moreSectionsContainer, m, initialSectionLimit + idx)
    );

    const showMoreSectionsBtn = body.createEl("button", {
      cls: "pkmrag-btn-sm pkmrag-btn-show-more",
      text: `▾ Show ${remainingMatches.length} more matching sections`,
    });
    showMoreSectionsBtn.onclick = () => {
      const isHidden = moreSectionsContainer.hasClass("pkmrag-hidden");
      moreSectionsContainer.toggleClass("pkmrag-hidden", !isHidden);
      showMoreSectionsBtn.setText(
        isHidden ? "▴ Show fewer sections" : `▾ Show ${remainingMatches.length} more matching sections`
      );
    };
  }
}
