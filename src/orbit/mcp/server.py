"""Model Context Protocol (MCP) server integration for Project Orbit."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from mcp.server.mcpserver import MCPServer

from orbit.config import get_default_db_dir
from orbit.graph.store import GraphStore
from orbit.mcp.tools import (
    execute_find_bridges,
    execute_get_note_context,
    execute_query_vault,
    execute_read_note,
    execute_vault_overview,
)
from orbit.search.service import SearchService


def setup_stdio_logging() -> None:
    """Ensure all logs and warnings route strictly to stderr to protect JSON-RPC on stdout."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.INFO)


def create_mcp_server(vault_path: Path | str) -> MCPServer:
    """Build and configure an MCPServer instance for the specified vault."""
    vpath = Path(vault_path).resolve()
    setup_stdio_logging()

    mcp = MCPServer(
        "orbit",
        instructions=(
            f"Orbit Knowledge Engine for vault '{vpath.name}'. Use 'query_vault' to search "
            "for relevant note chunks, 'read_note' to fetch full file content, 'get_note_context' "
            "to inspect backlinks and graph connections, 'find_bridges' to find relationship "
            "paths between notes, and 'vault_overview' to get high-level statistics and hub notes."
        ),
    )

    # Initialize read-only search service and graph store
    search_service = SearchService(vpath)
    db_dir = get_default_db_dir(vpath)
    graph_store: Optional[GraphStore] = None
    if db_dir.exists():
        try:
            graph_store = GraphStore(db_dir, read_only=True)
        except Exception as e:
            logger = logging.getLogger("orbit.mcp")
            logger.warning("Could not open graph store in read-only mode: %s", e)

    @mcp.tool()
    def query_vault(
        query: str,
        near: Optional[str] = None,
        mode: str = "hybrid",
        limit: int = 5,
    ) -> str:
        """Search the vault using hybrid (semantic + keyword) retrieval with optional graph boost.

        Args:
            query: The search query or question.
            near: Optional note path or title to boost nearby notes in the graph.
            mode: Retrieval mode ('hybrid', 'dense', or 'sparse').
            limit: Maximum number of snippet results to return (default 5, max 20).
        """
        return execute_query_vault(
            search_service=search_service,
            query=query,
            near=near,
            mode=mode,
            limit=limit,
        )

    @mcp.tool()
    def read_note(
        note_path: str,
        max_chars: int = 15000,
        offset: int = 0,
    ) -> str:
        """Read the full content of a note from the vault.

        Args:
            note_path: Relative path to the markdown file within the vault.
            max_chars: Maximum characters to read (supports pagination for large notes).
            offset: Starting character offset for paginated reading.
        """
        return execute_read_note(
            vault_path=vpath,
            note_path=note_path,
            max_chars=max_chars,
            offset=offset,
        )

    @mcp.tool()
    def get_note_context(
        note_path: str,
    ) -> str:
        """Retrieve structural graph context (outgoing links, backlinks, tags, 2-hop cluster).

        Args:
            note_path: Relative path or filename of the note to inspect.
        """
        return execute_get_note_context(
            graph_store=graph_store,
            note_path=note_path,
        )

    @mcp.tool()
    def find_bridges(
        source_note: str,
        target_note: str,
        max_hops: int = 5,
    ) -> str:
        """Find the shortest sequence of wikilinks connecting two notes across the vault.

        Args:
            source_note: Starting note path or name.
            target_note: Destination note path or name.
            max_hops: Maximum search depth (default 5, max 10).
        """
        return execute_find_bridges(
            graph_store=graph_store,
            source_note=source_note,
            target_note=target_note,
            max_hops=max_hops,
        )

    @mcp.tool()
    def vault_overview(
        limit: int = 10,
    ) -> str:
        """Get high-level statistics, central hub notes (most backlinks), and top tags.

        Args:
            limit: Number of hub notes and tags to list (default 10).
        """
        return execute_vault_overview(
            graph_store=graph_store,
            limit=limit,
        )

    return mcp
