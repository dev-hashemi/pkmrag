"""LadybugDB openCypher schema definitions and DDL statements."""

from __future__ import annotations

SCHEMA_DDL_STATEMENTS: list[str] = [
    # Node Tables
    """
    CREATE NODE TABLE IF NOT EXISTS Note(
        path STRING,
        title STRING,
        hash STRING,
        mtime DOUBLE,
        is_unresolved BOOLEAN,
        PRIMARY KEY(path)
    );
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Tag(
        name STRING,
        PRIMARY KEY(name)
    );
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Folder(
        path STRING,
        name STRING,
        PRIMARY KEY(path)
    );
    """,
    # Relationship Tables
    """
    CREATE REL TABLE IF NOT EXISTS LINKS_TO(
        FROM Note TO Note,
        anchor STRING,
        alias STRING,
        is_embed BOOLEAN
    );
    """,
    """
    CREATE REL TABLE IF NOT EXISTS TAGGED_WITH(
        FROM Note TO Tag
    );
    """,
    """
    CREATE REL TABLE IF NOT EXISTS NOTE_CONTAINED_IN(
        FROM Note TO Folder
    );
    """,
    """
    CREATE REL TABLE IF NOT EXISTS FOLDER_CONTAINED_IN(
        FROM Folder TO Folder
    );
    """,
]
