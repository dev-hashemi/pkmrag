"""Hierarchical Markdown heading chunker with breadcrumb context preservation."""

from __future__ import annotations

import re

from pkmrag.models import ChunkMetadata

HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*)$")
FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


class HierarchicalMarkdownChunker:
    """Chunks Markdown text by heading hierarchy with breadcrumb context."""

    def __init__(
        self,
        min_tokens: int = 40,
        max_tokens: int = 500,
        overlap_tokens: int = 30,
    ) -> None:
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count based on whitespace-delimited words."""
        return max(1, len(text.split()))

    def _strip_frontmatter(self, content: str) -> tuple[str, int]:
        """Strip YAML frontmatter and return (cleaned_text, offset)."""
        match = FRONTMATTER_REGEX.match(content)
        if match:
            offset = match.end()
            return content[offset:], offset
        return content, 0

    def chunk_document(
        self,
        note_path: str,
        note_title: str,
        content: str,
    ) -> list[ChunkMetadata]:
        """Split a Markdown document into contextual heading chunks."""
        cleaned_content, base_offset = self._strip_frontmatter(content)
        if not cleaned_content.strip():
            return []

        raw_sections = self._extract_raw_sections(cleaned_content, note_title, base_offset)
        merged_sections = self._merge_micro_sections(raw_sections)

        chunks: list[ChunkMetadata] = []
        chunk_idx = 0

        for heading, body, start_char, end_char in merged_sections:
            token_count = self._estimate_tokens(body)
            if token_count <= self.max_tokens:
                chunk_text = f"{heading}\n\n{body}".strip() if heading else body.strip()
                chunks.append(
                    ChunkMetadata(
                        chunk_id=f"{note_path}#chunk_{chunk_idx}",
                        note_path=note_path,
                        note_title=note_title,
                        heading=heading,
                        text=chunk_text,
                        chunk_index=chunk_idx,
                        token_count=self._estimate_tokens(chunk_text),
                        start_char=start_char,
                        end_char=end_char,
                    )
                )
                chunk_idx += 1
            else:
                sub_chunks = self._split_large_section(
                    note_path=note_path,
                    note_title=note_title,
                    heading=heading,
                    body=body,
                    start_char=start_char,
                    start_index=chunk_idx,
                )
                chunks.extend(sub_chunks)
                chunk_idx += len(sub_chunks)

        return chunks

    def _extract_raw_sections(
        self,
        content: str,
        default_title: str,
        base_offset: int,
    ) -> list[tuple[str, str, int, int]]:
        """Parse text into sections defined by heading levels."""
        lines = content.splitlines(keepends=True)
        sections: list[tuple[str, str, int, int]] = []

        breadcrumbs: list[tuple[int, str]] = [(1, default_title)]
        current_body_lines: list[str] = []
        section_start_char = base_offset
        current_char_offset = base_offset

        for line in lines:
            line_len = len(line)
            match = HEADING_REGEX.match(line.strip())

            if match:
                # Flush previous section
                body_text = "".join(current_body_lines).strip()
                if body_text:
                    heading_str = self._format_breadcrumbs(breadcrumbs)
                    sections.append(
                        (heading_str, body_text, section_start_char, current_char_offset)
                    )

                level = len(match.group(1))
                title = match.group(2).strip()

                # Adjust breadcrumb hierarchy
                breadcrumbs = [b for b in breadcrumbs if b[0] < level]
                breadcrumbs.append((level, title))

                current_body_lines = []
                section_start_char = current_char_offset
            else:
                current_body_lines.append(line)

            current_char_offset += line_len

        # Flush final section
        body_text = "".join(current_body_lines).strip()
        if body_text:
            heading_str = self._format_breadcrumbs(breadcrumbs)
            sections.append((heading_str, body_text, section_start_char, current_char_offset))

        return sections

    def _format_breadcrumbs(self, breadcrumbs: list[tuple[int, str]]) -> str:
        """Format stack of (level, title) into readable breadcrumb."""
        parts: list[str] = []
        for level, title in breadcrumbs:
            prefix = "#" * level
            parts.append(f"{prefix} {title}")
        return " > ".join(parts)

    def _merge_micro_sections(
        self,
        sections: list[tuple[str, str, int, int]],
    ) -> list[tuple[str, str, int, int]]:
        """Merge adjacent sections that are below the min token threshold."""
        if not sections:
            return []

        merged: list[tuple[str, str, int, int]] = []
        curr_heading, curr_body, curr_start, curr_end = sections[0]

        for next_heading, next_body, next_start, next_end in sections[1:]:
            curr_tokens = self._estimate_tokens(curr_body)
            # If current body is small, merge into next section
            if curr_tokens < self.min_tokens:
                combined_body = f"{curr_body}\n\n{next_body}".strip()
                # Retain the more specific or next heading if relevant
                curr_heading = next_heading if next_heading else curr_heading
                curr_body = combined_body
                curr_end = next_end
            else:
                merged.append((curr_heading, curr_body, curr_start, curr_end))
                curr_heading, curr_body, curr_start, curr_end = (
                    next_heading,
                    next_body,
                    next_start,
                    next_end,
                )

        merged.append((curr_heading, curr_body, curr_start, curr_end))
        return merged

    def _split_large_section(
        self,
        note_path: str,
        note_title: str,
        heading: str,
        body: str,
        start_char: int,
        start_index: int,
    ) -> list[ChunkMetadata]:
        """Split a large section into multiple sub-chunks on paragraph boundaries."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        chunks: list[ChunkMetadata] = []

        curr_parts: list[str] = []
        curr_tokens = 0
        chunk_idx = start_index

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)
            if curr_tokens + para_tokens > self.max_tokens and curr_parts:
                sub_body = "\n\n".join(curr_parts)
                full_text = f"{heading}\n\n{sub_body}".strip() if heading else sub_body
                chunks.append(
                    ChunkMetadata(
                        chunk_id=f"{note_path}#chunk_{chunk_idx}",
                        note_path=note_path,
                        note_title=note_title,
                        heading=heading,
                        text=full_text,
                        chunk_index=chunk_idx,
                        token_count=self._estimate_tokens(full_text),
                        start_char=start_char,
                        end_char=start_char + len(sub_body),
                    )
                )
                chunk_idx += 1
                curr_parts = [para]
                curr_tokens = para_tokens
            else:
                curr_parts.append(para)
                curr_tokens += para_tokens

        if curr_parts:
            sub_body = "\n\n".join(curr_parts)
            full_text = f"{heading}\n\n{sub_body}".strip() if heading else sub_body
            chunks.append(
                ChunkMetadata(
                    chunk_id=f"{note_path}#chunk_{chunk_idx}",
                    note_path=note_path,
                    note_title=note_title,
                    heading=heading,
                    text=full_text,
                    chunk_index=chunk_idx,
                    token_count=self._estimate_tokens(full_text),
                    start_char=start_char,
                    end_char=start_char + len(sub_body),
                )
            )

        return chunks
