/**
 * Matching evidence & passage inspection for PKMRAG Insights sidebar.
 */

import { App, CachedMetadata, Keymap, MarkdownView } from "obsidian";

import type PkmragPlugin from "./main";
import { VIEW_TYPE_PKMRAG_INSIGHTS } from "./view";
import { ChunkPairMatch, SemanticGapCandidate } from "./types";
import {
  displayTitle,
  excerpt,
  normalizeHeading,
  searchAnchor,
  splitChunkHeading,
} from "./format";

export const EXCERPT_LENGTH_THRESHOLD = 200;

/** Attach Obsidian Page Preview core plugin hover preview to an element. */
export function attachHoverPreview(
  app: App,
  targetEl: HTMLElement,
  linktext: string,
  sourcePath: string
): void {
  if (!targetEl || typeof targetEl.addEventListener !== "function") return;
  targetEl.addEventListener("mouseover", (event: MouseEvent) => {
    app.workspace.trigger("hover-link", {
      event,
      source: VIEW_TYPE_PKMRAG_INSIGHTS,
      hoverParent: { hoverPopover: null },
      targetEl,
      linktext,
      sourcePath,
    });
  });
}

function scrollToEditor(editor: any, from: any, to: any): void {
  editor.scrollIntoView({ from, to }, true);
  if (typeof editor.setCursor === "function") editor.setCursor(from);
}

/** Locate the line offset of a section heading using metadata cache, line scan, or passage fallback. */
export function findHeadingLine(
  view: MarkdownView,
  cache: CachedMetadata | null,
  section: string,
  passage?: string
): number {
  const normSec = normalizeHeading(section);

  if (normSec) {
    // 1. Match against Obsidian's parsed heading cache
    const cached = cache?.headings?.find((h) => {
      const normH = normalizeHeading(h.heading);
      return normH === normSec || normH.includes(normSec) || normSec.includes(normH);
    });
    if (cached) return cached.position.start.line;

    // 2. Scan lines in the editor
    if (view.getMode() === "source") {
      const headingIdx = view.editor.getValue().split("\n").findIndex((line) => {
        const nl = normalizeHeading(line);
        return Boolean(nl) && (/^#+/.test(line.trim()) || line.trim().startsWith("**")) &&
          (nl === normSec || nl.includes(normSec) || normSec.includes(nl));
      });
      if (headingIdx !== -1) return headingIdx;
    }
  }

  // 3. Fallback: locate the line of the passage directly under this heading
  if (passage && view.getMode() === "source") {
    const cleanSnippet = passage.trim().slice(0, 50);
    const content = view.editor.getValue();
    const idx = cleanSnippet ? content.indexOf(cleanSnippet) : -1;
    if (idx !== -1) {
      return view.editor.offsetToPos(idx).line;
    }
  }

  return -1;
}

/**
 * Navigate to a note/heading anchor and optionally scroll to the passage in the editor.
 */
export async function navigateToEvidence(
  plugin: PkmragPlugin,
  path: string,
  heading: string | undefined,
  passage: string | undefined,
  currentNotePath: string | null,
  evt?: MouseEvent,
  preferHeading = false
): Promise<void> {
  const section = searchAnchor(heading || "");
  const newLeaf = Keymap.isModEvent(evt);

  // If opening in-place (no Cmd/Ctrl/Alt modifier): check if already open in a markdown leaf
  if (!newLeaf) {
    const leaf = plugin.app.workspace.getLeavesOfType("markdown").find((l) => {
      const v = l.view;
      if (!(v instanceof MarkdownView)) return false;
      const p = v.file?.path;
      return p === path || p === `${path}.md` || `${p}.md` === path;
    });

    if (leaf && leaf.view instanceof MarkdownView) {
      plugin.app.workspace.setActiveLeaf(leaf, { focus: true });

      // If clicking passage text specifically, scroll to passage first
      if (passage && !preferHeading && leaf.view.getMode() === "source") {
        const editor = leaf.view.editor;
        const cleanSnippet = passage.trim().slice(0, 50);
        const idx = cleanSnippet ? editor.getValue().indexOf(cleanSnippet) : -1;
        if (idx !== -1) {
          const fromPos = editor.offsetToPos(idx);
          const toPos = editor.offsetToPos(idx + cleanSnippet.length);
          scrollToEditor(editor, fromPos, toPos);
          return;
        }
      }

      // Find target heading line (with automatic passage fallback)
      const file = leaf.view.file;
      const cache = file ? plugin.app.metadataCache.getFileCache(file) : null;
      const targetLine = findHeadingLine(leaf.view, cache, section, passage);

      if (targetLine !== -1 && leaf.view.getMode() === "source") {
        const pos = { line: targetLine, ch: 0 };
        scrollToEditor(leaf.view.editor, pos, pos);
        return;
      }

      // Fallback: Use Obsidian's in-note anchor link
      if (section) {
        await plugin.app.workspace.openLinkText(`#${normalizeHeading(section)}`, path, false);
        return;
      }
      return;
    }
  }

  // If leaf is not open, or opening in a new leaf/split:
  const linkTarget = section ? `${path}#${section}` : path;
  await plugin.app.workspace.openLinkText(linkTarget, currentNotePath ?? "", newLeaf);
}

/** Render the matching passages that justify the similarity score. */
export function renderEvidence(
  card: HTMLElement,
  plugin: PkmragPlugin,
  gap: SemanticGapCandidate,
  currentNotePath: string | null
): void {
  const details = card.createEl("details", { cls: "pkmrag-evidence" });
  const matches: ChunkPairMatch[] = gap.matched_chunks?.length
    ? gap.matched_chunks
    : [{
        source_chunk_id: gap.source_chunk_id,
        target_chunk_id: gap.target_chunk_id,
        source_chunk_text: gap.source_chunk_text,
        target_chunk_text: gap.target_chunk_text,
        similarity: gap.chunk_similarity || gap.similarity,
      }];

  const simPct = Math.round((matches[0]?.similarity || gap.chunk_similarity || gap.similarity) * 100);
  const headerLabel =
    matches.length > 1
      ? `Why are these similar? (${matches.length} matching sections)`
      : `Why are these similar? (${simPct}% section match)`;

  const summary = details.createEl("summary", {
    cls: "pkmrag-evidence-summary",
    text: headerLabel,
    attr: { title: "Matching passages from both notes with section similarity scores" },
  });

  const body = details.createDiv({ cls: "pkmrag-evidence-body" });
  const initialSectionLimit = 2;
  const initialMatches = matches.slice(0, initialSectionLimit);
  const remainingMatches = matches.slice(initialSectionLimit);

  const renderMatch = (parentEl: HTMLElement, m: ChunkPairMatch, idx: number) => {
    const chunkPct = Math.round(m.similarity * 100);
    const chunkContainer = parentEl.createDiv({ cls: "pkmrag-evidence-pair" });
    const sectionTitle =
      matches.length > 1
        ? `Match ${idx + 1} · ${chunkPct}% section similarity`
        : `Section similarity: ${chunkPct}%`;

    chunkContainer.createDiv({ cls: "pkmrag-evidence-section-header", text: sectionTitle });

    const sides: Array<[string, string, string, string | undefined, string | undefined]> = [
      ["From", gap.source_path, m.source_chunk_text, m.source_heading, gap.source_title],
      ["To", gap.target_path, m.target_chunk_text, m.target_heading, gap.target_title],
    ];

    for (const [label, path, text, headingOverride, noteTitle] of sides) {
      const { heading: parsedHeading, body: passage } = splitChunkHeading(text);
      const heading = headingOverride || parsedHeading;
      const section = searchAnchor(heading);
      const isCurrent = Boolean(currentNotePath && path === currentNotePath);

      const row = chunkContainer.createDiv({
        cls: isCurrent ? "pkmrag-evidence-row pkmrag-evidence-current" : "pkmrag-evidence-row",
      });
      row.createSpan({
        cls: "pkmrag-evidence-label",
        text: isCurrent ? "This note" : label,
      });

      const noteLink = row.createEl("a", {
        cls: "pkmrag-evidence-note pkmrag-link",
        text: displayTitle(path, noteTitle),
        attr: { title: "Open note (Cmd/Ctrl for new tab)" },
      });
      noteLink.onclick = (e: MouseEvent) => {
        navigateToEvidence(plugin, path, undefined, undefined, currentNotePath, e);
      };
      attachHoverPreview(plugin.app, noteLink, path, currentNotePath ?? "");

      if (section) {
        const headingLink = row.createEl("a", {
          cls: "pkmrag-evidence-heading pkmrag-link",
          text: `# ${section}`,
          attr: { title: `Jump to #${section}` },
        });
        headingLink.onclick = (e: MouseEvent) => {
          navigateToEvidence(plugin, path, heading, passage, currentNotePath, e, true);
        };
        attachHoverPreview(plugin.app, headingLink, `${path}#${section}`, currentNotePath ?? "");
      }

      if (passage) {
        const textContainer = row.createDiv({
          cls: "pkmrag-evidence-text",
          attr: { title: "Click to jump to this passage in note" },
        });

        const isLong = passage.length > EXCERPT_LENGTH_THRESHOLD;
        const textSpan = textContainer.createSpan({
          cls: "pkmrag-evidence-text-content",
          text: isLong ? excerpt(passage, EXCERPT_LENGTH_THRESHOLD) : passage,
        });

        if (isLong) {
          const toggleBtn = textContainer.createSpan({
            cls: "pkmrag-evidence-toggle",
            text: "▾ more",
            attr: { title: "Show full passage", role: "button" },
          });

          let expanded = false;
          toggleBtn.onclick = (e: MouseEvent) => {
            e.stopPropagation();
            expanded = !expanded;
            textSpan.setText(expanded ? passage : excerpt(passage, EXCERPT_LENGTH_THRESHOLD));
            toggleBtn.setText(expanded ? "▴ less" : "▾ more");
            toggleBtn.setAttribute("title", expanded ? "Show excerpt" : "Show full passage");
          };
        }

        textContainer.onclick = (e: MouseEvent) => {
          navigateToEvidence(plugin, path, heading, passage, currentNotePath, e, false);
        };
      }
    }
  };

  initialMatches.forEach((m, idx) => renderMatch(body, m, idx));

  if (remainingMatches.length > 0) {
    const moreSectionsContainer = body.createDiv({ cls: "pkmrag-more-sections pkmrag-hidden" });
    remainingMatches.forEach((m, idx) =>
      renderMatch(moreSectionsContainer, m, initialSectionLimit + idx)
    );

    const showMoreSectionsBtn = body.createEl("button", {
      cls: "pkmrag-btn-sm pkmrag-btn-show-more",
      text: `▾ Show ${remainingMatches.length} more matching sections`,
    });
    showMoreSectionsBtn.onclick = () => {
      const isHidden = moreSectionsContainer.hasClass("pkmrag-hidden");
      moreSectionsContainer.toggleClass("pkmrag-hidden", !isHidden);
      showMoreSectionsBtn.setText(
        isHidden ? "▴ Show fewer sections" : `▾ Show ${remainingMatches.length} more matching sections`
      );
    };
  }
}
