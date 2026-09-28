"""Graph traversal and proximity queries for LadybugDB."""

from __future__ import annotations

from typing import Any


def _get_single_result(res: Any) -> Any:
    return res[0] if isinstance(res, list) else res


def _extract_row(row: Any) -> list[Any]:
    if isinstance(row, dict):
        return list(row.values())
    return list(row)


def resolve_note_path(conn: Any, identifier: str) -> str | None:
    """Resolve an identifier (full path, filename, or title) to a note path in the graph."""
    # 1. Exact match on path
    res = conn.execute("MATCH (n:Note {path: $p}) RETURN n.path LIMIT 1;", {"p": identifier})
    query_res = _get_single_result(res)
    if query_res.has_next():
        row = _extract_row(query_res.get_next())
        return str(row[0])

    # 2. Case-insensitive or stripped .md match
    clean_id = identifier.removesuffix(".md").strip().lower()
    res = conn.execute("MATCH (n:Note) RETURN n.path, n.title;")
    query_res = _get_single_result(res)
    while query_res.has_next():
        row = _extract_row(query_res.get_next())
        path = str(row[0])
        title = str(row[1]) if row[1] is not None else ""
        stem = path.rsplit("/", 1)[-1].removesuffix(".md").lower()
        if stem == clean_id or title.lower() == clean_id:
            return path

    return None


def get_neighbor_hops(
    conn: Any,
    focus_path: str,
    max_hops: int = 2,
) -> dict[str, int]:
    """Find undirected graph neighbors within max_hops from focus note.

    Returns a mapping of note_path -> shortest hop distance (0 for focus note).
    """
    resolved = resolve_note_path(conn, focus_path)
    if not resolved:
        return {}

    hops: dict[str, int] = {resolved: 0}
    if max_hops < 1:
        return hops

    # 1-hop undirected neighbors
    res_1 = conn.execute(
        "MATCH (f:Note {path: $p})-[r:LINKS_TO]-(nbr:Note) RETURN DISTINCT nbr.path;",
        {"p": resolved},
    )
    query_res_1 = _get_single_result(res_1)
    while query_res_1.has_next():
        row = _extract_row(query_res_1.get_next())
        nbr_path = str(row[0])
        if nbr_path not in hops:
            hops[nbr_path] = 1

    if max_hops >= 2:
        # 2-hop undirected neighbors
        res_2 = conn.execute(
            "MATCH (f:Note {path: $p})-[*2..2]-(nbr:Note) "
            "WHERE nbr.path <> $p RETURN DISTINCT nbr.path;",
            {"p": resolved},
        )
        query_res_2 = _get_single_result(res_2)
        while query_res_2.has_next():
            row = _extract_row(query_res_2.get_next())
            nbr_path = str(row[0])
            if nbr_path not in hops:
                hops[nbr_path] = 2

    return hops


def get_graph_stats(conn: Any) -> dict[str, int]:
    """Aggregate total count metrics from the property graph."""

    def _count(query: str) -> int:
        res = conn.execute(query)
        query_res = _get_single_result(res)
        if query_res.has_next():
            row = _extract_row(query_res.get_next())
            val = row[0]
            return int(val) if val is not None else 0
        return 0

    return {
        "notes": _count("MATCH (n:Note) RETURN count(n);"),
        "unresolved_notes": _count("MATCH (n:Note {is_unresolved: true}) RETURN count(n);"),
        "tags": _count("MATCH (t:Tag) RETURN count(t);"),
        "folders": _count("MATCH (f:Folder) RETURN count(f);"),
        "links": _count("MATCH ()-[r:LINKS_TO]->() RETURN count(r);"),
        "tagged_with": _count("MATCH ()-[r:TAGGED_WITH]->() RETURN count(r);"),
        "contained_in": _count("MATCH ()-[r:NOTE_CONTAINED_IN]->() RETURN count(r);"),
    }
