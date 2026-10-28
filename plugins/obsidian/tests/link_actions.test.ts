/**
 * Tests for target-aware link insertion against a fake Obsidian app.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { MarkdownView, TFile } from "obsidian";
import {
  addRelatedLinkToNote,
  insertReferenceAtCursor,
} from "../src/link_actions.js";

interface Position {
  line: number;
  ch: number;
}

interface FakeEditor {
  value: string;
  cursor: Position | null;
  scrolled: boolean;
  focused: boolean;
  replacedSelection: string | null;
  getValue(): string;
  replaceRange(text: string, from: Position): void;
  replaceSelection(text: string): void;
  setCursor(pos: Position): void;
  scrollIntoView(): void;
  focus(): void;
}

function toOffset(value: string, pos: Position): number {
  const lines = value.split("\n");
  let offset = 0;
  for (let i = 0; i < pos.line; i++) offset += (lines[i] ?? "").length + 1;
  return offset + pos.ch;
}

function fakeEditor(value: string): FakeEditor {
  const editor: FakeEditor = {
    value,
    cursor: null,
    scrolled: false,
    focused: false,
    replacedSelection: null,
    getValue: () => editor.value,
    replaceRange: (text, from) => {
      const offset = toOffset(editor.value, from);
      editor.value = editor.value.slice(0, offset) + text + editor.value.slice(offset);
    },
    replaceSelection: (text) => {
      editor.replacedSelection = text;
    },
    setCursor: (pos) => {
      editor.cursor = pos;
    },
    scrollIntoView: () => {
      editor.scrolled = true;
    },
    focus: () => {
      editor.focused = true;
    },
  };
  return editor;
}

function fakeFile(path: string): TFile {
  const file = new TFile();
  file.path = path;
  return file;
}

interface FakeAppOptions {
  files: Record<string, string>;
  views?: MarkdownView[];
  links?: Array<{ link: string }>;
  resolvedLinks?: Record<string, Record<string, number>>;
  linkText?: (target: TFile) => string;
}

function fakeApp(options: FakeAppOptions): { app: any; files: Record<string, string>; revealed: string[] } {
  const files = { ...options.files };
  const revealed: string[] = [];
  const fileMap = new Map(
    Object.keys(files).map((path) => [path, fakeFile(path)])
  );

  const app = {
    vault: {
      getAbstractFileByPath: (path: string) => fileMap.get(path) ?? null,
      process: async (file: TFile, fn: (data: string) => string) => {
        files[file.path] = fn(files[file.path] ?? "");
        return files[file.path];
      },
    },
    metadataCache: {
      resolvedLinks: options.resolvedLinks ?? {},
      fileToLinktext: (target: TFile) =>
        options.linkText ? options.linkText(target) : target.path.replace(/\.md$/, ""),
      getFileCache: () =>
        options.links ? { links: options.links.map((l) => ({ ...l, position: {} })) } : null,
      getFirstLinkpathDest: (link: string) => fileMap.get(`${link}.md`) ?? null,
    },
    workspace: {
      getLeavesOfType: () => (options.views ?? []).map((view) => ({ view })),
      revealLeaf: async (leaf: { view: MarkdownView }) => {
        revealed.push(leaf.view.file?.path ?? "");
      },
    },
  };
  return { app, files, revealed };
}

function fakeView(path: string, editor: FakeEditor | null): MarkdownView {
  const view = new MarkdownView({} as any);
  view.file = fakeFile(path);
  (view as any).editor = editor ?? undefined;
  (view as any).leaf = { view };
  (view as any).getMode = () => (editor ? "source" : "preview");
  return view;
}

const SOURCE = "Notes/Source.md";
const TARGET = "Notes/Target.md";

test("writes the link under Related when the source note is closed", async () => {
  const { app, files } = fakeApp({ files: { [SOURCE]: "# Source\n", [TARGET]: "" } });

  const result = await addRelatedLinkToNote(app, SOURCE, TARGET);

  assert.deepEqual(result, { linkText: "Notes/Target", inserted: true });
  assert.equal(files[SOURCE], "# Source\n\n## Related\n- [[Notes/Target]]\n");
  assert.equal(files[TARGET], "");
});

test("targets the source note's editor, not another open markdown view", async () => {
  const sourceEditor = fakeEditor("# Source\n");
  const otherEditor = fakeEditor("# Other\n");
  const { app, files, revealed } = fakeApp({
    files: { [SOURCE]: "# Source\n", "Notes/Other.md": "# Other\n", [TARGET]: "" },
    views: [fakeView("Notes/Other.md", otherEditor), fakeView(SOURCE, sourceEditor)],
  });

  const result = await addRelatedLinkToNote(app, SOURCE, TARGET);

  assert.equal(result.inserted, true);
  assert.equal(sourceEditor.value, "# Source\n\n## Related\n- [[Notes/Target]]\n");
  assert.equal(otherEditor.value, "# Other\n");
  assert.equal(files[SOURCE], "# Source\n");
  assert.deepEqual(revealed, [SOURCE]);
  assert.equal(sourceEditor.focused, true);
  assert.equal(sourceEditor.scrolled, true);
  assert.equal(sourceEditor.cursor?.line, 3);
});

test("writes through the vault when the source is open in reading mode", async () => {
  const { app, files } = fakeApp({
    files: { [SOURCE]: "# Source\n", [TARGET]: "" },
    views: [fakeView(SOURCE, null)],
  });

  await addRelatedLinkToNote(app, SOURCE, TARGET);

  assert.equal(files[SOURCE], "# Source\n\n## Related\n- [[Notes/Target]]\n");
});

test("does not write a duplicate link", async () => {
  const original = "## Related\n- [[Notes/Target]]\n";
  const { app, files } = fakeApp({
    files: { [SOURCE]: original, [TARGET]: "" },
    resolvedLinks: { [SOURCE]: { [TARGET]: 1 } },
  });

  const result = await addRelatedLinkToNote(app, SOURCE, TARGET);

  assert.deepEqual(result, { linkText: "Notes/Target", inserted: false });
  assert.equal(files[SOURCE], original);
});

test("detects duplicates from links when resolved links are unavailable", async () => {
  const original = "## Related\n- [[Notes/Target]]\n";
  const { app, files } = fakeApp({
    files: { [SOURCE]: original, [TARGET]: "" },
    links: [{ link: "Notes/Target" }],
  });

  const result = await addRelatedLinkToNote(app, SOURCE, TARGET);

  assert.equal(result.inserted, false);
  assert.equal(files[SOURCE], original);
});

test("inserts a reference at the cursor in the source note", () => {
  const editor = fakeEditor("Body text");
  const { app } = fakeApp({
    files: { [SOURCE]: "Body text", [TARGET]: "" },
    views: [fakeView(SOURCE, editor)],
  });

  const wikilink = insertReferenceAtCursor(app, SOURCE, TARGET, "Section");

  assert.equal(wikilink, "[[Notes/Target#Section]]");
  assert.equal(editor.replacedSelection, "[[Notes/Target#Section]]");
  assert.equal(editor.focused, true);
});

test("refuses to insert at the cursor when the source is in reading mode", () => {
  const { app } = fakeApp({
    files: { [SOURCE]: "Body text", [TARGET]: "" },
    views: [fakeView(SOURCE, null)],
  });

  assert.throws(
    () => insertReferenceAtCursor(app, SOURCE, TARGET),
    /editing mode/
  );
});
