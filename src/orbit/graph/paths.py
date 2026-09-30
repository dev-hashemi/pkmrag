"""Pathfinding, structural context, and overview queries for LadybugDB."""

from __future__ import annotations

from typing import Any

from orbit.graph.traversal import (
    _extract_row,
    _get_single_result,
    get_graph_stats,
    get_neighbor_hops,
    resolve_note_path,
)
from orbit.models import GraphBridge, NoteContext, VaultOverview


def find_shortest_bridge(
    conn: Any,
    source_id: str,
    target_id: str,
    max_hops: int = 5,
) -> GraphBridge:
    """Find the shortest connection path between two notes in the knowledge graph."""
    src_path = resolve_note_path(conn, source_id)
    dst_path = resolve_note_path(conn, target_id)

    if not src_path or not dst_path:
        return GraphBridge(
            source=source_id,
            target=target_id,
            found=False,
            hops=-1,
            path=[],
        )

    if src_path == dst_path:
        return GraphBridge(
            source=source_id,
            target=target_id,
            found=True,
            hops=0,
            path=[src_path],
        )

    clamped_hops = max(1, min(max_hops, 10))
    query = (
        f"MATCH p = (a:Note {{path: $src}})-[:LINKS_TO* SHORTEST 1..{clamped_hops}]-"
        "(b:Note {path: $dst}) RETURN nodes(p) LIMIT 1;"
    )

    try:
        res = conn.execute(query, {"src": src_path, "dst": dst_path})
        query_res = _get_single_result(res)
        if query_res.has_next():
            row = _extract_row(query_res.get_next())
            nodes_list = row[0] if row else []
            path_nodes: list[str] = []
            for n in nodes_list:
                if isinstance(n, dict):
                    node_path = str(n.get("path") or n.get("name") or "")
                else:
                    node_path = str(getattr(n, "path", getattr(n, "name", "")))
                if node_path:
                    path_nodes.append(node_path)

            if path_nodes:
                return GraphBridge(
                    source=source_id,
                    target=target_id,
                    found=True,
                    hops=len(path_nodes) - 1,
                    path=path_nodes,
                )
    except Exception:
        pass

    return GraphBridge(
        source=source_id,
        target=target_id,
        found=False,
        hops=-1,
        path=[],
    )


def get_note_structural_context(conn: Any, note_id: str) -> NoteContext | None:
    """Retrieve detailed graph context (links, backlinks, tags, 2-hop cluster) for a note."""
    resolved = resolve_note_path(conn, note_id)
    if not resolved:
        return None

    title = resolved.rsplit("/", 1)[-1].removesuffix(".md")
    is_unresolved = False
    res_info = conn.execute(
        "MATCH (n:Note {path: $p}) RETURN n.title, n.is_unresolved LIMIT 1;",
        {"p": resolved},
    )
    q_info = _get_single_result(res_info)
    if q_info.has_next():
        row_info = _extract_row(q_info.get_next())
        if row_info[0]:
            title = str(row_info[0])
        if row_info[1] is not None:
            is_unresolved = bool(row_info[1])

    outgoing: list[str] = []
    res_out = conn.execute(
        "MATCH (a:Note {path: $p})-[:LINKS_TO]->(b:Note) RETURN DISTINCT b.path;",
        {"p": resolved},
    )
    q_out = _get_single_result(res_out)
    while q_out.has_next():
        row = _extract_row(q_out.get_next())
        outgoing.append(str(row[0]))

    backlinks: list[str] = []
    res_in = conn.execute(
        "MATCH (b:Note)-[:LINKS_TO]->(a:Note {path: $p}) RETURN DISTINCT b.path;",
        {"p": resolved},
    )
    q_in = _get_single_result(res_in)
    while q_in.has_next():
        row = _extract_row(q_in.get_next())
        backlinks.append(str(row[0]))

    tags: list[str] = []
    res_tags = conn.execute(
        "MATCH (a:Note {path: $p})-[:TAGGED_WITH]->(t:Tag) RETURN DISTINCT t.name;",
        {"p": resolved},
    )
    q_tags = _get_single_result(res_tags)
    while q_tags.has_next():
        row = _extract_row(q_tags.get_next())
        tags.append(str(row[0]))

    all_hops = get_neighbor_hops(conn, resolved, max_hops=2)
    direct_set = set(outgoing) | set(backlinks) | {resolved}
    neighbors_2hop = [p for p, hop in all_hops.items() if hop == 2 and p not in direct_set]

    return NoteContext(
        path=resolved,
        title=title,
        tags=tags,
        outgoing_links=outgoing,
        backlinks=backlinks,
        neighbors_2hop=neighbors_2hop,
        is_unresolved=is_unresolved,
    )


def get_vault_overview(conn: Any, limit: int = 10) -> VaultOverview:
    """Aggregate high-level graph statistics and central hub notes."""
    stats = get_graph_stats(conn)

    hub_notes: list[dict[str, Any]] = []
    res_hubs = conn.execute(
        "MATCH (b:Note)-[:LINKS_TO]->(a:Note) "
        "WHERE a.is_unresolved = false "
        "RETURN a.path, a.title, count(b) AS in_degree "
        "ORDER BY in_degree DESC LIMIT $limit;",
        {"limit": limit},
    )
    q_hubs = _get_single_result(res_hubs)
    while q_hubs.has_next():
        row = _extract_row(q_hubs.get_next())
        hub_notes.append(
            {
                "path": str(row[0]),
                "title": str(row[1])
                if row[1]
                else str(row[0]).rsplit("/", 1)[-1].removesuffix(".md"),
                "backlinks_count": int(row[2]),
            }
        )

    top_tags: list[dict[str, Any]] = []
    res_tags = conn.execute(
        "MATCH (n:Note)-[:TAGGED_WITH]->(t:Tag) "
        "RETURN t.name, count(n) AS note_count "
        "ORDER BY note_count DESC LIMIT $limit;",
        {"limit": limit},
    )
    q_tags = _get_single_result(res_tags)
    while q_tags.has_next():
        row = _extract_row(q_tags.get_next())
        top_tags.append(
            {
                "tag": str(row[0]),
                "notes_count": int(row[1]),
            }
        )

    return VaultOverview(
        total_notes=stats.get("notes", 0),
        resolved_notes=stats.get("notes", 0) - stats.get("unresolved_notes", 0),
        ghost_notes=stats.get("unresolved_notes", 0),
        total_links=stats.get("links", 0),
        total_tags=stats.get("tags", 0),
        hub_notes=hub_notes,
        top_tags=top_tags,
    )
