/**
 * Live Progress Banner rendered in PKMRAG Insights sidebar when background tasks run.
 */

import { ActiveJobState } from "./types";

export function renderProgressBanner(
  container: HTMLElement,
  job: ActiveJobState
): HTMLElement {
  const banner = container.createDiv({ cls: "pkmrag-progress-banner" });

  const headerRow = banner.createDiv({ cls: "pkmrag-progress-header" });
  const phaseLower = (job.phase || "").toLowerCase();
  const isModel = phaseLower.includes("model") || phaseLower.includes("download");
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
  headerRow.createSpan({ cls: "pkmrag-progress-pct", text: `${pct}%` });

  // Progress Bar Track & Fill
  const track = banner.createDiv({ cls: "pkmrag-progress-track" });
  const fill = track.createDiv({ cls: "pkmrag-progress-fill" });
  const widthVal = `${pct}%`;
  fill.style.width = widthVal;

  // Subtitle / Phase info
  const detailRow = banner.createDiv({ cls: "pkmrag-progress-detail" });
  let label = job.message || job.desc || "";
  if (!label && job.phase) {
    label = `${job.phase} (${job.cur}/${job.total})`;
  }
  detailRow.createSpan({ cls: "pkmrag-progress-text", text: label || "Processing..." });

  return banner;
}
