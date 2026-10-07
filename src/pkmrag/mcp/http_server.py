"""Starlette HTTP/SSE application serving Model Context Protocol and REST endpoints."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.types import ASGIApp

from pkmrag.config import settings
from pkmrag.discovery import GapDiscoveryEngine
from pkmrag.graph.paths import get_note_structural_context, get_vault_overview
from pkmrag.graph.traversal import get_inferred_relationships
from pkmrag.ingest import SingleNoteReindexer
from pkmrag.mcp.auth import extract_request_token, resolve_server_token, validate_token
from pkmrag.mcp.events import EventBroadcaster
from pkmrag.mcp.http_ops import register_ops_routes
from pkmrag.mcp.server import create_mcp_server
from pkmrag.mcp.server_state import ServerState

logger = logging.getLogger("pkmrag.http")
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets"


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Enforces authentication token validation on non-public endpoints."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        public_paths = {"/health", "/favicon.ico", "/favicon.svg", "/logo.svg"}
        if request.method == "OPTIONS" or request.url.path in public_paths:
            return await call_next(request)

        if not self.token:
            return await call_next(request)

        req_token = extract_request_token(request)
        if not validate_token(req_token, self.token):
            return JSONResponse(
                {
                    "error": "Unauthorized",
                    "message": "Invalid or missing PKMRAG authentication token.",
                },
                status_code=401,
            )
        return await call_next(request)


def create_http_app(
    vault_path: Path | str,
    host: str = "127.0.0.1",
    port: int = 3747,
    token: str = "",
) -> Starlette:
    """Build Starlette app with MCP SSE transport, REST APIs, CORS, and dynamic ServerState."""
    vpath = Path(vault_path).resolve()
    mcp = create_mcp_server(vpath)
    broadcaster = EventBroadcaster()
    server_state = ServerState(vpath, broadcaster)

    async def health_handler(request: Request) -> Response:
        return JSONResponse(server_state.get_health_status(token_enabled=bool(token)))

    async def context_handler(request: Request) -> Response:
        note_path = request.query_params.get("note_path", "").strip()
        if not note_path:
            return JSONResponse({"error": "Missing 'note_path' query parameter."}, status_code=400)
        if server_state.graph_store is None:
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

    async def gaps_handler(request: Request) -> Response:
        note_path = request.query_params.get("note_path", "").strip()
        threshold = float(request.query_params.get("threshold", "0.80"))
        limit = int(request.query_params.get("limit", "10"))

        engine = GapDiscoveryEngine(vpath)
        try:
            candidates, _, stats = engine.discover(
                similarity_threshold=threshold,
                limit=limit,
                dry_run=True,
            )
            if note_path:
                candidates = [
                    c
                    for c in candidates
                    if c.source_path == note_path or c.target_path == note_path
                ]
            return JSONResponse(
                {
                    "candidates": [c.model_dump() for c in candidates],
                    "total": len(candidates),
                    "duration_ms": stats.duration_ms,
                }
            )
        finally:
            engine.close()

    async def search_handler(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON request body."}, status_code=400)

        query = body.get("query", "").strip()
        if not query:
            return JSONResponse({"error": "Query cannot be empty."}, status_code=400)
        if server_state.search_service is None:
            return JSONResponse(
                {
                    "error": "VAULT_UNINDEXED",
                    "message": "Search service is unavailable. Vault is unindexed.",
                },
                status_code=503,
            )

        results = server_state.search_service.search(
            query=query,
            near=body.get("near"),
            mode=body.get("mode", "hybrid"),
            limit=int(body.get("limit", 5)),
            folder=body.get("folder"),
            tags=body.get("tags"),
        )
        return JSONResponse({"results": [r.model_dump() for r in results], "count": len(results)})

    async def reindex_handler(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON request body."}, status_code=400)

        note_path = body.get("note_path", "").strip()
        if not note_path:
            return JSONResponse({"error": "Missing 'note_path' in payload."}, status_code=400)

        reindexer = SingleNoteReindexer(
            vault_path=vpath,
            graph_store=server_state.graph_store,
            vector_store=server_state.vector_store,
            cache_manager=server_state.cache_manager,
        )
        res = reindexer.reindex_note(note_path)
        server_state.reload_stores()
        await broadcaster.broadcast("reindex", {"note_path": note_path, "status": "ok"})
        return JSONResponse(res.model_dump())

    async def sync_handler(request: Request) -> Response:
        reindexer = SingleNoteReindexer(
            vault_path=vpath,
            graph_store=server_state.graph_store,
            vector_store=server_state.vector_store,
            cache_manager=server_state.cache_manager,
        )
        results = reindexer.sync_vault_delta()
        server_state.reload_stores()
        await broadcaster.broadcast("sync", {"status": "ok", "updated_notes": len(results)})
        return JSONResponse({"results": [r.model_dump() for r in results], "count": len(results)})

    async def overview_handler(request: Request) -> Response:
        if server_state.graph_store is None:
            return JSONResponse({"error": "Graph store is unavailable."}, status_code=503)
        limit = int(request.query_params.get("limit", "10"))
        overview = get_vault_overview(server_state.graph_store.conn, limit=limit)
        return JSONResponse(overview.model_dump())

    async def events_handler(request: Request) -> Response:
        return StreamingResponse(broadcaster.subscribe(), media_type="text/event-stream")

    async def favicon_handler(request: Request) -> Response:
        ico = ASSETS_DIR / "favicon.ico"
        if not ico.is_file():
            return Response(status_code=404)
        return FileResponse(ico, media_type="image/x-icon")

    async def favicon_svg_handler(request: Request) -> Response:
        svg = ASSETS_DIR / "favicon.svg"
        if not svg.is_file():
            return Response(status_code=404)
        return FileResponse(svg, media_type="image/svg+xml")

    async def logo_handler(request: Request) -> Response:
        logo = ASSETS_DIR / "pkmrag-logo-dark.svg"
        if not logo.is_file():
            return Response(status_code=404)
        return FileResponse(logo, media_type="image/svg+xml")

    app = mcp.sse_app(host=host)
    app.add_route("/health", health_handler, methods=["GET"])
    app.add_route("/favicon.ico", favicon_handler, methods=["GET"])
    app.add_route("/favicon.svg", favicon_svg_handler, methods=["GET"])
    app.add_route("/logo.svg", logo_handler, methods=["GET"])
    app.add_route("/api/v1/context", context_handler, methods=["GET"])
    app.add_route("/api/v1/gaps", gaps_handler, methods=["GET"])
    app.add_route("/api/v1/search", search_handler, methods=["POST"])
    app.add_route("/api/v1/reindex", reindex_handler, methods=["POST"])
    app.add_route("/api/v1/sync", sync_handler, methods=["POST"])
    app.add_route("/api/v1/overview", overview_handler, methods=["GET"])
    app.add_route("/api/v1/events", events_handler, methods=["GET"])

    register_ops_routes(app, vpath, broadcaster, server_state)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TokenAuthMiddleware, token=token)
    app.state.broadcaster = broadcaster
    app.state.server_state = server_state
    return app


def run_server(
    vault_path: Path | str,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 3747,
    token: Optional[str] = None,
    no_auth: bool = False,
) -> None:
    """Start an MCP server exposing PKMRAG tools over stdio or HTTP/SSE."""
    resolved_path = Path(vault_path).resolve()
    if transport == "stdio":
        create_mcp_server(resolved_path).run(transport="stdio")
        return

    if transport in ("http", "sse"):
        import uvicorn

        from pkmrag.mcp.views import render_server_startup

        auth_token = resolve_server_token(resolved_path, cli_token=token, no_auth=no_auth)
        app = create_http_app(resolved_path, host=host, port=port, token=auth_token)
        render_server_startup(
            resolved_path, host=host, port=port, token=auth_token, no_auth=no_auth
        )
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    raise ValueError(f"Unsupported transport '{transport}'. Must be 'stdio', 'http', or 'sse'.")
