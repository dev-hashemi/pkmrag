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

  wrapper.createEl("h3", { text: "Vault Setup & Initial Indexing", cls: "pkmrag-offline-title" });

  wrapper.createEl("p", {
    cls: "pkmrag-offline-desc",
    text: "PKMRAG is connected, but your vault has not been indexed yet. Initial setup will build your LadybugDB graph and download the local BAAI/bge-small-en-v1.5 embedding model (~130 MB, runs 100% on-device via ONNX with zero API fees) for semantic vector search.",
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
      new Notice("PKMRAG: Indexing started (downloading embedding model in background)...");
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
