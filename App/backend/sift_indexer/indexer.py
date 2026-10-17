"""Approved-root reconciliation and durable scan jobs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import threading
import weakref
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from .db import Database
from .access import safe_path
from .parsers import IsolatedParser, MAX_INPUT_BYTES, PARSER_VERSION, SUPPORTED, parse


log = logging.getLogger(__name__)
_DEFAULT_PARSE = parse


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def file_hash(path: Path, cancelled: threading.Event, should_stop=None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if cancelled.is_set() or (should_stop is not None and should_stop()):
                raise InterruptedError("Scan cancelled")
            digest.update(chunk)
    return digest.hexdigest()


class Indexer:
    def __init__(self, db: Database):
        self.db = db
        self._guard = threading.Lock()
        self._worker: threading.Thread | None = None
        self._queue: deque[tuple[int, int | None, str]] = deque()
        self._cancel_events: dict[int, threading.Event] = {}
        self._closing = False
        # Replace the immutable set under the queue lock; readers can check it without
        # taking that lock while a database transaction is open.
        self._paused_roots: frozenset[int] = frozenset()
        self._parser = IsolatedParser()
        self._parser_finalizer = weakref.finalize(self, self._parser.close)
        with self.db.connect() as connection:
            connection.execute("UPDATE jobs SET state='failed', finished_at=?, error='Service stopped during scan' WHERE state IN ('queued','running')", (now(),))

    def roots(self) -> list[dict]:
        with self.db.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM roots WHERE state != 'removed' ORDER BY added_at")]

    def add_root(self, raw_path: str) -> dict:
        requested = Path(raw_path).absolute()
        if requested.is_symlink() or requested.resolve() != requested or not requested.is_dir():
            raise ValueError("Choose an existing folder that is not a symlink or junction")
        canonical = requested.resolve(strict=True)
        with self._guard:
            if self._closing:
                raise RuntimeError("Indexer is shutting down")
            with self.db.connect() as connection:
                for row in connection.execute("SELECT path FROM roots WHERE state != 'removed'"):
                    other = Path(row["path"])
                    if canonical != other and (contained(canonical, other) or contained(other, canonical)):
                        raise ValueError("This folder overlaps an already approved folder")
                connection.execute(
                    "INSERT INTO roots(path,state,added_at) VALUES (?,'active',?) "
                    "ON CONFLICT(path) DO UPDATE SET state='active', last_error=NULL",
                    (str(canonical), now()),
                )
                result = dict(connection.execute("SELECT * FROM roots WHERE path=?", (str(canonical),)).fetchone())
            self._paused_roots = self._paused_roots - {result["id"]}
            return result

    def set_root_state(self, root_id: int, state: str) -> dict:
        if state not in {"active", "paused", "removed"}:
            raise ValueError("Invalid folder state")
        with self._guard:
            if self._closing:
                raise RuntimeError("Indexer is shutting down")
            with self.db.connect() as connection:
                row = connection.execute("SELECT * FROM roots WHERE id=? AND state!='removed'", (root_id,)).fetchone()
                if not row:
                    raise KeyError("Folder not found")
                if state == "active":
                    self._paused_roots = self._paused_roots - {root_id}
                else:
                    self._paused_roots = self._paused_roots | {root_id}
                connection.execute("UPDATE roots SET state=? WHERE id=?", (state, root_id))
                if state == "removed":
                    hashes = [item[0] for item in connection.execute("SELECT DISTINCT content_hash FROM files WHERE root_id=? AND content_hash IS NOT NULL", (root_id,))]
                    connection.execute("UPDATE files SET status='excluded' WHERE root_id=?", (root_id,))
                    for digest in hashes:
                        self._refresh_duplicates(connection, digest)
                if state != "active":
                    retained = deque()
                    for job_id, queued_root_id, source in self._queue:
                        if queued_root_id == root_id:
                            connection.execute("UPDATE jobs SET state='cancelled', finished_at=? WHERE id=? AND state='queued'", (now(), job_id))
                        else:
                            retained.append((job_id, queued_root_id, source))
                    self._queue = retained
                return dict(connection.execute("SELECT * FROM roots WHERE id=?", (root_id,)).fetchone())

    def start_scan(self, root_id: int | None = None, source: str = "manual") -> int:
        if source not in {"manual", "watcher", "reconciliation"}:
            raise ValueError("Invalid scan source")
        with self._guard:
            if self._closing:
                raise RuntimeError("Indexer is shutting down")
            with self.db.connect() as connection:
                if root_id is not None and not connection.execute(
                    "SELECT 1 FROM roots WHERE id=? AND state='active'", (root_id,)
                ).fetchone():
                    raise ValueError("Folder is not active")
                if source != "manual":
                    pending = connection.execute(
                        "SELECT id FROM jobs WHERE root_id IS ? AND source=? AND state='queued' ORDER BY id DESC LIMIT 1",
                        (root_id, source),
                    ).fetchone()
                    if pending:
                        return int(pending["id"])
                connection.execute("INSERT INTO jobs(root_id,state,source) VALUES (?,'queued',?)", (root_id, source))
                job_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._queue.append((job_id, root_id, source))
            if self._worker is None:
                self._worker = threading.Thread(target=self._drain_queue, daemon=True, name="sift-scan-queue")
                self._worker.start()
            return job_id

    def cancel(self, job_id: int) -> bool:
        with self._guard:
            with self.db.connect() as connection:
                row = connection.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
                if not row or row["state"] not in {"queued", "running"}:
                    return False
                if row["state"] == "queued":
                    self._queue = deque(item for item in self._queue if item[0] != job_id)
                    connection.execute("UPDATE jobs SET state='cancelled', finished_at=? WHERE id=?", (now(), job_id))
                    return True
                cancelled = self._cancel_events.get(job_id)
                if cancelled is None:
                    return False
                cancelled.set()
                return True

    def close(self) -> None:
        """Stop an active parser worker when the local service shuts down."""
        with self._guard:
            self._closing = True
            for cancelled in self._cancel_events.values():
                cancelled.set()
            queued_ids = [item[0] for item in self._queue]
            self._queue.clear()
            if queued_ids:
                with self.db.connect() as connection:
                    connection.executemany(
                        "UPDATE jobs SET state='cancelled', finished_at=? WHERE id=? AND state='queued'",
                        [(now(), job_id) for job_id in queued_ids],
                    )
            worker = self._worker
        if worker and worker is not threading.current_thread():
            worker.join(timeout=5)
        self._parser.close()

    def _should_stop_root(self, root_id: int, cancelled: threading.Event) -> bool:
        return cancelled.is_set() or root_id in self._paused_roots

    def _drain_queue(self) -> None:
        while True:
            with self._guard:
                if not self._queue:
                    self._worker = None
                    return
                job_id, root_id, _source = self._queue.popleft()
                cancelled = threading.Event()
                self._cancel_events[job_id] = cancelled
                with self.db.connect() as connection:
                    connection.execute("UPDATE jobs SET state='running', started_at=? WHERE id=? AND state='queued'", (now(), job_id))
                    state = connection.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            if state == "running":
                self._run_job(job_id, root_id, cancelled)
            else:
                self._set_job_state(job_id, "cancelled")
            with self._guard:
                self._cancel_events.pop(job_id, None)

    def _set_job_state(self, job_id: int, state: str, error: str | None = None) -> None:
        with self.db.connect() as connection:
            connection.execute("UPDATE jobs SET state=?, error=COALESCE(?,error), finished_at=?, current_path=NULL WHERE id=?",
                               (state, error[:2000] if error else None, now(), job_id))

    def job(self, job_id: int) -> dict | None:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["errors"] = [dict(item) for item in connection.execute(
                "SELECT path,code,message FROM job_errors WHERE job_id=? ORDER BY id LIMIT 500", (job_id,)
            )]
            return result

    def latest_job(self) -> dict | None:
        with self.db.connect() as connection:
            row = connection.execute("SELECT id FROM jobs ORDER BY id DESC LIMIT 1").fetchone()
        return self.job(row[0]) if row else None

    def _count(self, connection, job_id: int, column: str, amount: int = 1) -> None:
        assert column in {"processed", "created", "changed", "moved", "unchanged", "missing", "failed", "skipped"}
        connection.execute(f"UPDATE jobs SET {column}={column}+? WHERE id=?", (amount, job_id))

    def _error(self, connection, job_id: int, path: Path, code: str, message: str) -> None:
        connection.execute("INSERT INTO job_errors(job_id,path,code,message) VALUES (?,?,?,?)",
                           (job_id, str(path), code, message[:2000]))

    def _refresh_duplicates(self, connection, digest: str | None) -> None:
        if not digest:
            return
        rows = list(connection.execute("SELECT id,status FROM files WHERE content_hash=? ORDER BY id", (digest,)))
        canonical = next((row["id"] for row in rows if row["status"] == "indexed"), None)
        for row in rows:
            duplicate_of = canonical if row["status"] == "indexed" and row["id"] != canonical else None
            connection.execute("UPDATE files SET duplicate_of=? WHERE id=?", (duplicate_of, row["id"]))

    def _find_file(self, connection, path_text: str):
        if os.name == "nt":
            return connection.execute(
                "SELECT * FROM files WHERE path=? COLLATE NOCASE "
                "ORDER BY (path=? COLLATE BINARY) DESC,id LIMIT 1", (path_text, path_text),
            ).fetchone()
        return connection.execute("SELECT * FROM files WHERE path=?", (path_text,)).fetchone()

    def _discover(self, root: Path, root_id: int, job_id: int, cancelled: threading.Event) -> tuple[list[Path], bool]:
        files: list[Path] = []
        complete = True
        stack = [root]
        with self.db.connect() as connection:
            while stack:
                if self._should_stop_root(root_id, cancelled):
                    complete = False
                    break
                directory = stack.pop()
                try:
                    scanner = os.scandir(directory)
                except OSError as exc:
                    self._error(connection, job_id, directory, "unreadable_directory", str(exc))
                    complete = False
                    continue
                with scanner:
                    for entry in scanner:
                        if self._should_stop_root(root_id, cancelled):
                            complete = False
                            break
                        path = Path(entry.path)
                        try:
                            if connection.execute('SELECT 1 FROM collection_destinations WHERE path=? COLLATE NOCASE',(str(path),)).fetchone():
                                continue
                            if entry.is_symlink() or getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                                self._error(connection, job_id, path, "symlink_skipped", "Symlinks are never followed")
                                self._count(connection, job_id, "skipped")
                                continue
                            if not contained(path.resolve(strict=True), root):
                                self._error(connection, job_id, path, "outside_scope", "Resolved path is outside the approved folder")
                                self._count(connection, job_id, "skipped")
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if not entry.name.startswith(".") and entry.name not in {"$RECYCLE.BIN", "System Volume Information", "node_modules", "__pycache__"}:
                                    stack.append(path)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            if entry.name.startswith("~$") or entry.name.startswith(".") or entry.name.endswith((".tmp", ".part")):
                                self._count(connection, job_id, "skipped")
                                continue
                            if path.suffix.lower() not in SUPPORTED:
                                self._error(connection, job_id, path, "unsupported", "Unsupported file type")
                                self._count(connection, job_id, "skipped")
                                continue
                            files.append(path)
                        except OSError as exc:
                            self._error(connection, job_id, path, "unreadable", str(exc))
                            complete = False
            connection.execute("UPDATE jobs SET total=total+? WHERE id=?", (len(files), job_id))
        return sorted(files), complete and not self._should_stop_root(root_id, cancelled)

    def _run_job(self, job_id: int, root_id: int | None, cancelled: threading.Event) -> None:
        try:
            with self.db.connect() as connection:
                roots = [dict(row) for row in connection.execute(
                    "SELECT * FROM roots WHERE state='active' AND (? IS NULL OR id=?)", (root_id, root_id)
                )]
            for root_row in roots:
                if cancelled.is_set():
                    break
                self._scan_root(root_row, job_id, cancelled)
            self._finish_job(job_id, root_id, cancelled, "done")
        except Exception as exc:
            log.exception("Scan job %s failed", job_id)
            self._finish_job(job_id, root_id, cancelled, "failed", str(exc))

    def _finish_job(self, job_id: int, root_id: int | None, cancelled: threading.Event,
                    state: str, error: str | None = None) -> None:
        # Serialize final state with cancel() so a successful cancel request cannot
        # race with a late transition from running to done.
        with self._guard:
            if cancelled.is_set() or (root_id is not None and root_id in self._paused_roots):
                state = "cancelled"
            with self.db.connect() as connection:
                connection.execute(
                    "UPDATE jobs SET state=?, error=COALESCE(?,error), finished_at=?, current_path=NULL WHERE id=?",
                    (state, error[:2000] if error else None, now(), job_id),
                )

    def _scan_root(self, root_row: dict, job_id: int, cancelled: threading.Event) -> None:
        root = Path(root_row["path"])
        root_id = root_row["id"]
        if self._should_stop_root(root_id, cancelled):
            return
        if not root.is_dir() or root.is_symlink() or root.resolve() != root:
            with self.db.connect() as connection:
                message = "Approved folder is unavailable; indexed files were retained"
                connection.execute("UPDATE roots SET last_error=? WHERE id=?", (message, root_row["id"]))
                self._error(connection, job_id, root, "root_unavailable", message)
                self._count(connection, job_id, "failed")
            return
        discovered, complete = self._discover(root, root_id, job_id, cancelled)
        discovered_paths = {str(path) for path in discovered}
        for path in discovered:
            if self._should_stop_root(root_id, cancelled):
                return
            with self.db.connect() as connection:
                connection.execute("UPDATE jobs SET current_path=? WHERE id=?", (str(path), job_id))
            self._index_file(root_row["id"], path, discovered_paths, job_id, cancelled)
        if complete and not self._should_stop_root(root_id, cancelled):
            with self.db.connect() as connection:
                # Only a fully traversed root can establish that a path is missing.
                rows = list(connection.execute("SELECT id,path FROM files WHERE root_id=? AND status NOT IN ('missing','excluded')", (root_row["id"],)))
                for row in rows:
                    if row["path"] not in discovered_paths:
                        connection.execute("UPDATE files SET status='missing', error=NULL WHERE id=?", (row["id"],))
                        digest = connection.execute("SELECT content_hash FROM files WHERE id=?", (row["id"],)).fetchone()[0]
                        self._refresh_duplicates(connection, digest)
                        self._count(connection, job_id, "missing")
                connection.execute("UPDATE roots SET last_scan_at=?, last_error=NULL WHERE id=?", (now(), root_row["id"]))

    def _index_file(self, root_id: int, path: Path, discovered_paths: set[str], job_id: int,
                    cancelled: threading.Event) -> None:
        path_text = str(path)
        try:
            with self.db.connect() as connection:
                approved = connection.execute('SELECT path FROM roots WHERE id=?', (root_id,)).fetchone()
            if not approved or not safe_path(path_text, approved['path']):
                # Discovery is a snapshot: a rename may remove this path before indexing.
                # Keep the last content identity until a later scan reconciles its location.
                path.lstat()
                raise ValueError('File is outside a canonical approved folder or crosses a symlink/junction')
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or path.is_symlink():
                raise ValueError("File is not a regular file")
            if before.st_size > MAX_INPUT_BYTES:
                raise ValueError(f"File exceeds the {MAX_INPUT_BYTES // (1024 * 1024)} MB extraction limit")
            digest = file_hash(path, cancelled, lambda: self._should_stop_root(root_id, cancelled))
            after_hash = path.lstat()
            if not safe_path(path_text, approved['path']):
                raise ValueError('Folder path changed during hashing')
            if (before.st_size, before.st_mtime_ns) != (after_hash.st_size, after_hash.st_mtime_ns):
                raise ValueError("File changed while hashing; rescan to retry")
            with self.db.transaction(immediate=True) as connection:
                if cancelled.is_set() or not connection.execute("SELECT 1 FROM roots WHERE id=? AND state='active'", (root_id,)).fetchone():
                    return
                existing = self._find_file(connection, path_text)
                version = connection.execute("SELECT parser_version FROM documents WHERE file_id=?", (existing["id"],)).fetchone() if existing else None
                if existing and existing["content_hash"] == digest and existing["status"] in {"indexed", "missing"} and version and version[0] == PARSER_VERSION:
                    renamed = existing["path"] != path_text
                    connection.execute("UPDATE files SET root_id=?, path=?, filename=?, status='indexed', size=?, modified_ns=?, error=NULL WHERE id=?",
                                       (root_id, path_text, path.name, before.st_size, before.st_mtime_ns, existing["id"]))
                    if renamed:
                        connection.execute("INSERT INTO path_history(file_id,old_path,new_path,moved_at) VALUES (?,?,?,?)",
                                           (existing["id"], existing["path"], path_text, now()))
                    self._refresh_duplicates(connection, digest)
                    self._count(connection, job_id, "moved" if renamed else "unchanged")
                    self._count(connection, job_id, "processed")
                    return
                move = None
                if not existing:
                    for candidate in connection.execute(
                        "SELECT * FROM files WHERE content_hash=? AND extension=? ORDER BY id", (digest, path.suffix.lower())
                    ):
                        # Discovery may include both names when a move happens mid-walk.
                        # Current absence, rather than stale snapshot membership, proves
                        # this is a move candidate. Present duplicates retain distinct IDs.
                        if not Path(candidate["path"]).exists():
                            move = candidate
                            break
                if move and connection.execute("SELECT 1 FROM documents WHERE file_id=?", (move["id"],)).fetchone():
                    connection.execute("UPDATE files SET root_id=?, path=?, filename=?, size=?, modified_ns=?, status='indexed', error=NULL WHERE id=?",
                                       (root_id, path_text, path.name, before.st_size, before.st_mtime_ns, move["id"]))
                    connection.execute("INSERT INTO path_history(file_id,old_path,new_path,moved_at) VALUES (?,?,?,?)",
                                       (move["id"], move["path"], path_text, now()))
                    self._refresh_duplicates(connection, digest)
                    self._count(connection, job_id, "moved")
                    self._count(connection, job_id, "processed")
                    return
            if parse is _DEFAULT_PARSE:
                parsed = self._parser.parse(path, lambda: self._should_stop_root(root_id, cancelled))
            else:
                # Keep the parser seam replaceable for deterministic tests and integrations.
                parsed = parse(path)
            if self._should_stop_root(root_id, cancelled):
                raise InterruptedError("Scan stopped during parsing")
            after_parse = path.lstat()
            if not safe_path(path_text, approved['path']):
                raise ValueError('Folder path changed during parsing')
            if (before.st_size, before.st_mtime_ns) != (after_parse.st_size, after_parse.st_mtime_ns):
                raise ValueError("File changed while parsing; rescan to retry")
            with self.db.transaction(immediate=True) as connection:
                if cancelled.is_set() or not connection.execute("SELECT 1 FROM roots WHERE id=? AND state='active'", (root_id,)).fetchone():
                    return
                existing = self._find_file(connection, path_text)
                duplicate = connection.execute("SELECT id FROM files WHERE content_hash=? AND status='indexed' AND path!=? ORDER BY id LIMIT 1",
                                               (digest, path_text)).fetchone()
                if existing:
                    file_id = existing["id"]
                    action = "changed"
                    old_digest = existing["content_hash"]
                    connection.execute(
                        "UPDATE files SET root_id=?, path=?, filename=?, extension=?, size=?, modified_ns=?, content_hash=?, "
                        "status='indexed', error=NULL, indexed_at=?, duplicate_of=? WHERE id=?",
                        (root_id, path_text, path.name, path.suffix.lower(), before.st_size, before.st_mtime_ns, digest, now(),
                         duplicate["id"] if duplicate else None, file_id),
                    )
                    if existing["path"] != path_text:
                        connection.execute("INSERT INTO path_history(file_id,old_path,new_path,moved_at) VALUES (?,?,?,?)",
                                           (file_id, existing["path"], path_text, now()))
                    connection.execute("DELETE FROM documents WHERE file_id=?", (file_id,))
                else:
                    action = "created"
                    old_digest = None
                    connection.execute(
                        "INSERT INTO files(root_id,path,filename,extension,size,modified_ns,content_hash,status,indexed_at,discovered_at,duplicate_of) "
                        "VALUES (?,?,?,?,?,?,?,'indexed',?,?,?)",
                        (root_id, path_text, path.name, path.suffix.lower(), before.st_size, before.st_mtime_ns, digest,
                         now(), now(), duplicate["id"] if duplicate else None),
                    )
                    file_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                connection.execute("DELETE FROM text_blocks WHERE file_id=?", (file_id,))
                connection.execute("DELETE FROM parser_warnings WHERE file_id=?", (file_id,))
                connection.execute("INSERT INTO documents(file_id,title,text,metadata_json,parser_version) VALUES (?,?,?,?,?)",
                                   (file_id, parsed.title, parsed.text, json.dumps(parsed.metadata), PARSER_VERSION))
                connection.executemany("INSERT INTO text_blocks(file_id,position,location,text) VALUES (?,?,?,?)",
                                       [(file_id, b.position, b.location, b.text) for b in parsed.blocks])
                connection.executemany("INSERT INTO parser_warnings(file_id,message) VALUES (?,?)",
                                       [(file_id, warning) for warning in parsed.warnings])
                self._refresh_duplicates(connection, old_digest)
                self._refresh_duplicates(connection, digest)
                self._count(connection, job_id, action)
                self._count(connection, job_id, "processed")
                if cancelled.is_set():
                    # Raising inside the transaction rolls back the entire replacement.
                    raise InterruptedError("Scan cancelled")
        except InterruptedError:
            return
        except Exception as exc:
            if isinstance(exc, FileNotFoundError) and not path.exists():
                # Missing paths are inaccessible already; retain identity for reconciliation.
                with self.db.connect() as connection:
                    self._error(connection, job_id, path, 'path_disappeared', 'Path disappeared during scanning; rescan to reconcile moved or missing files.')
                    self._count(connection, job_id, 'skipped')
                    self._count(connection, job_id, 'processed')
                return
            log.warning("Cannot index %s: %s", path, exc)
            with self.db.transaction(immediate=True) as connection:
                if cancelled.is_set() or not connection.execute("SELECT 1 FROM roots WHERE id=? AND state='active'", (root_id,)).fetchone():
                    return
                message = f"{type(exc).__name__}: {exc}"[:2000]
                existing = self._find_file(connection, path_text)
                if existing:
                    old_digest = connection.execute("SELECT content_hash FROM files WHERE id=?", (existing["id"],)).fetchone()[0]
                    connection.execute("UPDATE files SET status='error', error=? WHERE id=?", (message, existing["id"]))
                    self._refresh_duplicates(connection, old_digest)
                else:
                    connection.execute(
                        "INSERT INTO files(root_id,path,filename,extension,status,error,discovered_at) VALUES (?,?,?,?,'error',?,?)",
                        (root_id, path_text, path.name, path.suffix.lower(), message, now()),
                    )
                self._error(connection, job_id, path, "index_failed", message)
                self._count(connection, job_id, "failed")
                self._count(connection, job_id, "processed")
