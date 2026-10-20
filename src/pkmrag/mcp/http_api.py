"""Read-only REST endpoints for vault context, semantic gaps, search, and overview."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pkmrag.discovery import GapDiscoveryEngine
from pkmrag.graph.paths import get_note_structural_context, get_vault_overview
from pkmrag.graph.traversal import get_inferred_relationships

if TYPE_CHECKING:
    from pkmrag.mcp.server_state import ServerState


def register_api_routes(
    app: Starlette,
    vault_path: Path,
    server_state: ServerState,
    token: str = "",
) -> None:
    """Register read-only query endpoints.

    Handlers that do not read a request body are plain ``def`` so Starlette runs them
    in a worker thread instead of blocking the event loop (and the SSE stream) while
    a scan is running.
    """

    def health_handler(request: Request) -> Response:
        return JSONResponse(server_state.get_health_status(token_enabled=bool(token)))

    def context_handler(request: Request) -> Response:
        note_path = request.query_params.get("note_path", "").strip()
        if not note_path:
            return JSONResponse({"error": "Missing 'note_path' query parameter."}, status_code=400)
        if not server_state.is_indexed() or server_state.graph_store is None:
            return JSONResponse(
                {
                    "error": "VAULT_UNINDEXED",
                    "message": "Graph store is unavailable. Vault has not been indexed yet.",
                },
                status_code=503,
            )

        ctx = get_note_structural_context(server_state.graph_store.conn, note_path)
        if ctx is None:
            return JSONResponse(
                {
                    "error": "NOTE_NOT_FOUND",
                    "message": f"Note '{note_path}' was not found in graph.",
                },
                status_code=404,
            )

        ctx.inferred_relationships = get_inferred_relationships(
            server_state.graph_store.conn, ctx.path
        )
        return JSONResponse(ctx.model_dump())

    def gaps_handler(request: Request) -> Response:
        if not server_state.is_indexed() or server_state.graph_store is None:
            return JSONResponse(
                {
                    "error": "VAULT_UNINDEXED",
                    "message": "Vault has not been indexed yet.",
                },
                status_code=503,
            )

        note_path = request.query_params.get("note_path", "").strip()
        threshold = float(request.query_params.get("threshold", "0.80"))
        limit = max(1, int(request.query_params.get("limit", "10")))

        started = time.perf_counter()
        engine = GapDiscoveryEngine(vault_path, graph_store=server_state.graph_store)
        try:
            # A note-scoped sweep costs O(chunks in that note) instead of O(vault).
            candidates = engine.find_gap_candidates(
                min_similarity=threshold,
                focus_path=note_path or None,
            )
            # Enrich only the visible subset: hop distance requires a graph query per pair.
            candidates = engine.enrich_candidates(candidates[:limit])
        finally:
            engine.close()

        return JSONResponse(
            {
                "candidates": [c.model_dump() for c in candidates],
                "total": len(candidates),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )

    async def search_handler(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON request body."}, status_code=400)

        query = body.get("query", "").strip()
        if not query:
            return JSONResponse({"error": "Query cannot be empty."}, status_code=400)
        if not server_state.is_indexed() or server_state.search_service is None:
            return JSONResponse(
                {
                    "error": "VAULT_UNINDEXED",
                    "message": "Search service is unavailable. Vault is unindexed.",
                },
                status_code=503,
            )

        results = await run_in_threadpool(
            server_state.search_service.search,
            query=query,
            near=body.get("near"),
            mode=body.get("mode", "hybrid"),
            limit=int(body.get("limit", 5)),
            folder=body.get("folder"),
            tags=body.get("tags"),
        )
        return JSONResponse({"results": [r.model_dump() for r in results], "count": len(results)})

    def overview_handler(request: Request) -> Response:
        if not server_state.is_indexed() or server_state.graph_store is None:
            return JSONResponse(
                {
                    "error": "VAULT_UNINDEXED",
                    "message": "Graph store is unavailable. Vault unindexed.",
                },
                status_code=503,
            )
        limit = int(request.query_params.get("limit", "10"))
        overview = get_vault_overview(server_state.graph_store.conn, limit=limit)
        return JSONResponse(overview.model_dump())

    app.add_route("/health", health_handler, methods=["GET"])
    app.add_route("/api/v1/context", context_handler, methods=["GET"])
    app.add_route("/api/v1/gaps", gaps_handler, methods=["GET"])
    app.add_route("/api/v1/overview", overview_handler, methods=["GET"])
    app.add_route("/api/v1/search", search_handler, methods=["POST"])
