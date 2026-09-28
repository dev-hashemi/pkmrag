"""Embedded LadybugDB graph storage engine implementation."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import ladybug

from orbit.graph.schema import SCHEMA_DDL_STATEMENTS


def _get_single_result(res: Any) -> Any:
    return res[0] if isinstance(res, list) else res


def _extract_row(row: Any) -> list[Any]:
    if isinstance(row, dict):
        return list(row.values())
    return list(row)


class GraphStore:
    """Manages LadybugDB lifecycle, transactions, and openCypher graph operations."""

    def __init__(self, db_path: Path | str, rebuild: bool = False) -> None:
        target_path = Path(db_path).resolve()
        if target_path.is_dir() or target_path.suffix != ".ladybug":
            self.db_dir = target_path
            self.db_path = self.db_dir / "orbit.ladybug"
        else:
            self.db_path = target_path
            self.db_dir = self.db_path.parent

        if rebuild and self.db_dir.exists():
            for p in self.db_dir.glob("orbit.ladybug*"):
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db = ladybug.Database(str(self.db_path))
        self.conn = ladybug.Connection(self.db)
        self._init_schema()

    def _init_schema(self) -> None:
        """Execute DDL statements to ensure all tables exist."""
        for statement in SCHEMA_DDL_STATEMENTS:
            self.conn.execute(statement)

    def get_all_notes(self) -> dict[str, dict[str, Any]]:
        """Retrieve all currently tracked notes from the graph."""
        res = self.conn.execute("MATCH (n:Note) RETURN n.path, n.hash, n.mtime, n.is_unresolved;")
        query_res = _get_single_result(res)
        notes: dict[str, dict[str, Any]] = {}
        while query_res.has_next():
            row = _extract_row(query_res.get_next())
            path = str(row[0])
            notes[path] = {
                "hash": str(row[1]) if row[1] is not None else "",
                "mtime": float(row[2]) if row[2] is not None else 0.0,
                "is_unresolved": bool(row[3]),
            }
        return notes

    def upsert_folder(self, folder_path: str, name: str) -> None:
        """Upsert a single folder node."""
        norm_path = folder_path.strip("/")
        self.conn.execute(
            "MERGE (f:Folder {path: $p}) ON CREATE SET f.name = $n ON MATCH SET f.name = $n;",
            {"p": norm_path, "n": name},
        )

    def upsert_folder_hierarchy(self, folder_path: str) -> None:
        """Recursively ensure all ancestor folders and FOLDER_CONTAINED_IN edges exist."""
        norm_path = folder_path.strip("/")
        if not norm_path or norm_path == ".":
            return

        parts = PurePosixPath(norm_path).parts
        current = ""
        prev = ""

        for part in parts:
            current = f"{current}/{part}".lstrip("/") if current else part
            self.upsert_folder(current, part)
            if prev:
                self.conn.execute(
                    "MATCH (sub:Folder {path: $s}), (parent:Folder {path: $p}) "
                    "MERGE (sub)-[:FOLDER_CONTAINED_IN]->(parent);",
                    {"s": current, "p": prev},
                )
            prev = current

    def upsert_note(
        self,
        path: str,
        title: str,
        content_hash: str,
        mtime: float,
        is_unresolved: bool = False,
    ) -> None:
        """Upsert a Note node with properties."""
        self.conn.execute(
            "MERGE (n:Note {path: $p}) "
            "ON CREATE SET n.title = $t, n.hash = $h, n.mtime = $m, n.is_unresolved = $u "
            "ON MATCH SET n.title = $t, n.hash = $h, n.mtime = $m, n.is_unresolved = $u;",
            {
                "p": path,
                "t": title,
                "h": content_hash,
                "m": mtime,
                "u": is_unresolved,
            },
        )

    def add_note_contained_in(self, note_path: str, folder_path: str) -> None:
        """Create NOTE_CONTAINED_IN relationship between note and folder."""
        norm_folder = folder_path.strip("/")
        if not norm_folder or norm_folder == ".":
            return
        self.upsert_folder_hierarchy(norm_folder)
        self.conn.execute(
            "MATCH (n:Note {path: $np}), (f:Folder {path: $fp}) "
            "MERGE (n)-[:NOTE_CONTAINED_IN]->(f);",
            {"np": note_path, "fp": norm_folder},
        )

    def upsert_tag(self, tag_name: str) -> None:
        """Upsert a Tag node."""
        clean_name = tag_name.lstrip("#").strip()
        if not clean_name:
            return
        self.conn.execute(
            "MERGE (t:Tag {name: $name});",
            {"name": clean_name},
        )

    def add_tagged_with(self, note_path: str, tag_name: str) -> None:
        """Associate a note with a tag."""
        clean_name = tag_name.lstrip("#").strip()
        if not clean_name:
            return
        self.upsert_tag(clean_name)
        self.conn.execute(
            "MATCH (n:Note {path: $np}), (t:Tag {name: $tn}) MERGE (n)-[:TAGGED_WITH]->(t);",
            {"np": note_path, "tn": clean_name},
        )

    def add_links_to(
        self,
        from_path: str,
        to_path: str,
        anchor: str = "",
        alias: str = "",
        is_embed: bool = False,
        to_title: str = "",
    ) -> None:
        """Create a LINKS_TO relationship, ensuring target note exists."""
        target_title = to_title or PurePosixPath(to_path).stem
        # Ensure target note exists (if new, initialize as unresolved ghost note)
        self.conn.execute(
            "MERGE (b:Note {path: $p}) "
            "ON CREATE SET b.title = $t, b.hash = '', b.mtime = 0.0, b.is_unresolved = true;",
            {"p": to_path, "t": target_title},
        )

        # Merge relationship with properties
        self.conn.execute(
            "MATCH (a:Note {path: $src}), (b:Note {path: $dst}) "
            "MERGE (a)-[r:LINKS_TO {anchor: $anc, alias: $al, is_embed: $emb}]->(b);",
            {
                "src": from_path,
                "dst": to_path,
                "anc": anchor,
                "al": alias,
                "emb": is_embed,
            },
        )

    def delete_outgoing_edges(self, note_path: str) -> None:
        """Remove all outgoing relationships for a given note."""
        self.conn.execute(
            "MATCH (n:Note {path: $p})-[r:LINKS_TO]->() DELETE r;",
            {"p": note_path},
        )
        self.conn.execute(
            "MATCH (n:Note {path: $p})-[r:TAGGED_WITH]->() DELETE r;",
            {"p": note_path},
        )
        self.conn.execute(
            "MATCH (n:Note {path: $p})-[r:NOTE_CONTAINED_IN]->() DELETE r;",
            {"p": note_path},
        )

    def handle_deleted_note(self, note_path: str) -> None:
        """Handle a note deleted from disk.

        Removes outgoing edges. If other notes link to it, demotes it to a ghost note;
        otherwise, removes the note node completely.
        """
        self.delete_outgoing_edges(note_path)

        # Check if any incoming links exist
        res = self.conn.execute(
            "MATCH ()-[r:LINKS_TO]->(n:Note {path: $p}) RETURN count(r);",
            {"p": note_path},
        )
        query_res = _get_single_result(res)
        incoming_count = 0
        if query_res.has_next():
            row = _extract_row(query_res.get_next())
            incoming_count = int(row[0]) if row and row[0] is not None else 0

        if incoming_count > 0:
            # Keep as ghost note
            self.conn.execute(
                "MATCH (n:Note {path: $p}) SET n.is_unresolved = true, n.hash = '', n.mtime = 0.0;",
                {"p": note_path},
            )
        else:
            # Completely remove
            self.conn.execute(
                "MATCH (n:Note {path: $p}) DELETE n;",
                {"p": note_path},
            )

    def reconcile_ghost_notes(self, real_path: str) -> None:
        """Migrate dangling incoming links from matching ghost notes to a newly created note."""
        stem = PurePosixPath(real_path).stem.lower()
        res = self.conn.execute("MATCH (g:Note {is_unresolved: true}) RETURN g.path;")
        query_res = _get_single_result(res)
        ghost_paths_to_migrate: list[str] = []
        while query_res.has_next():
            row = _extract_row(query_res.get_next())
            gp = str(row[0])
            if gp != real_path and PurePosixPath(gp).stem.lower() == stem:
                ghost_paths_to_migrate.append(gp)

        for gp in ghost_paths_to_migrate:
            self.conn.execute(
                "MATCH (src:Note)-[r:LINKS_TO]->(ghost:Note {path: $gp}), "
                "(real:Note {path: $rp}) "
                "MERGE (src)-[:LINKS_TO {"
                "anchor: r.anchor, alias: r.alias, is_embed: r.is_embed"
                "}]->(real) "
                "DELETE r;",
                {"gp": gp, "rp": real_path},
            )
            self.conn.execute(
                "MATCH (ghost:Note {path: $gp}) DELETE ghost;",
                {"gp": gp},
            )

    def cleanup_orphaned_tags(self) -> None:
        """Remove tags that are no longer referenced by any notes."""
        self.conn.execute("MATCH (t:Tag) WHERE NOT (t)<-[:TAGGED_WITH]-(:Note) DELETE t;")

    def get_stats(self) -> dict[str, int]:
        """Aggregate total count metrics from the property graph."""

        def _count(query: str) -> int:
            res = self.conn.execute(query)
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

    def close(self) -> None:
        """Close LadybugDB connection."""
        if hasattr(self, "conn") and not self.conn.is_closed:
            self.conn.close()

    def __enter__(self) -> GraphStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
