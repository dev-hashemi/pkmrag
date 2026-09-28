"""Unit and integration tests for extensible knowledge base dialects."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from orbit.cli import app
from orbit.dialects import (
    CommonMarkDialect,
    KnowledgeDialect,
    ObsidianDialect,
    get_default_registry,
)
from orbit.ingest import IngestPipeline
from orbit.models import NoteMetadata, ResolvedLink, SourceIndex, Wikilink

runner = CliRunner()


def test_dialect_registry_basic() -> None:
    """Verify dialect registration, retrieval, and error handling."""
    reg = get_default_registry()
    names = reg.list_dialects()
    assert "obsidian" in names
    assert "commonmark" in names

    obsidian = reg.get("obsidian")
    assert isinstance(obsidian, ObsidianDialect)

    commonmark = reg.get("commonmark")
    assert isinstance(commonmark, CommonMarkDialect)

    with pytest.raises(ValueError, match="Unknown dialect 'foobar'"):
        reg.get("foobar")


def test_dialect_auto_detection(tmp_path: Path) -> None:
    """Verify auto-detection selects Obsidian for vaults and CommonMark for docs."""
    reg = get_default_registry()

    # Obsidian vault with .obsidian directory
    obsidian_vault = tmp_path / "obsidian_kb"
    (obsidian_vault / ".obsidian").mkdir(parents=True)
    detected = reg.detect(obsidian_vault)
    assert detected.name == "obsidian"

    # Obsidian Publish vault (with publish.css or site-options.json)
    publish_vault = tmp_path / "publish_kb"
    publish_vault.mkdir(parents=True)
    (publish_vault / "publish.css").write_text("body {}")
    assert reg.detect(publish_vault).name == "obsidian"

    # Generic documentation folder without .obsidian or publish files
    docs_folder = tmp_path / "generic_docs"
    docs_folder.mkdir(parents=True)
    detected_docs = reg.detect(docs_folder)
    assert detected_docs.name == "commonmark"

    # Explicit override overrides auto-detection
    override = reg.detect(obsidian_vault, preferred="commonmark")
    assert override.name == "commonmark"


def test_commonmark_dialect_strict_relative() -> None:
    """Verify CommonMark dialect enforces strict relative POSIX path resolution."""
    dialect = CommonMarkDialect()

    index = SourceIndex(
        paths_set={"docs/concepts/model.md", "docs/index.md", "readme.md"},
        lower_path_to_path={
            "docs/concepts/model.md": "docs/concepts/model.md",
            "docs/index.md": "docs/index.md",
            "readme.md": "readme.md",
        },
    )

    # Relative child resolution
    res1 = dialect.resolve_link(
        source_rel_path="docs/index.md",
        link=Wikilink(target="concepts/model.md", anchor="arch"),
        index=index,
    )
    assert res1.target_path == "docs/concepts/model.md"
    assert res1.is_unresolved is False
    assert res1.anchor == "arch"

    # Relative parent resolution
    res2 = dialect.resolve_link(
        source_rel_path="docs/concepts/model.md",
        link=Wikilink(target="../../readme.md"),
        index=index,
    )
    assert res2.target_path == "readme.md"
    assert res2.is_unresolved is False

    # Unresolved relative target
    res3 = dialect.resolve_link(
        source_rel_path="docs/index.md",
        link=Wikilink(target="missing/spec.md"),
        index=index,
    )
    assert res3.target_path == "docs/missing/spec.md"
    assert res3.is_unresolved is True


def test_custom_app_dialect_extensibility(tmp_path: Path) -> None:
    """Demonstrate how easily a new third-party app dialect can be plugged into Orbit."""

    class CustomZettelDialect:
        """Hypothetical Zettelkasten app where IDs are timestamps [[20260101]]."""

        name: str = "zettelkasten"

        def can_handle(self, root_path: Path) -> bool:
            return (root_path / ".zettel").is_dir()

        def should_ignore_dir(self, dir_name: str) -> bool:
            return dir_name.startswith(".")

        def should_ignore_file(self, file_name: str) -> bool:
            return not file_name.endswith(".md")

        def extract_document(
            self, rel_path: str, content: str, mtime: float, content_hash: str
        ) -> NoteMetadata:
            # Simple metadata extraction
            return NoteMetadata(
                path=rel_path,
                title=f"Zettel {rel_path}",
                hash=content_hash,
                mtime=mtime,
                is_unresolved=False,
                tags=["zettel"],
                links=[Wikilink(target="20260102.md", raw_text="[[20260102]]")],
            )

        def resolve_link(
            self, source_rel_path: str, link: Wikilink, index: SourceIndex
        ) -> ResolvedLink:
            # Custom resolution logic
            target = link.target
            return ResolvedLink(
                target_path=target,
                is_unresolved=target not in index.paths_set,
            )

    # Verify custom dialect satisfies KnowledgeDialect protocol
    custom = CustomZettelDialect()
    assert isinstance(custom, KnowledgeDialect)

    # Test running IngestPipeline with the custom dialect directly
    vault = tmp_path / "zettel_vault"
    vault.mkdir()
    (vault / "20260101.md").write_text("Note content")

    pipeline = IngestPipeline(vault, dialect=custom)
    stats = pipeline.run()

    assert stats.dialect == "zettelkasten"
    assert stats.notes_scanned == 1
    assert stats.notes_added == 1
    assert stats.unresolved_notes == 1  # 20260102.md is ghost
    assert stats.total_notes == 2


def test_cli_dialect_selection(tmp_path: Path) -> None:
    """Verify --dialect option in orbit ingest CLI."""
    vault = tmp_path / "cli_dialect_test"
    vault.mkdir()
    (vault / "readme.md").write_text("# Readme\n[Guide](guide.md)")
    (vault / "guide.md").write_text("# Guide")

    # Ingest using explicit commonmark dialect
    res = runner.invoke(app, ["ingest", str(vault), "--dialect", "commonmark"])
    assert res.exit_code == 0
    assert "Dialect: commonmark" in res.stdout
    assert "Ingestion successful" in res.stdout
