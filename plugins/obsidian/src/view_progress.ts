/**
 * Live Progress & Error Presentation rendered in PKMRAG Insights sidebar.
 */

import type PkmragPlugin from "./main";
import { ActiveJobState, TaskErrorState } from "./types";

/** Stage reported by the server while the embedding model weights are transferred. */
const MODEL_DOWNLOAD_STAGE = "model_download";

/**
 * Decide whether the job is currently downloading the embedding model.
 *
 * Prefers the structured stage reported by the server and only falls back to
 * the phase text for servers that predate the stage field.
 */
export function isModelDownload(job: ActiveJobState): boolean {
  if (job.stage) return job.stage === MODEL_DOWNLOAD_STAGE;
  const phaseLower = (job.phase || "").toLowerCase();
  return phaseLower.includes("model") || phaseLower.includes("download");
}

/** Report whether the job reports byte-based progress. */
export function hasByteProgress(job: ActiveJobState): boolean {
  return job.unit === "bytes" && job.total > 0;
}

/** Format a byte count for display. */
export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 MB";
  const megabytes = value / (1024 * 1024);
  if (megabytes >= 1) return `${megabytes.toFixed(1)} MB`;
  return `${Math.round(value / 1024)} KB`;
}

/** Render the detail line of a job, preferring byte progress when available. */
export function jobDetail(job: ActiveJobState, fallback: string): string {
  if (hasByteProgress(job)) {
    return `${formatBytes(job.cur)} / ${formatBytes(job.total)}`;
  }
  if (job.message) return job.message;
  if (job.phase) return `${job.phase} (${job.cur}/${job.total})`;
  return fallback;
}

export function renderProgressBanner(
  container: HTMLElement,
  job: ActiveJobState
): HTMLElement {
  const banner = container.createDiv({ cls: "pkmrag-progress-banner" });

  const headerRow = banner.createDiv({ cls: "pkmrag-progress-header" });
  const isModel = isModelDownload(job);
  const bytes = hasByteProgress(job);
  const icon = job.type === "discover" ? "🧠" : isModel ? "📥" : "🔄";
  const titleText = job.type === "discover"
    ? "AI Gap Discovery"
    : isModel
    ? "Downloading Embedding Model"
    : "Vault Indexing";

  const titleWrapper = headerRow.createDiv({ cls: "pkmrag-progress-title-wrapper" });
  titleWrapper.createSpan({ cls: "pkmrag-progress-icon", text: icon });
  titleWrapper.createSpan({ cls: "pkmrag-progress-title", text: titleText });

  const pct = Math.min(100, Math.max(0, job.percent));
  headerRow.createSpan({
    cls: "pkmrag-progress-pct",
    text: isModel ? (bytes ? `${pct}%` : "Downloading (~67 MB)") : `${pct}%`,
  });

  const track = banner.createDiv({ cls: "pkmrag-progress-track" });
  const fill = track.createDiv({ cls: "pkmrag-progress-fill" });
  if (isModel && !bytes) {
    track.addClass("pkmrag-progress-indeterminate");
  } else {
    fill.style.width = `${pct}%`;
  }

  const detailRow = banner.createDiv({ cls: "pkmrag-progress-detail" });
  detailRow.createSpan({
    cls: "pkmrag-progress-text",
    text: jobDetail(job, "Processing..."),
  });

  return banner;
}

export function renderJobProgressView(
  container: HTMLElement,
  plugin: PkmragPlugin,
  job: ActiveJobState
): void {
  const wrapper = container.createDiv({ cls: "pkmrag-offline-container" });
  const card = wrapper.createDiv({ cls: "pkmrag-progress-card" });

  const isModel = isModelDownload(job);
  const bytes = hasByteProgress(job);
  const isDisc = job.type === "discover";

  const iconText = isDisc ? "🧠" : isModel ? "📥" : "🔄";
  const titleText = isDisc
    ? "AI Relationship Discovery"
    : isModel
    ? "Downloading Local Embedding Model"
    : "Vault Indexing & Property Graph";

  const descText = isDisc
    ? "Discovering semantic gaps and inferring cross-note conceptual connections."
    : isModel
    ? "Downloading the BAAI/bge-small-en-v1.5 embedding model weights (~67 MB). This is a one-time download — vector search runs 100% locally on your machine with zero cloud dependencies or API fees."
    : "Parsing markdown notes, building the LadybugDB graph, and generating dense vector embeddings in LanceDB.";

  const header = card.createDiv({ cls: "pkmrag-progress-header" });
  const titleWrapper = header.createDiv({ cls: "pkmrag-progress-title-wrapper" });
  titleWrapper.createSpan({ cls: "pkmrag-progress-icon", text: iconText });
  titleWrapper.createEl("h3", { cls: "pkmrag-progress-card-title", text: titleText });

  const pct = Math.min(100, Math.max(0, job.percent));
  header.createSpan({
    cls: "pkmrag-progress-pct",
    text: isModel
      ? bytes
        ? `Step 1/2: ${pct}%`
        : "Step 1/2: Downloading"
      : isDisc
      ? `${pct}%`
      : `Step 2/2: ${pct}%`,
  });

  card.createEl("p", { cls: "pkmrag-progress-card-desc", text: descText });

  const track = card.createDiv({ cls: "pkmrag-progress-track" });
  const fill = track.createDiv({ cls: "pkmrag-progress-fill" });
  if (isModel && !bytes) {
    track.addClass("pkmrag-progress-indeterminate");
  } else {
    fill.style.width = `${pct}%`;
  }

  const detailRow = card.createDiv({ cls: "pkmrag-progress-detail" });
  detailRow.createSpan({
    cls: "pkmrag-progress-text",
    text: jobDetail(job, isModel ? "Streaming ONNX weights to local cache..." : "Processing in background..."),
  });

  const hint = card.createDiv({ cls: "pkmrag-wizard-hint" });
  hint.setText(
    isModel
      ? "⚡ One-time download: weights are saved to your local cache so future launches are instant."
      : "⚡ Local background process active. Insights will appear automatically upon completion."
  );
}

export function renderTaskErrorCard(
  container: HTMLElement,
  plugin: PkmragPlugin,
  error: TaskErrorState,
  onRetry: () => void
): void {
  const wrapper = container.createDiv({ cls: "pkmrag-offline-container" });
  const card = wrapper.createDiv({ cls: "pkmrag-progress-card pkmrag-error-card" });

  const header = card.createDiv({ cls: "pkmrag-progress-header" });
  const titleWrapper = header.createDiv({ cls: "pkmrag-progress-title-wrapper" });
  titleWrapper.createSpan({ cls: "pkmrag-progress-icon", text: "⚠️" });
  titleWrapper.createEl("h3", {
    cls: "pkmrag-progress-card-title",
    text: error.type === "discover" ? "Discovery Error" : "Vault Indexing Failed",
  });

  const errBox = card.createDiv({ cls: "pkmrag-error-box" });
  errBox.setText(error.message);

  const lower = error.message.toLowerCase();
  const isNet = ["connect", "timeout", "network", "huggingface", "download", "dns", "getaddrinfo", "ssl", "offline", "unreachable", "urlopen"].some((k) => lower.includes(k));

  if (isNet) {
    const netHint = card.createDiv({ cls: "pkmrag-installer-desc" });
    netHint.setText(
      "Network problem detected: PKMRAG could not reach the model repository to download the local embedding model (BAAI/bge-small-en-v1.5). Please verify your internet connection or proxy settings and retry."
    );
  }

  const actions = card.createDiv({ cls: "pkmrag-offline-actions" });
  const retryBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm mod-cta",
    text: "🔄 Retry Indexing",
  });
  retryBtn.onclick = () => {
    retryBtn.setText("Retrying...");
    retryBtn.setAttribute("disabled", "true");
    plugin.lastTaskError = null;
    onRetry();
  };

  const dismissBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Dismiss",
  });
  dismissBtn.onclick = () => {
    plugin.lastTaskError = null;
    plugin.refreshActiveView();
  };

  const settingsBtn = actions.createEl("button", {
    cls: "pkmrag-btn-sm",
    text: "Settings",
  });
  settingsBtn.onclick = () => {
    (plugin.app as any).setting?.open?.();
    (plugin.app as any).setting?.openTabById?.(plugin.manifest.id);
  };
}

export async function retryFailedTask(plugin: PkmragPlugin, render: () => void): Promise<void> {
  try {
    plugin.lastTaskError = null;
    plugin.activeJob = {
      type: "ingest",
      stage: "scan",
      unit: "items",
      phase: "initializing",
      cur: 0,
      total: 100,
      percent: 0,
      message: "Retrying vault indexing...",
    };
    plugin.updateStatusBar();
    render();
    await plugin.client.autoDiscoverVaultToken(plugin.app);
    plugin.initEventStream();
    await plugin.client.triggerIngest({ rebuild: true });
    await plugin.syncJobState();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    plugin.lastTaskError = {
      type: "ingest",
      message: msg,
      timestamp: new Date(),
    };
    render();
  }
}
