/**
 * Status bar presentation and SSE background event handling for Orbit Insights.
 */

import { Notice } from "obsidian";
import type OrbitInsightsPlugin from "./main";
import { VIEW_TYPE_ORBIT_INSIGHTS, OrbitInsightsView } from "./view";

export function renderStatusBar(
  statusBarEl: HTMLElement,
  plugin: OrbitInsightsPlugin
): void {
  statusBarEl.empty();
  statusBarEl.onclick = () => plugin.activateView();

  if (!plugin.isServerConnected) {
    if (!plugin.daemonManager.isBinaryAvailable()) {
      statusBarEl.createSpan({ text: "⚪ PKMRAG: Setup Required", cls: "orbit-status-setup" });
      statusBarEl.setAttribute("title", "PKMRAG engine is not installed. Click to open setup wizard.");
      return;
    }
    statusBarEl.createSpan({ text: "🔴 PKMRAG: Offline", cls: "orbit-status-disconnected" });
    statusBarEl.setAttribute("title", "PKMRAG daemon is offline. Click to open panel.");
    return;
  }

  if (plugin.activeJob) {
    const isDisc = plugin.activeJob.type === "discover";
    const icon = isDisc ? "🧠" : "🔄";
    const name = isDisc ? "Discovering" : "Indexing";
    const pct = Math.min(100, Math.max(0, plugin.activeJob.percent));
    statusBarEl.createSpan({
      text: `${icon} PKMRAG: ${name} (${pct}%)`,
      cls: "orbit-status-busy",
    });
    const desc = plugin.activeJob.message || plugin.activeJob.desc || plugin.activeJob.phase;
    statusBarEl.setAttribute("title", `PKMRAG ${name}: ${desc} (${pct}%)`);
    return;
  }

  if (!plugin.isVaultIndexed) {
    statusBarEl.createSpan({ text: "⚠️ PKMRAG: Unindexed", cls: "orbit-status-warning" });
    statusBarEl.setAttribute("title", "Vault not indexed. Click to open setup.");
    return;
  }

  statusBarEl.createSpan({ text: "🟢 PKMRAG: Ready", cls: "orbit-status-connected" });
  statusBarEl.setAttribute("title", "PKMRAG is ready. Click to open panel.");
}

export function setupEventStream(plugin: OrbitInsightsPlugin): EventSource | null {
  return plugin.client.connectEvents((event, data) => {
    const activeFile = plugin.app.workspace.getActiveFile();
    if (event === "ingest_progress") {
      plugin.activeJob = {
        type: "ingest",
        phase: String(data.phase || "indexing"),
        cur: Number(data.cur || 0),
        total: Number(data.total || 100),
        percent: Number(data.percent || 0),
        message: String(data.message || ""),
      };
      plugin.updateStatusBar();
      notifySidebar(plugin);
    } else if (event === "discover_progress") {
      plugin.activeJob = {
        type: "discover",
        phase: String(data.phase || "discovery"),
        cur: Number(data.cur || 0),
        total: Number(data.total || 100),
        percent: Number(data.percent || 0),
        desc: String(data.desc || ""),
      };
      plugin.updateStatusBar();
      notifySidebar(plugin);
    } else if (event === "ingest_complete") {
      plugin.activeJob = null;
      plugin.isVaultIndexed = true;
      plugin.updateStatusBar();
      new Notice("PKMRAG: Vault indexing complete.");
      plugin.refreshActiveView();
    } else if (event === "discover_complete") {
      plugin.activeJob = null;
      plugin.updateStatusBar();
      new Notice(`PKMRAG: AI Discovery finished (${data.inferred_count ?? 0} relationships).`);
      plugin.refreshActiveView();
    } else if (event === "ingest_error" || event === "discover_error") {
      plugin.activeJob = null;
      plugin.updateStatusBar();
      new Notice(`PKMRAG task failed: ${data.message ?? "Error"}`);
      plugin.refreshActiveView();
    } else if (activeFile) {
      if (event === "reindex") {
        const reindexed = data.note_path as string;
        if (reindexed && activeFile.path.endsWith(reindexed)) {
          plugin.refreshActiveView(activeFile.path);
        }
      } else if (event === "sync") {
        plugin.refreshActiveView(activeFile.path);
      }
    }
  });
}

function notifySidebar(plugin: OrbitInsightsPlugin): void {
  const leaves = plugin.app.workspace.getLeavesOfType(VIEW_TYPE_ORBIT_INSIGHTS);
  if (leaves.length > 0) {
    (leaves[0].view as OrbitInsightsView).render();
  }
}
