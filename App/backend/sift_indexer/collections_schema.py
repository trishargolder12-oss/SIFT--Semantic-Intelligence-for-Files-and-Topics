SCHEMA = r'''
CREATE TABLE syllabus_attachments(id TEXT PRIMARY KEY,path TEXT NOT NULL,name TEXT NOT NULL,
 content_hash TEXT NOT NULL,size INTEGER NOT NULL,modified_ns INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE collection_destinations(id TEXT PRIMARY KEY,path TEXT NOT NULL UNIQUE,base_path TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE study_collections(id TEXT PRIMARY KEY,attachment_id TEXT REFERENCES syllabus_attachments(id),
 pasted_text TEXT NOT NULL DEFAULT '',subject TEXT NOT NULL DEFAULT 'Study collection',revision INTEGER NOT NULL DEFAULT 0,
 source_version TEXT,outline_json TEXT NOT NULL DEFAULT '{}',extracted_json TEXT NOT NULL DEFAULT '{}',corrected INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'queued',issues_json TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL);
CREATE TABLE syllabus_revisions(collection_id TEXT NOT NULL REFERENCES study_collections(id),revision INTEGER NOT NULL,
 source_version TEXT,outline_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(collection_id,revision));
CREATE TABLE visual_pages(source_key TEXT NOT NULL,content_hash TEXT NOT NULL,page INTEGER NOT NULL,config TEXT NOT NULL,
 status TEXT NOT NULL,regions_json TEXT NOT NULL,thumbnail BLOB,issues_json TEXT NOT NULL,PRIMARY KEY(source_key,content_hash,page,config));
ALTER TABLE chunks ADD COLUMN region_id TEXT;
CREATE TABLE topic_assignments(collection_id TEXT NOT NULL REFERENCES study_collections(id),topic_id TEXT NOT NULL,
 file_id INTEGER NOT NULL REFERENCES files(id),content_hash TEXT NOT NULL,classification TEXT NOT NULL,
 decision TEXT NOT NULL DEFAULT 'auto',evidence_json TEXT NOT NULL,reason TEXT NOT NULL,
 PRIMARY KEY(collection_id,topic_id,file_id));
CREATE TABLE collection_jobs(id INTEGER PRIMARY KEY,collection_id TEXT REFERENCES study_collections(id),
 kind TEXT NOT NULL DEFAULT 'organize',state TEXT NOT NULL DEFAULT 'queued',phase TEXT NOT NULL DEFAULT 'reading',
 processed INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL DEFAULT 0,error TEXT,attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE collection_exports(id TEXT PRIMARY KEY,collection_id TEXT NOT NULL REFERENCES study_collections(id),
 destination_id TEXT NOT NULL REFERENCES collection_destinations(id),revision INTEGER NOT NULL,plan_json TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending',error TEXT,UNIQUE(collection_id,destination_id));
CREATE TABLE collection_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO collection_settings VALUES('ocr_pack','');
CREATE TRIGGER collection_file_changed AFTER UPDATE OF content_hash,status ON files
WHEN old.content_hash IS NOT new.content_hash OR old.status IS NOT new.status BEGIN
 UPDATE study_collections SET state='stale' WHERE id IN (SELECT collection_id FROM topic_assignments WHERE file_id=new.id);
 UPDATE collection_exports SET state='stale' WHERE collection_id IN (SELECT collection_id FROM topic_assignments WHERE file_id=new.id);
 DELETE FROM visual_pages WHERE source_key='file:'||new.id AND (content_hash IS NOT new.content_hash OR new.status!='indexed');
END;
CREATE TRIGGER collection_root_revoked AFTER UPDATE OF state ON roots WHEN new.state='removed' BEGIN
 UPDATE study_collections SET state='stale' WHERE id IN (SELECT a.collection_id FROM topic_assignments a JOIN files f ON f.id=a.file_id WHERE f.root_id=new.id);
 UPDATE collection_exports SET state='stale';
END;
CREATE TRIGGER collection_file_moved AFTER UPDATE OF path ON files WHEN old.path!=new.path BEGIN
 UPDATE study_collections SET state='stale' WHERE id IN (SELECT collection_id FROM topic_assignments WHERE file_id=new.id);
 UPDATE collection_exports SET state='stale';
END;
'''
