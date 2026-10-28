/**
 * Pure planner for appending a link to a note's `Related` section.
 */

export const RELATED_HEADING = "Related";

export interface RelatedInsertionPlan {
  /** Character offset in the original content where `snippet` is inserted. */
  offset: number;
  /** Text to insert at `offset`. */
  snippet: string;
  /** Line of the inserted link in the resulting content (0-based). */
  linkLine: number;
  /** Column of the inserted link in the resulting content (0-based). */
  linkCh: number;
}

interface Heading {
  line: number;
  level: number;
  text: string;
}

/** Apply a planned insertion to a note's raw content. */
export function applyRelatedInsertion(
  content: string,
  plan: RelatedInsertionPlan
): string {
  return content.slice(0, plan.offset) + plan.snippet + content.slice(plan.offset);
}

/** Convert a character offset into an Obsidian editor position. */
export function offsetToPosition(
  content: string,
  offset: number
): { line: number; ch: number } {
  const clamped = Math.max(0, Math.min(offset, content.length));
  const before = content.slice(0, clamped);
  const line = before.split("\n").length - 1;
  return { line, ch: before.length - (before.lastIndexOf("\n") + 1) };
}

/** Plan an insertion of `wikilink` under the note's Related section. */
export function planRelatedInsertion(
  content: string,
  wikilink: string,
  heading: string = RELATED_HEADING
): RelatedInsertionPlan {
  const lines = content.length === 0 ? [""] : content.split("\n");
  const headings = collectHeadings(lines);
  const target = headings.find(
    (item) => item.text.toLowerCase() === heading.trim().toLowerCase()
  );

  if (!target) {
    const separator = content.length === 0
      ? ""
      : content.endsWith("\n\n")
        ? ""
        : content.endsWith("\n")
          ? "\n"
          : "\n\n";
    const snippet = `${separator}## ${heading}\n- ${wikilink}\n`;
    return buildPlan(content, content.length, snippet, wikilink);
  }

  const next = headings.find(
    (item) => item.line > target.line && item.level <= target.level
  );
  const sectionStart = target.line + 1;
  const sectionEnd = next ? next.line : lines.length;

  let last = sectionEnd - 1;
  while (last >= sectionStart && (lines[last] ?? "").trim() === "") {
    last--;
  }

  if (last < sectionStart) {
    const offset = lineStartOffset(lines, sectionStart, content.length);
    const separator =
      sectionStart >= lines.length && content.length > 0 && !content.endsWith("\n")
        ? "\n"
        : "";
    const snippet = `${separator}- ${wikilink}\n`;
    return buildPlan(content, offset, snippet, wikilink);
  }

  const lastLine = lines[last] ?? "";
  const listMatch = /^(\s*)(?:[-*+]|\d+[.)])\s+/.exec(lastLine);
  const indent = listMatch ? listMatch[1] : "";
  const insertLine = last + 1;
  const atUnterminatedEnd = insertLine >= lines.length && !content.endsWith("\n");
  const separator = listMatch ? (atUnterminatedEnd ? "\n" : "") : "\n";
  const offset = lineStartOffset(lines, insertLine, content.length);
  const snippet = `${separator}${indent}- ${wikilink}\n`;
  return buildPlan(content, offset, snippet, wikilink);
}

/** Collect ATX headings outside frontmatter and fenced code blocks. */
function collectHeadings(lines: string[]): Heading[] {
  const headings: Heading[] = [];
  let fence: { marker: string; length: number } | null = null;
  const start = bodyStartLine(lines);

  for (let i = start; i < lines.length; i++) {
    const line = lines[i] ?? "";
    const fenceMatch = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
    if (fenceMatch) {
      const marker = fenceMatch[1][0];
      const length = fenceMatch[1].length;
      if (fence === null) {
        fence = { marker, length };
      } else if (fence.marker === marker && length >= fence.length) {
        fence = null;
      }
      continue;
    }
    if (fence !== null) continue;

    const headingMatch = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (!headingMatch) continue;
    headings.push({
      line: i,
      level: headingMatch[1].length,
      text: headingMatch[2].trim(),
    });
  }

  return headings;
}

/** The first line after YAML frontmatter. */
function bodyStartLine(lines: string[]): number {
  if ((lines[0] ?? "").trim() !== "---") return 0;
  for (let i = 1; i < lines.length; i++) {
    const trimmed = (lines[i] ?? "").trim();
    if (trimmed === "---" || trimmed === "...") return i + 1;
  }
  return 1;
}

/** Character offset at which a zero-based line starts. */
function lineStartOffset(lines: string[], line: number, contentLength: number): number {
  if (line >= lines.length) return contentLength;
  let offset = 0;
  for (let i = 0; i < line; i++) {
    offset += (lines[i] ?? "").length + 1;
  }
  return offset;
}

/** Attach the inserted link's line/column to a plan. */
function buildPlan(
  content: string,
  offset: number,
  snippet: string,
  wikilink: string
): RelatedInsertionPlan {
  const linkIndex = snippet.indexOf(wikilink);
  const beforeLink =
    content.slice(0, offset) + snippet.slice(0, linkIndex < 0 ? 0 : linkIndex);
  const beforeLines = beforeLink.split("\n");
  return {
    offset,
    snippet,
    linkLine: beforeLines.length - 1,
    linkCh: beforeLines[beforeLines.length - 1].length,
  };
}
