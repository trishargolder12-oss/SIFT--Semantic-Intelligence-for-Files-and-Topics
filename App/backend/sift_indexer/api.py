"""Private loopback API. The launch secret is never exposed to the renderer."""

from __future__ import annotations

import hmac
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .db import Database, SCHEMA_VERSION
from .indexer import Indexer
from .monitor import Monitor
from .access import permitted_file
from .intelligence import Intelligence
from .intelligence_api import register_intelligence
from .study_collections import StudyCollections
from .collections_api import register_collections


class FolderInput(BaseModel):
    path: str


class FolderState(BaseModel):
    state: str


class ScanInput(BaseModel):
    root_id: int | None = None


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


def create_app(db_path: Path, secret: str) -> FastAPI:
    db = Database(db_path)
    indexer = Indexer(db)
    monitor = Monitor(indexer)
    intelligence = Intelligence(db)
    collections = StudyCollections(db,intelligence)
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        monitor.start()
        intelligence.start()
        collections.start()
        try:
            yield
        finally:
            monitor.close()
            collections.close()
            intelligence.close()
            indexer.close()

    app = FastAPI(title="SIFT Local Library Indexer", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.indexer = indexer
    app.state.intelligence = intelligence
    app.state.collections = collections

    def authorized(x_sift_token: str | None = Header(default=None)) -> None:
        if not x_sift_token or not hmac.compare_digest(x_sift_token, secret):
            raise HTTPException(401, "Unauthorized")

    auth = [Depends(authorized)]
    register_intelligence(app, intelligence, auth)
    register_collections(app, collections, auth)

    @app.get("/health", dependencies=auth)
    def health():
        return {"ok": True, "schema_version": SCHEMA_VERSION}

    @app.get("/folders", dependencies=auth)
    def folders():
        return indexer.roots()

    @app.post("/folders", dependencies=auth)
    def add_folder(body: FolderInput):
        try:
            result = indexer.add_root(body.path)
            monitor.refresh()
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.patch("/folders/{root_id}", dependencies=auth)
    def update_folder(root_id: int, body: FolderState):
        try:
            result = indexer.set_root_state(root_id, body.state)
            monitor.refresh()
            if body.state == "active":
                monitor.schedule(root_id)
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/scans", dependencies=auth)
    def start_scan(body: ScanInput):
        try:
            job_id = indexer.start_scan(body.root_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": job_id}

    @app.get("/jobs/latest", dependencies=auth)
    def latest_job():
        return indexer.latest_job()

    @app.get("/jobs/{job_id}", dependencies=auth)
    def get_job(job_id: int):
        result = indexer.job(job_id)
        if result is None:
            raise HTTPException(404, "Job not found")
        return result

    @app.post("/jobs/{job_id}/cancel", dependencies=auth)
    def cancel_job(job_id: int):
        if not indexer.cancel(job_id):
            raise HTTPException(409, "Job is no longer running")
        return {"cancel_requested": True}

    @app.get("/documents", dependencies=auth)
    def documents(status: str | None = None, limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
        if status and status not in {"indexed", "error", "missing", "excluded"}:
            raise HTTPException(400, "Invalid status")
        with db.transaction() as connection:
            where = "WHERE f.status=?" if status else ""
            params = (status,) if status else ()
            total = connection.execute(f"SELECT COUNT(*) FROM files f {where}", params).fetchone()[0]
            library_total = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            rows = connection.execute(
                "SELECT f.*, d.title, substr(d.text,1,240) AS preview, "
                "(SELECT COUNT(*) FROM parser_warnings w WHERE w.file_id=f.id) AS warning_count "
                f"FROM files f LEFT JOIN documents d ON d.file_id=f.id {where} "
                "ORDER BY f.discovered_at DESC, f.id DESC LIMIT ? OFFSET ?", (*params, limit, offset),
            )
            items = []
            for row in rows:
                item = dict(row)
                if not permitted_file(connection, item['id'], available=False):
                    item.update(title=None, preview=None, warning_count=0)
                items.append(item)
            return {"total": total, "library_total": library_total, "items": items}

    @app.get("/documents/{file_id}", dependencies=auth)
    def document(file_id: int):
        with db.connect() as connection:
            if not permitted_file(connection, file_id, available=False):
                raise HTTPException(403, 'Document is outside current approved folders')
            row = connection.execute("SELECT f.*, d.title, d.text, d.metadata_json FROM files f "
                                     "LEFT JOIN documents d ON d.file_id=f.id WHERE f.id=?", (file_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Document not found")
            result = dict(row)
            result["blocks"] = [dict(block) for block in connection.execute(
                "SELECT position,location,text FROM text_blocks WHERE file_id=? ORDER BY position", (file_id,)
            )]
            result["warnings"] = [warning[0] for warning in connection.execute(
                "SELECT message FROM parser_warnings WHERE file_id=?", (file_id,)
            )]
            result["path_history"] = [dict(item) for item in connection.execute(
                "SELECT old_path,new_path,moved_at FROM path_history WHERE file_id=? ORDER BY id DESC", (file_id,)
            )]
            return result

    @app.get('/documents/{file_id}/access', dependencies=auth)
    def file_access(file_id: int):
        with db.connect() as connection:
            row = permitted_file(connection, file_id, current=True)
            if not row:
                raise HTTPException(403, 'File is unavailable, changed, or outside approved folders')
            return {'id': row['id'], 'root_id': row['root_id'], 'path': row['path'], 'status': row['status']}

    @app.post("/search", dependencies=auth)
    def search(body: SearchInput):
        terms = [word.replace('"', "") for word in body.query.split() if word.strip('"')]
        if not terms:
            return {"items": [], "total": 0, "offset": body.offset, "limit": body.limit, "has_more": False}
        expression = " AND ".join('"' + word + '"' for word in terms)
        filename_where = " AND ".join("instr(lower(f.filename), lower(?)) > 0" for _ in terms)
        try:
            with db.transaction() as connection:
                # Canonical folder/file permissions filter candidates before reading cached text.
                connection.execute('CREATE TEMP TABLE search_allowed(id INTEGER PRIMARY KEY)')
                candidates = [row[0] for row in connection.execute("SELECT f.id FROM files f JOIN roots r ON r.id=f.root_id WHERE f.status='indexed' AND r.state IN ('active','paused')")]
                allowed = [file_id for file_id in candidates if permitted_file(connection, file_id, current=True)]
                connection.executemany('INSERT INTO search_allowed VALUES(?)', [(file_id,) for file_id in allowed])
                rows = connection.execute(
                    "WITH filename_matches AS MATERIALIZED ("
                    "SELECT f.id,f.path,f.filename,f.status,f.content_hash AS content_version,d.title,f.filename AS snippet,"
                    "-100.0 AS rank,'filename' AS match_kind FROM files f JOIN documents d ON d.file_id=f.id JOIN search_allowed a ON a.id=f.id "
                    f"WHERE f.status='indexed' AND {filename_where}), "
                    "content_matches AS MATERIALIZED ("
                    "SELECT f.id,f.path,f.filename,f.status,f.content_hash AS content_version,d.title,"
                    "snippet(documents_fts,1,'[',']',' … ',24) AS snippet,"
                    "bm25(documents_fts) AS rank,'content' AS match_kind "
                    "FROM documents_fts JOIN documents d ON d.file_id=documents_fts.rowid "
                    "JOIN files f ON f.id=d.file_id JOIN search_allowed a ON a.id=f.id WHERE documents_fts MATCH ? AND f.status='indexed' "
                    "AND f.id NOT IN (SELECT id FROM filename_matches)) "
                    "SELECT * FROM (SELECT * FROM filename_matches UNION ALL SELECT * FROM content_matches) "
                    "ORDER BY CASE match_kind WHEN 'filename' THEN 0 ELSE 1 END,rank,filename COLLATE NOCASE,id "
                    "", (*terms, expression),
                )
                # Filesystem access and approval are checked before counting/paging results.
                snapshot = [dict(row) for row in rows]
                permitted = []
                # Recheck a fresh permission/version view after potentially long retrieval.
                with db.connect() as latest:
                    for row in snapshot:
                        current = permitted_file(latest, row['id'], current=True)
                        if current and current['content_hash'] == row['content_version']:
                            row.update(path=current['path'], filename=current['filename'], title=current['title'])
                            permitted.append(row)
                total = len(permitted)
                items = permitted[body.offset:body.offset+body.limit]
                return {"items": items, "total": total, "offset": body.offset, "limit": body.limit,
                        "has_more": body.offset + len(items) < total}
        except sqlite3.OperationalError as exc:
            raise HTTPException(400, f"Search query could not be processed: {exc}") from exc

    return app
