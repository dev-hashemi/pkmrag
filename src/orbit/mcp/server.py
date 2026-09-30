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
from orbit.mcp.tools_vault import (
    execute_get_outline,
    execute_list_notes,
    execute_list_tags,
    execute_search_by_tag,
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
            "note chunks, 'read_note' to fetch note content with graph context, 'list_notes' "
            "to browse files, 'list_tags' and 'search_by_tag' to navigate tags, 'get_outline' "
            "for heading structure, 'get_note_context' for backlinks, "
            "'find_bridges' for link paths, and 'vault_overview' for global hub statistics."
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
        folder: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Search the vault using hybrid (semantic + keyword) retrieval with optional graph boost.

        Args:
            query: The search query or question.
            near: Optional note path or title to boost nearby notes in the graph.
            mode: Retrieval mode ('hybrid', 'dense', or 'sparse').
            limit: Maximum number of snippet results to return (default 5, max 20).
            folder: Optional folder path prefix to restrict results (e.g. 'Plugins').
            tags: Optional list of tag names to filter results (e.g. ['api', 'guide']).
        """
        return execute_query_vault(
            search_service=search_service,
            query=query,
            near=near,
            mode=mode,
            limit=limit,
            folder=folder,
            tags=tags,
        )

    @mcp.tool()
    def read_note(
        note_path: str,
        max_chars: int = 15000,
        offset: int = 0,
    ) -> str:
        """Read the content of a note along with its immediate graph context (tags and links).

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
            graph_store=graph_store,
        )

    @mcp.tool()
    def list_notes(
        folder: Optional[str] = None,
        pattern: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        """List markdown notes in the vault with optional folder and wildcard filename filtering.

        Args:
            folder: Optional relative folder path to limit listing (e.g. 'Guides' or 'Templates').
            pattern: Optional glob pattern to match note filenames (e.g. '*plugin*.md' or 'Daily*').
            limit: Maximum number of notes to return (default 100, max 200).
        """
        return execute_list_notes(
            vault_path=vpath,
            folder=folder,
            pattern=pattern,
            limit=limit,
        )

    @mcp.tool()
    def list_tags(
        limit: int = 50,
    ) -> str:
        """List all unique tags in the vault ranked by note frequency.

        Args:
            limit: Maximum number of tags to return (default 50, max 200).
        """
        return execute_list_tags(
            graph_store=graph_store,
            limit=limit,
        )

    @mcp.tool()
    def search_by_tag(
        tag: str,
        limit: int = 50,
    ) -> str:
        """Find all notes tagged with a specific tag in the graph index.

        Args:
            tag: Tag name to search for (e.g. 'api' or '#project').
            limit: Maximum number of matching notes to return (default 50, max 500).
        """
        return execute_search_by_tag(
            graph_store=graph_store,
            tag=tag,
            limit=limit,
        )

    @mcp.tool()
    def get_outline(
        note_path: str,
    ) -> str:
        """Extract heading hierarchy and line numbers of a note to navigate large documents.

        Args:
            note_path: Relative path or filename of the note.
        """
        return execute_get_outline(
            vault_path=vpath,
            note_path=note_path,
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
