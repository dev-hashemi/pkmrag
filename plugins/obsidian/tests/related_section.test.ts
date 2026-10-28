/**
 * Unit tests for the pure Related-section insertion planner.
 */

import test from "node:test";
import assert from "node:assert/strict";
import {
  applyRelatedInsertion,
  offsetToPosition,
  planRelatedInsertion,
} from "../src/related_section.js";

function insert(content: string, wikilink = "[[Other]]"): string {
  return applyRelatedInsertion(content, planRelatedInsertion(content, wikilink));
}

test("creates a Related section at the end of a note", () => {
  assert.equal(
    insert("# Note\n\nBody.\n"),
    "# Note\n\nBody.\n\n## Related\n- [[Other]]\n"
  );
});

test("creates a Related section in an empty note", () => {
  assert.equal(insert(""), "## Related\n- [[Other]]\n");
});

test("appends to an existing bullet list", () => {
  assert.equal(
    insert("# Note\n\n## Related\n- [[A]]\n"),
    "# Note\n\n## Related\n- [[A]]\n- [[Other]]\n"
  );
});

test("keeps nested list indentation", () => {
  assert.equal(
    insert("## Related\n  - [[A]]\n"),
    "## Related\n  - [[A]]\n  - [[Other]]\n"
  );
});

test("separates the bullet from prose in an existing section", () => {
  assert.equal(
    insert("## Related\nSome prose.\n"),
    "## Related\nSome prose.\n\n- [[Other]]\n"
  );
});

test("fills an empty Related section before the next heading", () => {
  assert.equal(
    insert("## Related\n\n## Next\n"),
    "## Related\n- [[Other]]\n\n## Next\n"
  );
});

test("appends before the next heading of the same level", () => {
  assert.equal(
    insert("## Related\n- [[A]]\n\n## Next\n"),
    "## Related\n- [[A]]\n- [[Other]]\n\n## Next\n"
  );
});

test("matches the heading case-insensitively", () => {
  assert.equal(
    insert("## related\n"),
    "## related\n- [[Other]]\n"
  );
});

test("handles a list ending the file without a trailing newline", () => {
  assert.equal(
    insert("## Related\n- [[A]]"),
    "## Related\n- [[A]]\n- [[Other]]\n"
  );
});

test("handles an empty Related heading at EOF without a trailing newline", () => {
  assert.equal(insert("## Related"), "## Related\n- [[Other]]\n");
});

test("ignores Related headings inside fenced code blocks", () => {
  const content = "# Note\n\n```md\n## Related\n```\n";
  assert.equal(
    insert(content),
    `${content}\n## Related\n- [[Other]]\n`
  );
});

test("keeps scanning after a fence that contains a shorter fence", () => {
  const content = [
    "# Note",
    "",
    "````md",
    "## Related",
    "```",
    "````",
    "",
    "## Related",
    "- [[A]]",
    "",
  ].join("\n");
  assert.equal(insert(content), `${content}- [[Other]]\n`);
});

test("ignores headings inside YAML frontmatter", () => {
  const content = "---\ntitle: X\n---\n## Related\n- [[A]]\n";
  assert.equal(
    insert(content),
    "---\ntitle: X\n---\n## Related\n- [[A]]\n- [[Other]]\n"
  );
});

test("computes the inserted link position in the resulting content", () => {
  const content = "Body";
  const plan = planRelatedInsertion(content, "[[Other]]");
  assert.equal(applyRelatedInsertion(content, plan), "Body\n\n## Related\n- [[Other]]\n");
  assert.deepEqual({ line: plan.linkLine, ch: plan.linkCh }, { line: 3, ch: 2 });
});

test("converts offsets at the start, middle, and end of content", () => {
  const content = "abc\ndef\n";
  assert.deepEqual(offsetToPosition(content, 0), { line: 0, ch: 0 });
  assert.deepEqual(offsetToPosition(content, 5), { line: 1, ch: 1 });
  assert.deepEqual(offsetToPosition(content, content.length), { line: 2, ch: 0 });
});
