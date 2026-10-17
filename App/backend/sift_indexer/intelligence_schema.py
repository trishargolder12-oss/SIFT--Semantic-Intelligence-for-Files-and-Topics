"""Versioned, rebuildable intelligence data. Original documents remain untouched."""

SCHEMA = """
CREATE TABLE intelligence_documents (
 file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
 content_hash TEXT, parser_version INTEGER, engine_version INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'pending', published_at TEXT
);
CREATE TABLE chunks (
 id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 content_hash TEXT NOT NULL, position INTEGER NOT NULL, location TEXT, start_char INTEGER NOT NULL,
 text TEXT NOT NULL, embedding BLOB, embedding_model TEXT,
 UNIQUE(file_id,position)
);
CREATE INDEX chunks_file_version ON chunks(file_id,content_hash);
CREATE VIRTUAL TABLE chunks_fts USING fts5(text,content='chunks',content_rowid='id',tokenize='porter unicode61');
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
 INSERT INTO chunks_fts(rowid,text) VALUES(new.id,new.text);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
 INSERT INTO chunks_fts(chunks_fts,rowid,text) VALUES('delete',old.id,old.text);
END;
CREATE TABLE library_groups (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('subject','topic','type')),
 key TEXT NOT NULL, name TEXT NOT NULL, original_name TEXT NOT NULL,
 UNIQUE(kind,key)
);
CREATE TABLE group_assignments (
 file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 group_id INTEGER NOT NULL REFERENCES library_groups(id) ON DELETE CASCADE,
 source TEXT NOT NULL CHECK(source IN ('auto','user')), content_hash TEXT, reason TEXT NOT NULL,
 PRIMARY KEY(file_id,group_id,source)
);
CREATE INDEX group_assignments_group ON group_assignments(group_id,file_id);
CREATE TABLE group_corrections (
 file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('subject','topic','type')), updated_at TEXT NOT NULL,
 PRIMARY KEY(file_id,kind)
);
CREATE TABLE conversations(id TEXT PRIMARY KEY,created_at TEXT NOT NULL);
CREATE TABLE discovery_turns (
 id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id),
 created_at TEXT NOT NULL,message TEXT NOT NULL,intent_json TEXT NOT NULL,
 response_kind TEXT NOT NULL,refs_json TEXT NOT NULL,detail_json TEXT NOT NULL
);
CREATE INDEX discovery_turns_conversation ON discovery_turns(conversation_id,created_at);
CREATE TABLE intelligence_jobs (
 id INTEGER PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,
 payload_json TEXT NOT NULL,turn_id TEXT,conversation_id TEXT,
 processed INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,finished_at TEXT,error TEXT
);
CREATE TABLE intelligence_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO intelligence_settings VALUES('models_enabled','false');
INSERT INTO intelligence_documents(file_id,content_hash,parser_version)
 SELECT d.file_id,f.content_hash,d.parser_version FROM documents d JOIN files f ON f.id=d.file_id;

CREATE TRIGGER intelligence_document_insert AFTER INSERT ON documents BEGIN
 INSERT INTO intelligence_documents(file_id,content_hash,parser_version,state)
 VALUES(new.file_id,(SELECT content_hash FROM files WHERE id=new.file_id),new.parser_version,'pending')
 ON CONFLICT(file_id) DO UPDATE SET content_hash=excluded.content_hash,parser_version=excluded.parser_version,state='pending';
END;
CREATE TRIGGER intelligence_document_update AFTER UPDATE ON documents BEGIN
 DELETE FROM chunks WHERE file_id=new.file_id;
 DELETE FROM group_assignments WHERE file_id=new.file_id AND source='auto';
 INSERT INTO intelligence_documents(file_id,content_hash,parser_version,state)
 VALUES(new.file_id,(SELECT content_hash FROM files WHERE id=new.file_id),new.parser_version,'pending')
 ON CONFLICT(file_id) DO UPDATE SET content_hash=excluded.content_hash,parser_version=excluded.parser_version,state='pending';
END;
CREATE TRIGGER intelligence_document_delete AFTER DELETE ON documents BEGIN
 DELETE FROM chunks WHERE file_id=old.file_id;
 DELETE FROM group_assignments WHERE file_id=old.file_id AND source='auto';
 DELETE FROM intelligence_documents WHERE file_id=old.file_id;
END;
CREATE TRIGGER intelligence_file_change AFTER UPDATE ON files
 WHEN new.content_hash IS NOT old.content_hash OR new.status IS NOT old.status
 OR new.path IS NOT old.path OR new.root_id IS NOT old.root_id BEGIN
 DELETE FROM chunks WHERE file_id=new.id AND (new.content_hash IS NOT old.content_hash OR new.status!='indexed');
 DELETE FROM group_assignments WHERE file_id=new.id AND source='auto';
 UPDATE intelligence_documents SET state=CASE WHEN new.status='indexed' THEN 'pending' ELSE 'unavailable' END WHERE file_id=new.id;
END;
"""
