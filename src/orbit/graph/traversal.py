"""Graph traversal and proximity queries for LadybugDB."""

from __future__ import annotations

from typing import Any

from orbit.models import InferredRelationship


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

    clamped_hops = max(1, min(max_hops, 5))
    hops: dict[str, int] = {resolved: 0}

    for h in range(1, clamped_hops + 1):
        res = conn.execute(
            f"MATCH (f:Note {{path: $p}})-[:LINKS_TO* {h}..{h}]-(nbr:Note) "
            "WHERE nbr.path <> $p RETURN DISTINCT nbr.path;",
            {"p": resolved},
        )
        query_res = _get_single_result(res)
        while query_res.has_next():
            row = _extract_row(query_res.get_next())
            nbr_path = str(row[0])
            if nbr_path not in hops:
                hops[nbr_path] = h

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


def get_all_tags(conn: Any, limit: int = 50) -> list[dict[str, Any]]:
    """Return all tags with note counts, ordered by frequency."""
    clamped = max(1, min(limit, 200))
    res = conn.execute(
        "MATCH (n:Note)-[:TAGGED_WITH]->(t:Tag) "
        "RETURN t.name, count(n) AS cnt "
        "ORDER BY cnt DESC LIMIT $lim;",
        {"lim": clamped},
    )
    query_res = _get_single_result(res)
    tags: list[dict[str, Any]] = []
    while query_res.has_next():
        row = _extract_row(query_res.get_next())
        tags.append({"tag": str(row[0]), "notes_count": int(row[1])})
    return tags


def get_notes_by_tag(conn: Any, tag: str, limit: int = 50) -> list[dict[str, str]]:
    """Return notes tagged with a specific tag."""
    clean_tag = tag.strip().lstrip("#")
    clamped = max(1, min(limit, 500))
    res = conn.execute(
        "MATCH (n:Note)-[:TAGGED_WITH]->(t:Tag {name: $tag}) "
        "RETURN n.path, n.title "
        "ORDER BY n.path LIMIT $lim;",
        {"tag": clean_tag, "lim": clamped},
    )
    query_res = _get_single_result(res)
    notes: list[dict[str, str]] = []
    while query_res.has_next():
        row = _extract_row(query_res.get_next())
        notes.append({"path": str(row[0]), "title": str(row[1]) if row[1] else ""})
    return notes


def has_inferred_relationship(conn: Any, source_path: str, target_path: str) -> bool:
    """Check if an inferred relationship exists between two notes in either direction."""
    res = conn.execute(
        "MATCH (a:Note {path: $src})-[r:INFERRED_REL]-(b:Note {path: $dst}) RETURN count(r);",
        {"src": source_path, "dst": target_path},
    )
    query_res = _get_single_result(res)
    if query_res.has_next():
        row = _extract_row(query_res.get_next())
        return int(row[0]) > 0
    return False


def add_inferred_relationship(conn: Any, rel: InferredRelationship) -> None:
    """Persist an AI-discovered relationship edge between two notes."""
    conn.execute(
        "MATCH (a:Note {path: $src}), (b:Note {path: $dst}) "
        "MERGE (a)-[r:INFERRED_REL {rel_type: $rt}]->(b) "
        "ON CREATE SET r.confidence = $conf, r.reason = $rsn, r.model = $mdl, r.created_at = $cat;",
        {
            "src": rel.source_path,
            "dst": rel.target_path,
            "rt": rel.rel_type,
            "conf": float(rel.confidence),
            "rsn": rel.reason,
            "mdl": rel.model,
            "cat": rel.created_at,
        },
    )


def get_inferred_relationships(conn: Any, note_path: str) -> list[InferredRelationship]:
    """Retrieve all AI-discovered relationships connected to a note (undirected)."""
    clean = resolve_note_path(conn, note_path)
    if not clean:
        return []

    res = conn.execute(
        "MATCH (a:Note {path: $p})-[r:INFERRED_REL]-(b:Note) "
        "RETURN a.path, b.path, r.rel_type, r.confidence, r.reason, r.model, r.created_at;",
        {"p": clean},
    )
    query_res = _get_single_result(res)
    results: list[InferredRelationship] = []
    while query_res.has_next():
        row = _extract_row(query_res.get_next())
        results.append(
            InferredRelationship(
                source_path=str(row[0]),
                target_path=str(row[1]),
                rel_type=str(row[2]),
                confidence=float(row[3]),
                reason=str(row[4]),
                model=str(row[5]),
                created_at=str(row[6]),
            )
        )
    return results
