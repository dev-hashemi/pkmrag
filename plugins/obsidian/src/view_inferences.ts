/**
 * Inferred relationships and dismissed suggestions drawer rendering for PKMRAG sidebar.
 */

import { Notice } from "obsidian";
import type PkmragPlugin from "./main";
import { NoteContext } from "./types";
import { displayTitle, formatRelativeTime, isDismissedPair } from "./format";
import { DiscoveryEstimateModal } from "./modal_estimate";

export function renderInferencesSection(
  container: HTMLElement,
  plugin: PkmragPlugin,
  context: NoteContext | null,
  onOpenLink: (path: string) => void
): void {
  const dismissed = plugin.settings.dismissedSuggestions || {};
  // A dismissed missing link must not reappear as an inferred relationship.
  const infs = (context?.inferred_relationships || []).filter(
    (rel) => !isDismissedPair(dismissed, rel.source_path, rel.target_path)
  );

  const sec = container.createDiv({ cls: "pkmrag-section" });

  // 1. Header with Title & Action Button
  const secHead = sec.createDiv({ cls: "pkmrag-section-header-row" });
  secHead.createDiv({
    cls: "pkmrag-section-header",
    text: `Inferred Relationships (${infs.length})`,
  });

  const inferBtn = secHead.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "⚡ Infer Note",
  });
  inferBtn.setAttribute("title", "Estimate tokens and infer AI relationships for this note");

  const runNoteDiscovery = async () => {
    inferBtn.setAttribute("disabled", "true");
    inferBtn.setText("Estimating...");
    try {
      const estimate = await plugin.client.estimateDiscover({
        note_path: context?.path,
      });
      new DiscoveryEstimateModal(plugin.app, {
        estimate,
        notePath: context?.path,
        noteTitle: context?.title,
        onConfirm: async () => {
          new Notice("PKMRAG: AI Relationship Inference started...");
          await plugin.client.triggerDiscover({ note_path: context?.path });
        },
      }).open();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      new Notice(`PKMRAG: Estimation failed: ${msg}`);
    } finally {
      inferBtn.removeAttribute("disabled");
      inferBtn.setText("⚡ Infer Note");
    }
  };

  inferBtn.onclick = runNoteDiscovery;

  // 2. Freshness & Timestamp Subtitle
  let latestTs = context?.last_discovered_at || null;
  if (!latestTs && infs.length > 0) {
    for (const rel of infs) {
      if (rel.created_at && (!latestTs || rel.created_at > latestTs)) {
        latestTs = rel.created_at;
      }
    }
  }

  const subRow = sec.createDiv({ cls: "pkmrag-section-subtitle" });
  if (latestTs) {
    const relTime = formatRelativeTime(latestTs);
    const dateStr = new Date(latestTs).toLocaleString();
    const timeSpan = subRow.createSpan({
      cls: "pkmrag-timestamp",
      text: `Last discovered: ${relTime}`,
    });
    timeSpan.setAttribute("title", `Analysis performed on: ${dateStr}`);
  } else {
    subRow.createSpan({
      cls: "pkmrag-timestamp pkmrag-timestamp-empty",
      text: "Not analyzed yet",
    });
  }

  // 3. In-Section Progress Bar (if a discovery job is active)
  const activeJob = plugin.activeJob;
  if (activeJob && activeJob.type === "discover") {
    const isThisNote = activeJob.note_path === context?.path;
    const isVaultWide = !activeJob.note_path;
    if (isThisNote || isVaultWide) {
      const progCard = sec.createDiv({ cls: "pkmrag-in-section-progress" });
      const progHead = progCard.createDiv({ cls: "pkmrag-in-section-progress-head" });
      progHead.createSpan({
        text: isThisNote ? "🧠 Inferring note relationships..." : "🧠 Running vault-wide discovery...",
      });
      progHead.createSpan({
        cls: "pkmrag-in-section-progress-pct",
        text: `${activeJob.percent}%`,
      });

      const track = progCard.createDiv({ cls: "pkmrag-progress-track" });
      const fill = track.createDiv({ cls: "pkmrag-progress-fill" });
      fill.style.width = `${Math.min(100, Math.max(0, activeJob.percent))}%`;

      if (activeJob.message) {
        progCard.createDiv({
          cls: "pkmrag-progress-detail",
          text: activeJob.message,
        });
      }
    }
  }

  // 4. Empty State
  if (infs.length === 0) {
    const emptyContainer = sec.createDiv({ cls: "pkmrag-empty-state-actionable" });
    emptyContainer.createDiv({
      cls: "pkmrag-empty-state-text",
      text: "No AI inferences for this note yet. Run discovery to detect conceptual bridges, contradictions, and extensions.",
    });
    const discoverActionBtn = emptyContainer.createEl("button", {
      cls: "pkmrag-btn-sm mod-cta",
      text: "⚡ Discover for this note",
    });
    discoverActionBtn.onclick = runNoteDiscovery;
    return;
  }

  // 5. Inferred Relationship Cards
  for (const rel of infs) {
    const isContra = rel.rel_type === "CONTRADICTS";
    const otherPath = rel.source_path === context?.path ? rel.target_path : rel.source_path;
    const card = sec.createDiv({
      cls: `pkmrag-card ${isContra ? "pkmrag-card-contradiction" : ""}`,
    });
    const cardHead = card.createDiv({ cls: "pkmrag-card-header" });

    const link = cardHead.createEl("a", { cls: "pkmrag-card-target", text: displayTitle(otherPath) });
    link.onclick = () => onOpenLink(otherPath);

    const badgeCls = isContra ? "pkmrag-badge pkmrag-badge-warning" : "pkmrag-badge pkmrag-badge-accent";
    cardHead.createSpan({ cls: badgeCls, text: rel.rel_type });

    if (rel.reason) {
      card.createDiv({ cls: "pkmrag-card-reason", text: `"${rel.reason}"` });
    }

    // Metadata line (confidence, recency, model)
    const cardMeta = card.createDiv({ cls: "pkmrag-card-meta" });
    const confPct = Math.round(rel.confidence * 100);
    const metaParts = [`${confPct}% confidence`];
    if (rel.created_at) {
      metaParts.push(formatRelativeTime(rel.created_at));
    }
    if (rel.model) {
      metaParts.push(rel.model);
    }
    cardMeta.createSpan({
      cls: "pkmrag-card-meta-text",
      text: metaParts.join(" · "),
    });
  }
}

export function renderDismissedDrawer(
  sec: HTMLElement,
  plugin: PkmragPlugin,
  currentNotePath: string | null,
  onRestore: () => void
): void {
  const dismissed = plugin.settings.dismissedSuggestions || {};
  const noteDismissed = Object.entries(dismissed).filter(([_, item]) =>
    currentNotePath && (item.sourcePath === currentNotePath || item.targetPath === currentNotePath)
  );

  if (noteDismissed.length === 0) return;

  const drawer = sec.createDiv({ cls: "pkmrag-dismissed-drawer" });
  let isOpen = false;
  const toggleBtn = drawer.createEl("a", {
    cls: "pkmrag-dismissed-toggle",
    text: `▸ Show ${noteDismissed.length} dismissed`,
  });

  const listEl = drawer.createDiv({ cls: "pkmrag-dismissed-list pkmrag-hidden" });

  toggleBtn.onclick = () => {
    isOpen = !isOpen;
    toggleBtn.setText(`${isOpen ? "▾ Hide" : "▸ Show"} ${noteDismissed.length} dismissed`);
    listEl.toggleClass("pkmrag-hidden", !isOpen);
  };

  for (const [key, item] of noteDismissed) {
    const row = listEl.createDiv({ cls: "pkmrag-dismissed-row" });
    row.createSpan({ cls: "pkmrag-dismissed-title", text: displayTitle(item.targetPath, item.targetTitle) });
    const restoreBtn = row.createEl("button", { cls: "pkmrag-btn-sm", text: "Restore" });
    restoreBtn.onclick = async () => {
      delete plugin.settings.dismissedSuggestions[key];
      await plugin.saveSettings();
      onRestore();
    };
  }
}
