/**
 * Inferred relationships and dismissed suggestions drawer rendering for Orbit sidebar.
 */

import type OrbitInsightsPlugin from "./main";
import { NoteContext } from "./types";

export function renderInferencesSection(
  container: HTMLElement,
  context: NoteContext | null,
  onOpenLink: (path: string) => void
): void {
  const infs = context?.inferred_relationships || [];
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
    link.onclick = () => onOpenLink(rel.target_path);

    const badgeCls = isContra ? "orbit-badge orbit-badge-warning" : "orbit-badge orbit-badge-accent";
    cardHead.createSpan({ cls: badgeCls, text: rel.rel_type });

    if (rel.reason) {
      card.createDiv({ cls: "orbit-card-reason", text: `"${rel.reason}"` });
    }
  }
}

export function renderDismissedDrawer(
  sec: HTMLElement,
  plugin: OrbitInsightsPlugin,
  currentNotePath: string | null,
  onRestore: () => void
): void {
  const dismissed = plugin.settings.dismissedSuggestions || {};
  const noteDismissed = Object.entries(dismissed).filter(([_, item]) =>
    currentNotePath && (item.sourcePath === currentNotePath || item.targetPath === currentNotePath)
  );

  if (noteDismissed.length === 0) return;

  const drawer = sec.createDiv({ cls: "orbit-dismissed-drawer" });
  let isOpen = false;
  const toggleBtn = drawer.createEl("a", {
    cls: "orbit-dismissed-toggle",
    text: `▸ Show ${noteDismissed.length} dismissed`,
  });

  const listEl = drawer.createDiv({ cls: "orbit-dismissed-list orbit-hidden" });

  toggleBtn.onclick = () => {
    isOpen = !isOpen;
    toggleBtn.setText(`${isOpen ? "▾ Hide" : "▸ Show"} ${noteDismissed.length} dismissed`);
    listEl.toggleClass("orbit-hidden", !isOpen);
  };

  for (const [key, item] of noteDismissed) {
    const row = listEl.createDiv({ cls: "orbit-dismissed-row" });
    row.createSpan({ cls: "orbit-dismissed-title", text: item.targetTitle || item.targetPath });
    const restoreBtn = row.createEl("button", { cls: "orbit-btn-sm", text: "Restore" });
    restoreBtn.onclick = async () => {
      delete plugin.settings.dismissedSuggestions[key];
      await plugin.saveSettings();
      onRestore();
    };
  }
}
