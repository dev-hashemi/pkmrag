/**
 * Inferred relationships and dismissed suggestions drawer rendering for PKMRAG sidebar.
 */

import type PkmragPlugin from "./main";
import { NoteContext } from "./types";
import { displayTitle, isDismissedPair } from "./format";

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
  sec.createDiv({
    cls: "pkmrag-section-header",
    text: `Inferred Relationships (${infs.length})`,
  });

  if (infs.length === 0) {
    sec.createDiv({ cls: "pkmrag-empty-state", text: "No AI inferences for this note." });
    return;
  }

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
