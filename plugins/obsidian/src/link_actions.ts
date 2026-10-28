/**
 * Target-aware link insertion for notes referenced by the PKMRAG sidebar.
 */

import { App, Editor, MarkdownView, TFile } from "obsidian";
import { buildWikilink } from "./format";
import {
  applyRelatedInsertion,
  offsetToPosition,
  planRelatedInsertion,
} from "./related_section";

export interface RelatedLinkResult {
  /** Resolved link text without brackets, e.g. `Folder/Note`. */
  linkText: string;
  /** False when the source note already links to the target. */
  inserted: boolean;
}

/** Find the open markdown view for a note, preferring its editable instance. */
function findMarkdownView(app: App, sourcePath: string): MarkdownView | null {
  let fallback: MarkdownView | null = null;
  for (const leaf of app.workspace.getLeavesOfType("markdown")) {
    const view = leaf.view;
    if (!(view instanceof MarkdownView) || view.file?.path !== sourcePath) continue;
    if (view.getMode() === "source") return view;
    fallback ??= view;
  }
  return fallback;
}

/** Resolve a note path to a markdown file, or fail with a user-facing message. */
function getNoteFile(app: App, path: string): TFile {
  const file = app.vault.getAbstractFileByPath(path);
  if (!(file instanceof TFile)) {
    throw new Error(`Note not found: ${path}`);
  }
  return file;
}

/** Resolve a unique, folder-aware link text for the target note. */
function resolveLinkText(app: App, target: TFile, source: TFile): string {
  const linkText = app.metadataCache.fileToLinktext(target, source.path, true);
  if (!linkText) {
    throw new Error("Could not resolve a link target for this note.");
  }
  return linkText;
}

/** Whether the source note already has an outgoing link to the target. */
function hasLinkTo(app: App, source: TFile, target: TFile): boolean {
  if (app.metadataCache.resolvedLinks[source.path]?.[target.path]) return true;
  const cache = app.metadataCache.getFileCache(source);
  const refs = [...(cache?.links ?? []), ...(cache?.embeds ?? [])];
  return refs.some(
    (ref) =>
      app.metadataCache.getFirstLinkpathDest(ref.link, source.path)?.path ===
      target.path
  );
}

/** The editor for a note, but only when it is open in editing mode. */
function editableEditor(app: App, path: string): Editor | null {
  const view = findMarkdownView(app, path);
  if (!view || view.getMode() !== "source") return null;
  return view.editor ?? null;
}

/** Insert the link under the note's Related section from inside an editor. */
async function insertUnderRelated(
  app: App,
  view: MarkdownView,
  wikilink: string
): Promise<void> {
  await app.workspace.revealLeaf(view.leaf);
  const editor = view.editor;
  if (!editor) {
    throw new Error("The note switched out of editing mode. Try again.");
  }
  const content = editor.getValue();
  const plan = planRelatedInsertion(content, wikilink);
  const from = offsetToPosition(content, plan.offset);
  editor.replaceRange(plan.snippet, from);

  const cursor = { line: plan.linkLine, ch: plan.linkCh };
  const linkEnd = { line: plan.linkLine, ch: plan.linkCh + wikilink.length };
  editor.setCursor(cursor);
  editor.scrollIntoView({ from: cursor, to: linkEnd }, true);
  editor.focus();
}

/**
 * Append a link to the target under the source note's Related section.
 * Uses the note's own editor when it is open in edit mode, otherwise writes the file.
 */
export async function addRelatedLinkToNote(
  app: App,
  sourcePath: string,
  targetPath: string
): Promise<RelatedLinkResult> {
  const source = getNoteFile(app, sourcePath);
  const target = getNoteFile(app, targetPath);
  const linkText = resolveLinkText(app, target, source);

  if (hasLinkTo(app, source, target)) {
    return { linkText, inserted: false };
  }

  const wikilink = buildWikilink(linkText);
  const view = findMarkdownView(app, source.path);
  if (view && view.getMode() === "source") {
    await insertUnderRelated(app, view, wikilink);
  } else {
    await app.vault.process(source, (data) =>
      applyRelatedInsertion(data, planRelatedInsertion(data, wikilink))
    );
  }
  return { linkText, inserted: true };
}

/**
 * Insert a link at the cursor in the source note. Requires editing mode because
 * reading mode has no cursor to insert into.
 */
export function insertReferenceAtCursor(
  app: App,
  sourcePath: string,
  targetPath: string,
  anchor?: string
): string {
  const source = getNoteFile(app, sourcePath);
  const target = getNoteFile(app, targetPath);
  const editor = editableEditor(app, source.path);
  if (!editor) {
    throw new Error("Open the note in editing mode to insert a reference at the cursor.");
  }

  const wikilink = buildWikilink(resolveLinkText(app, target, source), anchor);
  if (!wikilink) {
    throw new Error("Cannot insert an empty link.");
  }
  editor.replaceSelection(wikilink);
  editor.focus();
  return wikilink;
}
