/**
 * Live Progress Banner rendered in Orbit Insights sidebar when background tasks run.
 */

import { ActiveJobState } from "./types";

export function renderProgressBanner(
  container: HTMLElement,
  job: ActiveJobState
): HTMLElement {
  const banner = container.createDiv({ cls: "orbit-progress-banner" });

  const headerRow = banner.createDiv({ cls: "orbit-progress-header" });
  const icon = job.type === "discover" ? "🧠" : "🔄";
  const titleText = job.type === "discover" ? "AI Gap Discovery" : "Vault Indexing";

  const titleWrapper = headerRow.createDiv({ cls: "orbit-progress-title-wrapper" });
  titleWrapper.createSpan({ cls: "orbit-progress-icon", text: icon });
  titleWrapper.createSpan({ cls: "orbit-progress-title", text: titleText });

  const pct = Math.min(100, Math.max(0, job.percent));
  headerRow.createSpan({ cls: "orbit-progress-pct", text: `${pct}%` });

  // Progress Bar Track & Fill
  const track = banner.createDiv({ cls: "orbit-progress-track" });
  const fill = track.createDiv({ cls: "orbit-progress-fill" });
  const widthVal = `${pct}%`;
  fill.style.width = widthVal;

  // Subtitle / Phase info
  const detailRow = banner.createDiv({ cls: "orbit-progress-detail" });
  let label = job.message || job.desc || "";
  if (!label && job.phase) {
    label = `${job.phase} (${job.cur}/${job.total})`;
  }
  detailRow.createSpan({ cls: "orbit-progress-text", text: label || "Processing..." });

  return banner;
}
