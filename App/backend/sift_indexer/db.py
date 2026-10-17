"""SQLite schema and connections. Migrations are deliberately explicit and transactional."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .intelligence_schema import SCHEMA as INTELLIGENCE_SCHEMA
from .collections_schema import SCHEMA as COLLECTIONS_SCHEMA

log = logging.getLogger(__name__)


def repair_text_blocks(connection: sqlite3.Connection) -> None:
    """Retain the newest complete block set matching the current cached text."""
    connection.execute("DELETE FROM text_blocks WHERE file_id NOT IN (SELECT file_id FROM documents)")
    for document in list(connection.execute("SELECT file_id,text FROM documents")):
        blocks = list(connection.execute(
            "SELECT position,location,text FROM text_blocks WHERE file_id=? ORDER BY id", (document['file_id'],)
        ))
        selected = []
        text = document['text']
        if text:
            length = 0
            for index in range(len(blocks) - 1, -1, -1):
                length += len(blocks[index]['text']) + (2 if index < len(blocks) - 1 else 0)
                if length >= len(text):
                    candidate = blocks[index:]
                    if length == len(text) and '\n\n'.join(block['text'] for block in candidate) == text:
                        selected = [(block['position'], block['location'], block['text']) for block in candidate]
                    break
            if not selected or len({block[0] for block in selected}) != len(selected):
                # Preserve the authoritative text if a legacy block set cannot be recovered.
                selected = [(0, 'Recovered cached text', text)]
        connection.execute("DELETE FROM text_blocks WHERE file_id=?", (document['file_id'],))
        connection.executemany("INSERT INTO text_blocks(file_id,position,location,text) VALUES (?,?,?,?)",
                               [(document['file_id'], *block) for block in selected])
    connection.execute("CREATE UNIQUE INDEX text_blocks_file_position ON text_blocks(file_id,position)")


def index_case_insensitive_paths(connection: sqlite3.Connection) -> None:
    # A non-unique index preserves existing records and case-sensitive platforms.
    connection.execute("CREATE INDEX files_path_nocase ON files(path COLLATE NOCASE)")
    collisions = connection.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM files GROUP BY path COLLATE NOCASE HAVING COUNT(*)>1)"
    ).fetchone()[0]
    if collisions:
        log.warning("Preserved %s case-insensitive path collision groups; exact spellings are preferred", collisions)


MIGRATIONS = [
    """
    CREATE TABLE roots (
        id INTEGER PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        state TEXT NOT NULL CHECK(state IN ('active', 'paused', 'removed')),
        added_at TEXT NOT NULL,
        last_scan_at TEXT,
        last_error TEXT
    );
    CREATE TABLE files (
        id INTEGER PRIMARY KEY,
        root_id INTEGER NOT NULL REFERENCES roots(id),
        path TEXT NOT NULL UNIQUE,
        filename TEXT NOT NULL,
        extension TEXT NOT NULL,
        size INTEGER,
        modified_ns INTEGER,
        content_hash TEXT,
        status TEXT NOT NULL CHECK(status IN ('indexed', 'error', 'missing', 'excluded')),
        error TEXT,
        indexed_at TEXT,
        discovered_at TEXT NOT NULL,
        duplicate_of INTEGER REFERENCES files(id)
    );
    CREATE INDEX files_root_status ON files(root_id, status);
    CREATE INDEX files_hash ON files(content_hash);
    CREATE TABLE path_history (
        id INTEGER PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES files(id),
        old_path TEXT NOT NULL,
        new_path TEXT NOT NULL,
        moved_at TEXT NOT NULL
    );
    CREATE TABLE documents (
        file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        text TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        parser_version INTEGER NOT NULL
    );
    CREATE TABLE text_blocks (
        id INTEGER PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        location TEXT,
        text TEXT NOT NULL
    );
    CREATE INDEX text_blocks_file ON text_blocks(file_id);
    CREATE TABLE parser_warnings (
        id INTEGER PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        message TEXT NOT NULL
    );
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY,
        root_id INTEGER REFERENCES roots(id),
        state TEXT NOT NULL CHECK(state IN ('queued', 'running', 'done', 'cancelled', 'failed')),
        source TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        total INTEGER NOT NULL DEFAULT 0,
        processed INTEGER NOT NULL DEFAULT 0,
        created INTEGER NOT NULL DEFAULT 0,
        changed INTEGER NOT NULL DEFAULT 0,
        moved INTEGER NOT NULL DEFAULT 0,
        unchanged INTEGER NOT NULL DEFAULT 0,
        missing INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0,
        skipped INTEGER NOT NULL DEFAULT 0,
        current_path TEXT,
        error TEXT
    );
    CREATE TABLE job_errors (
        id INTEGER PRIMARY KEY,
        job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        path TEXT NOT NULL,
        code TEXT NOT NULL,
        message TEXT NOT NULL
    );
    CREATE VIRTUAL TABLE documents_fts USING fts5(title, text, content='documents', content_rowid='file_id');
    CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
        INSERT INTO documents_fts(rowid, title, text) VALUES (new.file_id, new.title, new.text);
    END;
    CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
        INSERT INTO documents_fts(documents_fts, rowid, title, text) VALUES ('delete', old.file_id, old.title, old.text);
    END;
    CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
        INSERT INTO documents_fts(documents_fts, rowid, title, text) VALUES ('delete', old.file_id, old.title, old.text);
        INSERT INTO documents_fts(rowid, title, text) VALUES (new.file_id, new.title, new.text);
    END;
    """,
    repair_text_blocks,
    index_case_insensitive_paths,
    INTELLIGENCE_SCHEMA,
    COLLECTIONS_SCHEMA,
]

SCHEMA_VERSION = len(MIGRATIONS)


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """Open, transact, and close one connection with rollback on exceptions."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)")
            applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            for version, script in enumerate(MIGRATIONS, start=1):
                if version in applied:
                    continue
                if isinstance(script, str):
                    # executescript commits implicitly; the script owns its transaction.
                    connection.executescript(
                        "BEGIN IMMEDIATE;\n" + script +
                        f"\nINSERT INTO schema_migrations(version) VALUES ({version});\nCOMMIT;"
                    )
                else:
                    connection.execute("BEGIN IMMEDIATE")
                    script(connection)
                    connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
                    connection.commit()

