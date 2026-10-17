import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sift_indexer import indexer as indexer_module
from sift_indexer.api import create_app
from sift_indexer.db import Database
from sift_indexer.indexer import Indexer
from sift_indexer.parsers import ParsedDocument, TextBlock
from sift_indexer import db as db_module
from test_indexer import run_scan


def test_repeated_edits_replace_document_blocks_warnings_and_fts(tmp_path, monkeypatch):
    library = tmp_path / 'library'
    library.mkdir()
    source = library / 'notes.txt'
    source.write_text('first edition')
    token = {'X-SIFT-Token': 'test'}

    def parser(path):
        text = path.read_text()
        words = text.split()
        blocks = [TextBlock(i, f'Paragraph {i + 1}', word) for i, word in enumerate(words)]
        return ParsedDocument(path.stem, '\n\n'.join(words), blocks, [f'Note for {text}'])

    monkeypatch.setattr(indexer_module, 'parse', parser)
    app = create_app(tmp_path / 'index.sqlite', 'test')
    indexer = app.state.indexer
    root_id = indexer.add_root(str(library))['id']
    with TestClient(app) as client:
        for text in ['first edition', 'second revised edition', 'final']:
            source.write_text(text)
            run_scan(indexer, root_id)
            item = client.get('/documents', headers=token).json()['items'][0]
            detail = client.get(f'/documents/{item["id"]}', headers=token).json()
            assert [b['text'] for b in detail['blocks']] == text.split()
            assert [b['position'] for b in detail['blocks']] == list(range(len(text.split())))
            assert detail['text'] == '\n\n'.join(text.split())
            assert detail['warnings'] == [f'Note for {text}']
        with indexer.db.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM documents_fts WHERE documents_fts MATCH 'first'").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM documents_fts WHERE documents_fts MATCH 'final'").fetchone()[0] == 1


def test_failed_replacement_rolls_back_every_cached_part(tmp_path, monkeypatch):
    library = tmp_path / 'library'
    library.mkdir()
    source = library / 'notes.txt'
    source.write_text('old snapshot')
    db = Database(tmp_path / 'index.sqlite')
    indexer = Indexer(db)
    root_id = indexer.add_root(str(library))['id']
    run_scan(indexer, root_id)
    source.write_text('new snapshot')

    # Simulate a write failure after replacement has begun, not a parse failure.
    original_connect = db.connect
    class FailingConnection:
        def __init__(self, connection): self.connection = connection
        def __getattr__(self, name): return getattr(self.connection, name)
        def executemany(self, sql, params):
            if sql.startswith('INSERT INTO text_blocks'):
                raise sqlite3.OperationalError('Injected block write failure')
            return self.connection.executemany(sql, params)

    @contextmanager
    def failing_connect():
        with original_connect() as connection:
            yield FailingConnection(connection)

    monkeypatch.setattr(db, 'connect', failing_connect)
    assert run_scan(indexer, root_id)['failed'] == 1
    monkeypatch.setattr(db, 'connect', original_connect)
    with db.connect() as connection:
        assert connection.execute('SELECT text FROM documents').fetchone()[0] == 'old snapshot'
        assert [row[0] for row in connection.execute('SELECT text FROM text_blocks')] == ['old snapshot']
        assert connection.execute("SELECT COUNT(*) FROM documents_fts WHERE documents_fts MATCH 'new'").fetchone()[0] == 0


def test_cancelled_replacement_retains_last_snapshot(tmp_path, monkeypatch):
    library = tmp_path / 'library'
    library.mkdir()
    source = library / 'notes.txt'
    source.write_text('last good snapshot')
    db = Database(tmp_path / 'index.sqlite')
    indexer = Indexer(db)
    root_id = indexer.add_root(str(library))['id']
    run_scan(indexer, root_id)
    source.write_text('cancelled replacement')
    cancelled = threading.Event()
    original_parse = indexer_module.parse
    def cancel_after_parse(path):
        parsed = original_parse(path)
        cancelled.set()
        return parsed
    monkeypatch.setattr(indexer_module, 'parse', cancel_after_parse)
    with db.connect() as connection:
        connection.execute("INSERT INTO jobs(root_id,state,source) VALUES (?,'running','test')", (root_id,))
        job_id = connection.execute('SELECT last_insert_rowid()').fetchone()[0]
    indexer._index_file(root_id, source, {str(source)}, job_id, cancelled)
    with db.connect() as connection:
        assert connection.execute('SELECT text FROM documents').fetchone()[0] == 'last good snapshot'
        assert [row[0] for row in connection.execute('SELECT text FROM text_blocks')] == ['last good snapshot']


def test_connection_closes_after_commit_and_exception_and_rolls_back(tmp_path):
    db = Database(tmp_path / 'index.sqlite')
    with db.connect() as successful:
        successful.execute("INSERT INTO roots(path,state,added_at) VALUES ('saved','active','now')")
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        successful.execute('SELECT 1')
    with pytest.raises(RuntimeError):
        with db.connect() as failed:
            failed.execute("INSERT INTO roots(path,state,added_at) VALUES ('rolled-back','active','now')")
            raise RuntimeError('abort')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        failed.execute('SELECT 1')
    with db.connect() as connection:
        assert [row[0] for row in connection.execute('SELECT path FROM roots')] == ['saved']


def test_upgrade_repairs_old_blocks_and_preserves_case_collisions(tmp_path):
    path = tmp_path / 'legacy.sqlite'
    connection = sqlite3.connect(path)
    try:
        connection.executescript(db_module.MIGRATIONS[0])
        connection.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO schema_migrations VALUES (1)')
        connection.execute("INSERT INTO roots(id,path,state,added_at) VALUES (1,'C:/Study','active','now')")
        for file_id, filename, text in [(1, 'Notes.txt', 'short'), (2, 'notes.txt', '')]:
            connection.execute("INSERT INTO files(id,root_id,path,filename,extension,status,discovered_at) VALUES (?,1,?,?,'.txt','indexed','now')", (file_id, 'C:/Study/' + filename, filename))
            connection.execute("INSERT INTO documents VALUES (?,?,?,'{}',1)", (file_id, filename, text))
            connection.executemany('INSERT INTO text_blocks(file_id,position,location,text) VALUES (?,?,?,?)', [(file_id, 0, 'Old page 1', 'obsolete'), (file_id, 1, 'Old page 2', 'obsolete tail')])
        connection.execute("INSERT INTO text_blocks(file_id,position,location,text) VALUES (1,0,'Current page','short')")
        connection.commit()
    finally:
        connection.close()
    db = Database(path)
    with db.connect() as connection:
        assert [tuple(row) for row in connection.execute('SELECT file_id,position,location,text FROM text_blocks')] == [(1, 0, 'Current page', 'short')]
        assert connection.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 2
        plan = ' '.join(row['detail'] for row in connection.execute('EXPLAIN QUERY PLAN SELECT * FROM files WHERE path=? COLLATE NOCASE ORDER BY (path=? COLLATE BINARY) DESC,id LIMIT 1', ('C:/Study/NOTES.txt', 'C:/Study/NOTES.txt')))
        assert 'SEARCH files USING INDEX files_path_nocase' in plan
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO text_blocks(file_id,position,text) VALUES (1,0,'duplicate')")
    if indexer_module.os.name == 'nt':
        indexer = Indexer(db)
        with db.connect() as connection:
            assert indexer._find_file(connection, 'C:/Study/Notes.txt')['id'] == 1
            assert indexer._find_file(connection, 'C:/Study/notes.txt')['id'] == 2
    Database(path)  # Repeat startup does not rerun or duplicate migrations.


def test_failed_migration_rolls_back_schema_and_version(tmp_path, monkeypatch):
    path = tmp_path / 'index.sqlite'
    db = Database(path)
    def broken_migration(connection):
        connection.execute('CREATE TABLE should_not_survive (id INTEGER)')
        raise RuntimeError('migration interrupted')
    monkeypatch.setattr(db_module, 'MIGRATIONS', [*db_module.MIGRATIONS, broken_migration])
    with pytest.raises(RuntimeError, match='migration interrupted'):
        Database(path)
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='should_not_survive'").fetchone()[0] == 0
        assert connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0] == db_module.SCHEMA_VERSION


def test_search_pages_all_matches_without_duplicates_and_tracks_changes(tmp_path):
    path = tmp_path / 'search.sqlite'
    db = Database(path)
    (tmp_path / 'library').mkdir()
    with db.connect() as connection:
        connection.execute("INSERT INTO roots(id,path,state,added_at) VALUES (1,?,'paused','now')", (str(tmp_path / 'library'),))
        for number in range(199):
            filename = f'notes-{number:03}.txt' if number > 1 else f'benchmarkneedle-{number}.txt'
            text = 'unrelated text' if number == 1 else 'benchmarkneedle study material'
            actual = tmp_path / 'library' / filename
            actual.write_text(text)
            connection.execute("INSERT INTO files(id,root_id,path,filename,extension,status,discovered_at) VALUES (?,1,?,? ,'.txt','indexed','now')", (number + 1, str(actual), filename))
            import hashlib
            connection.execute('UPDATE files SET size=?,modified_ns=?,content_hash=? WHERE id=?', (actual.stat().st_size,actual.stat().st_mtime_ns,hashlib.sha256(actual.read_bytes()).hexdigest(),number+1))
            connection.execute("INSERT INTO documents VALUES (?,?,?,'{}',1)", (number + 1, filename, text))
    token = {'X-SIFT-Token': 'test'}
    with TestClient(create_app(path, 'test')) as client:
        pages = []
        for offset in [0, 50, 100, 150]:
            response = client.post('/search', headers=token, json={'query': 'benchmarkneedle', 'offset': offset, 'limit': 50})
            assert response.status_code == 200, response.text
            page = response.json()
            assert page['total'] == 199
            assert page['offset'] == offset and page['limit'] == 50
            assert page['has_more'] == (offset < 150)
            pages.append(page)
        ids = [item['id'] for page in pages for item in page['items']]
        assert len(ids) == len(set(ids)) == 199
        assert all(item['match_kind'] == 'filename' for item in pages[0]['items'][:2])
        repeated = client.post('/search', headers=token, json={'query': 'benchmarkneedle'}).json()
        assert repeated['items'] == pages[0]['items']
        assert client.post('/search', headers=token, json={'query': 'benchmarkneedle', 'offset': -1}).status_code == 422
        assert client.post('/search', headers=token, json={'query': 'benchmarkneedle', 'limit': 101}).status_code == 422
        with db.connect() as connection:
            connection.execute("UPDATE documents SET text='updated without matching word' WHERE file_id=3")
        assert client.post('/search', headers=token, json={'query': 'benchmarkneedle'}).json()['total'] == 198
        client.patch('/folders/1', headers=token, json={'state': 'removed'})
        assert client.post('/search', headers=token, json={'query': 'benchmarkneedle'}).json()['total'] == 0
        documents = client.get('/documents?status=indexed', headers=token).json()
        assert documents['total'] == 0 and documents['library_total'] == 199
        assert client.post('/search', headers=token, json={'query': '""'}).json()['items'] == []
