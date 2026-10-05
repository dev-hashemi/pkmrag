"""Integration and protocol tests for Project Orbit FastMCP server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.types import CallToolResult
from typer.testing import CliRunner

from orbit.cli import app
from orbit.ingest import IngestPipeline
from orbit.mcp import create_mcp_server

runner = CliRunner()


@pytest.mark.anyio
async def test_mcp_server_initialization_and_tool_registration(tmp_path: Path) -> None:
    """Verify MCPServer registers all 5 core tools with valid schemas."""
    vault_dir = tmp_path / "test_kb"
    vault_dir.mkdir()
    (vault_dir / "Readme.md").write_text("# Readme\nWelcome to Orbit.", encoding="utf-8")

    server = create_mcp_server(vault_dir)
    assert server.name == "orbit"

    tools = await server.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "query_vault",
        "read_note",
        "list_notes",
        "list_tags",
        "search_by_tag",
        "get_outline",
        "get_note_context",
        "find_bridges",
        "vault_overview",
    }
    assert expected_tools.issubset(tool_names)

    # Test read_note tool call
    result = await server.call_tool("read_note", {"note_path": "Readme.md"})
    assert isinstance(result, CallToolResult)
    assert not result.is_error
    assert len(result.content) > 0
    text_val = result.content[0].text  # type: ignore[union-attr]
    assert "Welcome to Orbit." in text_val

    # Test list_notes tool call
    list_res = await server.call_tool("list_notes", {})
    assert isinstance(list_res, CallToolResult)
    assert "Readme.md" in list_res.content[0].text  # type: ignore[union-attr]

    # Test get_outline tool call
    outline_res = await server.call_tool("get_outline", {"note_path": "Readme.md"})
    assert isinstance(outline_res, CallToolResult)
    assert "Readme" in outline_res.content[0].text  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_mcp_server_query_vault_integration(tmp_path: Path) -> None:
    """Verify query_vault tool integrates with SearchService after ingestion."""
    vault = tmp_path / "vault"
    vault.mkdir()
    doc_text = "# Graph Retrieval\nHybrid search combines vectors and graph."
    (vault / "Doc.md").write_text(doc_text, encoding="utf-8")

    pipeline = IngestPipeline(vault, target="all")
    pipeline.run()

    server = create_mcp_server(vault)
    result = await server.call_tool("query_vault", {"query": "Graph Retrieval", "mode": "hybrid"})
    assert isinstance(result, CallToolResult)
    assert not result.is_error
    text_val = result.content[0].text  # type: ignore[union-attr]
    assert "Doc.md" in text_val


def test_cli_mcp_config(tmp_path: Path) -> None:
    """Verify orbit mcp-config CLI outputs valid JSON configuration."""
    vault = tmp_path / "sample_vault"
    vault.mkdir()

    res = runner.invoke(app, ["mcp-config", str(vault)])
    assert res.exit_code == 0
    assert "Claude Desktop / Cursor Configuration" in res.output
    assert "opencode mcp add orbit" in res.output

    # Find and parse JSON block from output
    json_start = res.output.find("{")
    json_end = res.output.rfind("}") + 1
    assert json_start != -1 and json_end > json_start

    cfg = json.loads(res.output[json_start:json_end])
    assert "mcpServers" in cfg
    assert "orbit" in cfg["mcpServers"]
    orbit_cfg = cfg["mcpServers"]["orbit"]
    assert orbit_cfg["command"] == "uv"
    assert "serve" in orbit_cfg["args"]
    assert str(vault.resolve()) in orbit_cfg["args"]


def test_cli_mcp_config_sse(tmp_path: Path) -> None:
    """Verify orbit mcp-config --transport sse outputs valid SSE configuration."""
    vault = tmp_path / "sample_vault"
    vault.mkdir()

    res = runner.invoke(app, ["mcp-config", str(vault), "--transport", "sse", "--port", "3747"])
    assert res.exit_code == 0
    assert "SSE Configuration" in res.output

    json_start = res.output.find("{")
    json_end = res.output.rfind("}") + 1
    cfg = json.loads(res.output[json_start:json_end])
    assert "mcpServers" in cfg
    assert "orbit" in cfg["mcpServers"]
    orbit_cfg = cfg["mcpServers"]["orbit"]
    assert orbit_cfg["url"] == "http://127.0.0.1:3747/sse"
