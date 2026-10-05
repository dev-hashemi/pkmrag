"""Model Context Protocol (MCP) server integration for Project Orbit."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from mcp.server.mcpserver import MCPServer

from orbit.cache import CacheManager
from orbit.config import settings
from orbit.graph.store import GraphStore
from orbit.mcp.tools import (
    execute_find_bridges,
    execute_get_note_context,
    execute_query_vault,
    execute_read_note,
    execute_vault_overview,
)
from orbit.mcp.tools_sync import execute_reindex_note, execute_sync_vault
from orbit.mcp.tools_vault import (
    execute_discover_gaps,
    execute_get_outline,
    execute_list_notes,
    execute_list_tags,
    execute_search_by_tag,
)
from orbit.search.service import SearchService
from orbit.search.vector_store import VectorStore
from orbit.telemetry import trace_span


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

    if settings.tracing_enabled or settings.otlp_endpoint:
        from orbit.telemetry import setup_telemetry

        setup_telemetry(
            otlp_endpoint=settings.otlp_endpoint,
            otlp_headers=settings.otlp_headers,
            service_name=settings.service_name,
        )

    mcp = MCPServer(
        "orbit",
        instructions=(
            f"Orbit Knowledge Engine for vault '{vpath.name}'. Use 'query_vault' to search "
            "note chunks, 'read_note' to fetch note content with graph context, 'list_notes' "
            "to browse files, 'list_tags' and 'search_by_tag' to navigate tags, 'get_outline' "
            "for heading structure, 'get_note_context' for backlinks, "
            "'find_bridges' for link paths, 'vault_overview' for global hub statistics, "
            "'reindex_note' to update after edits, and 'sync_vault' for delta synchronization."
        ),
    )

    db_dir = settings.get_db_dir(vpath)
    vec_dir = settings.get_vector_dir(vpath)

    # Unified read-write store shared across search and synchronization
    graph_store: Optional[GraphStore] = None
    if db_dir.exists():
        try:
            graph_store = GraphStore(db_dir, read_only=False)
        except Exception as e:
            logging.getLogger("orbit.mcp").warning("Could not open graph store in RW mode: %s", e)

    vector_store = VectorStore(vec_dir) if vec_dir.exists() else None
    cache_manager = CacheManager(vpath)
    search_service = SearchService(
        vpath,
        graph_store=graph_store,
        vector_store=vector_store,
        cache_manager=cache_manager,
    )

    @mcp.tool()
    def query_vault(
        query: str,
        near: Optional[str] = None,
        mode: str = "hybrid",
        limit: int = 5,
        folder: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Search the vault using hybrid retrieval with optional graph proximity boosting."""
        with trace_span("orbit.mcp.query_vault", attributes={"query": query, "mode": mode}):
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
    def read_note(note_path: str, max_chars: int = 15000, offset: int = 0) -> str:
        """Read note content enriched with immediate graph context (tags and links)."""
        with trace_span("orbit.mcp.read_note", attributes={"note_path": note_path}):
            return execute_read_note(
                vault_path=vpath,
                note_path=note_path,
                max_chars=max_chars,
                offset=offset,
                graph_store=graph_store,
            )

    @mcp.tool()
    def list_notes(
        folder: Optional[str] = None, pattern: Optional[str] = None, limit: int = 100
    ) -> str:
        """List markdown notes in the vault with optional folder and wildcard filename filtering."""
        with trace_span("orbit.mcp.list_notes"):
            return execute_list_notes(vault_path=vpath, folder=folder, pattern=pattern, limit=limit)

    @mcp.tool()
    def list_tags(limit: int = 50) -> str:
        """List all unique tags in the vault ranked by note frequency."""
        with trace_span("orbit.mcp.list_tags"):
            return execute_list_tags(graph_store=graph_store, limit=limit)

    @mcp.tool()
    def search_by_tag(tag: str, limit: int = 50) -> str:
        """Find all notes tagged with a specific tag in the graph index."""
        with trace_span("orbit.mcp.search_by_tag", attributes={"tag": tag}):
            return execute_search_by_tag(graph_store=graph_store, tag=tag, limit=limit)

    @mcp.tool()
    def get_outline(note_path: str) -> str:
        """Extract heading hierarchy and line numbers of a note to navigate large documents."""
        with trace_span("orbit.mcp.get_outline", attributes={"note_path": note_path}):
            return execute_get_outline(vault_path=vpath, note_path=note_path)

    @mcp.tool()
    def get_note_context(note_path: str) -> str:
        """Retrieve structural graph context (outgoing links, backlinks, tags, 2-hop cluster)."""
        with trace_span("orbit.mcp.get_note_context", attributes={"note_path": note_path}):
            return execute_get_note_context(graph_store=graph_store, note_path=note_path)

    @mcp.tool()
    def find_bridges(source_note: str, target_note: str, max_hops: int = 5) -> str:
        """Find the shortest sequence of wikilinks connecting two notes across the vault."""
        with trace_span(
            "orbit.mcp.find_bridges",
            attributes={"source_note": source_note, "target_note": target_note},
        ):
            return execute_find_bridges(
                graph_store=graph_store,
                source_note=source_note,
                target_note=target_note,
                max_hops=max_hops,
            )

    @mcp.tool()
    def vault_overview(limit: int = 10) -> str:
        """Get high-level statistics, central hub notes (most backlinks), and top tags."""
        with trace_span("orbit.mcp.vault_overview"):
            return execute_vault_overview(graph_store=graph_store, limit=limit)

    @mcp.tool()
    def discover_gaps(threshold: float = 0.80, limit: int = 10) -> str:
        """Find unlinked note pairs exhibiting high semantic similarity (knowledge gaps)."""
        with trace_span("orbit.mcp.discover_gaps", attributes={"threshold": threshold}):
            return execute_discover_gaps(
                vault_path=vpath,
                graph_store=graph_store,
                threshold=threshold,
                limit=limit,
            )

    @mcp.tool()
    def reindex_note(note_path: str) -> str:
        """Incrementally re-index a single note after external edits and evict stale cache."""
        with trace_span("orbit.mcp.reindex_note", attributes={"note_path": note_path}):
            return execute_reindex_note(
                vault_path=vpath,
                note_path=note_path,
                graph_store=graph_store,
                vector_store=vector_store,
                cache_manager=cache_manager,
            )

    @mcp.tool()
    def sync_vault() -> str:
        """Scan and incrementally synchronize all modified or newly created files across vault."""
        with trace_span("orbit.mcp.sync_vault"):
            return execute_sync_vault(
                vault_path=vpath,
                graph_store=graph_store,
                vector_store=vector_store,
                cache_manager=cache_manager,
            )

    return mcp
