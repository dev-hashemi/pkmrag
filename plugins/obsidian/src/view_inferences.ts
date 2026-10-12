/**
 * Inferred relationships and dismissed suggestions drawer rendering for PKMRAG sidebar.
 */

import type PkmragPlugin from "./main";
import { NoteContext } from "./types";

export function renderInferencesSection(
  container: HTMLElement,
  context: NoteContext | null,
  onOpenLink: (path: string) => void
): void {
  const infs = context?.inferred_relationships || [];
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
    const card = sec.createDiv({
      cls: `pkmrag-card ${isContra ? "pkmrag-card-contradiction" : ""}`,
    });
    const cardHead = card.createDiv({ cls: "pkmrag-card-header" });

    const targetTitle = rel.target_path.replace(/\.md$/, "");
    const link = cardHead.createEl("a", { cls: "pkmrag-card-target", text: targetTitle });
    link.onclick = () => onOpenLink(rel.target_path);

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
    row.createSpan({ cls: "pkmrag-dismissed-title", text: item.targetTitle || item.targetPath });
    const restoreBtn = row.createEl("button", { cls: "pkmrag-btn-sm", text: "Restore" });
    restoreBtn.onclick = async () => {
      delete plugin.settings.dismissedSuggestions[key];
      await plugin.saveSettings();
      onRestore();
    };
  }
}
