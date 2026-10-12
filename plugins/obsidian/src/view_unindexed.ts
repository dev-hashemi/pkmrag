/**
 * Friendly unindexed onboarding view rendered when PKMRAG daemon is connected but vault is not yet indexed.
 */

import { Notice, setIcon } from "obsidian";
import type PkmragPlugin from "./main";

export function renderUnindexedView(
  container: HTMLElement,
  plugin: PkmragPlugin,
  onIndex: () => void
): void {
  const wrapper = container.createDiv({ cls: "pkmrag-offline-container pkmrag-unindexed-container" });

  const iconEl = wrapper.createDiv({ cls: "pkmrag-offline-icon" });
  setIcon(iconEl, "pkmrag-ribbon");

  wrapper.createEl("h3", { text: "Vault Not Indexed Yet", cls: "pkmrag-offline-title" });

  wrapper.createEl("p", {
    cls: "pkmrag-offline-desc",
    text: "PKMRAG is connected, but your vault has not been indexed into LadybugDB and LanceDB yet. Index notes to build graph relationships, semantic vector search, and AI discovery.",
  });

  const btnRow = wrapper.createDiv({ cls: "pkmrag-offline-actions" });
  const indexBtn = btnRow.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "⚡ Index Vault Now",
  });

  indexBtn.onclick = async () => {
    indexBtn.setText("Starting indexing...");
    indexBtn.setAttribute("disabled", "true");
    try {
      new Notice("PKMRAG: Vault indexing started in background...");
      await plugin.client.triggerIngest({ rebuild: true });
      onIndex();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      new Notice(`Indexing failed: ${msg}`);
      indexBtn.setText("⚡ Index Vault Now");
      indexBtn.removeAttribute("disabled");
    }
  };

  const settingsBtn = btnRow.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };
}
