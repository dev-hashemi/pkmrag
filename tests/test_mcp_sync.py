"""Integration tests for MCP digestion tools (reindex_note and sync_vault)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.types import CallToolResult

from pkmrag.ingest import IngestPipeline
from pkmrag.mcp import create_mcp_server


@pytest.mark.anyio
async def test_mcp_sync_tools_registered(tmp_path: Path) -> None:
    """Verify reindex_note and sync_vault are registered in MCPServer tool schema."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Init.md").write_text("# Initial", encoding="utf-8")

    server = create_mcp_server(vault)
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}

    assert "reindex_note" in tool_names
    assert "sync_vault" in tool_names


@pytest.mark.anyio
async def test_mcp_reindex_note_and_query_vault(tmp_path: Path) -> None:
    """Verify reindex_note tool immediately makes created notes searchable in query_vault."""
    vault = tmp_path / "vault"

    vault.mkdir()
    (vault / "Doc1.md").write_text("# Doc 1\nExisting documentation.", encoding="utf-8")

    pipe = IngestPipeline(vault, target="all")
    pipe.run()

    server = create_mcp_server(vault)

    # 1. External edit creates Doc2.md
    (vault / "Doc2.md").write_text(
        "# Quantum Computing\nQuantum entanglement and superposition algorithms.",
        encoding="utf-8",
    )

    # 2. Call reindex_note via MCP
    reindex_res = await server.call_tool("reindex_note", {"note_path": "Doc2.md"})
    assert isinstance(reindex_res, CallToolResult)
    assert not reindex_res.is_error
    assert "Successfully indexed" in reindex_res.content[0].text  # type: ignore[union-attr]

    # 3. Query immediately via query_vault MCP tool
    search_res = await server.call_tool(
        "query_vault", {"query": "Quantum entanglement", "mode": "hybrid"}
    )
    assert isinstance(search_res, CallToolResult)
    assert not search_res.is_error
    assert "Doc2.md" in search_res.content[0].text  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_mcp_sync_vault_tool(tmp_path: Path) -> None:
    """Verify sync_vault tool scans and synchronizes all modified notes."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Alpha.md").write_text("# Alpha\nContent.", encoding="utf-8")

    pipe = IngestPipeline(vault, target="all")
    pipe.run()

    server = create_mcp_server(vault)

    # Modify Alpha.md, add Beta.md
    (vault / "Alpha.md").write_text("# Alpha\nUpdated content.", encoding="utf-8")
    (vault / "Beta.md").write_text("# Beta\nNew note content.", encoding="utf-8")

    sync_res = await server.call_tool("sync_vault", {})
    assert isinstance(sync_res, CallToolResult)
    assert not sync_res.is_error
    text_out = sync_res.content[0].text  # type: ignore[union-attr]
    assert "Alpha.md" in text_out
    assert "Beta.md" in text_out
    assert "Vault Synchronized" in text_out
