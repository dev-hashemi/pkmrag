/**
 * Pure presentation helpers for PKMRAG Insights. No DOM access — unit testable.
 */

import { SearchResult, SemanticGapCandidate } from "./types";

/** Strip the `.md` extension and any folder segments from a note path. */
export function noteStem(notePath: string): string {
  const withoutExt = notePath.replace(/\.md$/, "");
  const segments = withoutExt.split("/");
  return segments[segments.length - 1] || withoutExt;
}

/** Display title for a note, preferring an explicit title over the file stem. */
export function displayTitle(notePath: string, title?: string | null): string {
  if (title && title.trim().length > 0 && !title.includes("/")) {
    return title.trim();
  }
  return noteStem(notePath);
}

/** Human-readable graph distance between two notes. `hops < 0` means no path was found. */
export function formatGapDistance(hops: number): string {
  if (hops < 0) return "No path within 10 hops";
  if (hops === 0) return "Same note";
  if (hops === 1) return "1 hop away";
  return `${hops} hops away`;
}

/** The side of a gap candidate that is *not* the note currently open. */
export interface GapCounterpart {
  path: string;
  title: string;
  isCurrent: boolean;
}

/** Resolve which side of a gap candidate is the counterpart of the open note. */
export function gapCounterpart(
  candidate: SemanticGapCandidate,
  currentNotePath: string | null
): GapCounterpart {
  const isCurrent = candidate.source_path === currentNotePath;
  const path = isCurrent ? candidate.target_path : candidate.source_path;
  const title = isCurrent ? candidate.target_title : candidate.source_title;
  return { path, title: displayTitle(path, title), isCurrent };
}

/** Render a shortest bridge path as a human-readable chain. */
export function formatBridgePath(bridgePath: string[]): string {
  return bridgePath.map((p) => noteStem(p)).join(" → ");
}

/**
 * Extract the anchor from a chunk heading breadcrumb (e.g. "# Title > ## Section" -> "Section").
 * Obsidian anchors resolve on the leaf heading, never the full breadcrumb.
 */
export function searchAnchor(heading: string): string {
  if (!heading) return "";
  const segments = heading.split(/\s+>\s+/);
  const leaf = segments[segments.length - 1] ?? "";
  return leaf.replace(/^#+\s*/, "").trim();
}

/** Build an Obsidian wikilink, optionally targeting a heading anchor. */
export function buildWikilink(title: string, anchor?: string): string {
  const clean = title.trim();
  if (!clean) return "";
  const cleanAnchor = anchor ? anchor.trim() : "";
  return cleanAnchor ? `[[${clean}#${cleanAnchor}]]` : `[[${clean}]]`;
}

/** How a failed daemon request should be interpreted. */
export type RequestFailure = "unindexed" | "offline";

/** Classify a failed daemon request: the vault is unindexed, or the daemon is unreachable. */
export function classifyRequestError(message: string): RequestFailure {
  return message.includes("VAULT_UNINDEXED") ? "unindexed" : "offline";
}

/** Canonical, order-independent key for a pair of note paths. */
export function pairKey(a: string, b: string): string {
  return [a, b].sort().join("::");
}

/** Whether the user previously dismissed the link between two notes. */
export function isDismissedPair(
  dismissed: Record<string, unknown>,
  a: string,
  b: string
): boolean {
  return Boolean(
    dismissed[pairKey(a, b)] || dismissed[`${a}::${b}`] || dismissed[`${b}::${a}`]
  );
}

/** Split a chunk's leading heading breadcrumb away from its body text. */
export function splitChunkHeading(text: string): { heading: string; body: string } {
  const trimmed = text.replace(/^\s+/, "");
  if (!trimmed.startsWith("#")) {
    return { heading: "", body: trimmed };
  }
  const newline = trimmed.indexOf("\n");
  if (newline === -1) {
    return { heading: trimmed.trim(), body: "" };
  }
  return { heading: trimmed.slice(0, newline).trim(), body: trimmed.slice(newline).trim() };
}

/** Collapse whitespace and clip text to a maximum length. */
export function excerpt(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max).trimEnd()}…` : clean;
}

/** Badge text describing the graph-proximity boost applied to a search result. */
export function formatGraphBoost(result: SearchResult): string {
  if (result.graph_boost_factor <= 1.0) return "";
  const hops = result.hop_distance;
  const hopStr = hops === null || hops === undefined ? "" : ` · ${hops} hop${hops === 1 ? "" : "s"}`;
  return `⚡ ×${result.graph_boost_factor.toFixed(2)}${hopStr}`;
}
