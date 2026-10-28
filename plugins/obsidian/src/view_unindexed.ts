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
    text: "PKMRAG is running. To enable semantic concept search and auto-linking, approve downloading the lightweight local embedding model:",
  });

  const modelCard = wrapper.createDiv({ cls: "pkmrag-model-card" });
  modelCard.createDiv({ cls: "pkmrag-model-badge", text: "Local Embedding Model • FastEmbed ONNX" });

  const specs = modelCard.createDiv({ cls: "pkmrag-model-specs" });

  const r1 = specs.createDiv({ cls: "pkmrag-model-spec-row" });
  r1.createSpan({ cls: "pkmrag-model-spec-label", text: "Model Architecture" });
  r1.createSpan({ cls: "pkmrag-model-spec-val", text: "BAAI/bge-small-en-v1.5" });

  const r2 = specs.createDiv({ cls: "pkmrag-model-spec-row" });
  r2.createSpan({ cls: "pkmrag-model-spec-label", text: "One-Time Download" });
  r2.createSpan({ cls: "pkmrag-model-spec-val", text: "~67 MB (~133 MB uncompressed)" });

  const r3 = specs.createDiv({ cls: "pkmrag-model-spec-row" });
  r3.createSpan({ cls: "pkmrag-model-spec-label", text: "Privacy & Network" });
  r3.createSpan({ cls: "pkmrag-model-spec-val", text: "100% On-Device • Zero Cloud API" });

  const actions = wrapper.createDiv({ cls: "pkmrag-offline-actions" });
  const indexFullBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "📥 Download Model & Index Vault (67 MB)",
  });

  const startJob = async (target: "all" | "graph") => {
    indexFullBtn.setAttribute("disabled", "true");
    indexGraphBtn.setAttribute("disabled", "true");
    plugin.lastTaskError = null;
    plugin.activeJob = {
      type: "ingest",
      stage: target === "all" ? "model_download" : "graph",
      unit: target === "all" ? "bytes" : "items",
      phase:
        target === "all"
          ? "Downloading local embedding model (BAAI/bge-small-en-v1.5)..."
          : "indexing graph",
      cur: 0,
      total: target === "all" ? 0 : 100,
      percent: 0,
      message:
        target === "all"
          ? "Downloading model weights (~67 MB) into local cache..."
          : "Indexing LadybugDB property graph...",
    };
    plugin.updateStatusBar();
    onIndex();
    try {
      await plugin.client.autoDiscoverVaultToken(plugin.app);
      plugin.initEventStream();
      await plugin.client.triggerIngest({ target, rebuild: true });
      // The first progress events can race the event stream, so read the
      // authoritative stage from the health endpoint.
      await plugin.syncJobState();
    } catch (err: unknown) {
      plugin.activeJob = null;
      plugin.updateStatusBar();
      const msg = err instanceof Error ? err.message : String(err);
      plugin.lastTaskError = {
        type: "ingest",
        message: msg,
        timestamp: new Date(),
      };
      new Notice(`Indexing failed: ${msg}`);
      onIndex();
    }
  };

  indexFullBtn.onclick = () => startJob("all");

  const indexGraphBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "⚡ Index Graph Only (0 MB)",
  });
  indexGraphBtn.setAttribute(
    "title",
    "Index links, tags, and orphans instantly with zero network download."
  );
  indexGraphBtn.onclick = () => startJob("graph");

  const settingsBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };
}

export function renderUnindexedNoteCard(
  container: HTMLElement,
  plugin: PkmragPlugin,
  notePath: string,
  onReindexed: () => Promise<void>
): void {
  const noteCard = container.createDiv({ cls: "pkmrag-card" });
  noteCard.createDiv({ cls: "pkmrag-card-target", text: "Note Not Indexed Yet" });
  noteCard.createDiv({
    cls: "pkmrag-card-reason",
    text: "This note has not been parsed into LadybugDB yet.",
  });
  const reindexBtn = noteCard.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "Index This Note",
  });
  reindexBtn.onclick = async () => {
    reindexBtn.setText("Indexing...");
    reindexBtn.setAttribute("disabled", "true");
    try {
      await plugin.client.reindexNote(notePath);
      await onReindexed();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      new Notice(`Reindex failed: ${msg}`);
      reindexBtn.setText("Index This Note");
      reindexBtn.removeAttribute("disabled");
    }
  };
}
