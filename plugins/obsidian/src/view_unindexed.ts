/**
 * Friendly unindexed onboarding view rendered when PKMRAG daemon is connected but vault is not yet indexed.
 */

import { Notice, setIcon } from "obsidian";
import type OrbitInsightsPlugin from "./main";

export function renderUnindexedView(
  container: HTMLElement,
  plugin: OrbitInsightsPlugin,
  onIndex: () => void
): void {
  const wrapper = container.createDiv({ cls: "orbit-offline-container orbit-unindexed-container" });

  const iconEl = wrapper.createDiv({ cls: "orbit-offline-icon" });
  setIcon(iconEl, "pkmrag-ribbon");

  wrapper.createEl("h3", { text: "Vault Not Indexed Yet", cls: "orbit-offline-title" });

  wrapper.createEl("p", {
    cls: "orbit-offline-desc",
    text: "PKMRAG is connected, but your vault has not been indexed into LadybugDB and LanceDB yet. Index notes to build graph relationships, semantic vector search, and AI discovery.",
  });

  const btnRow = wrapper.createDiv({ cls: "orbit-offline-actions" });
  const indexBtn = btnRow.createEl("button", {
    cls: "orbit-btn-sm mod-cta",
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
    cls: "orbit-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };
}
