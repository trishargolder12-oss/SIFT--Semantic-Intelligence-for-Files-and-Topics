"""Versioned syllabus collections, background matching and durable export plans."""
import base64
import hashlib
import json
import logging
from pathlib import Path
import re
import threading
import uuid

from .access import permitted_file, safe_path
from .document_vision import CONFIG, MAX_PAGES, inspect_page, inspect_source, pack_info
from .grouping import normalize
from .intelligence import now
from .syllabus import extract_outline, topics, validate_outline

log = logging.getLogger(__name__)


def canonical_directory(raw):
    path = Path(raw)
    if not path.is_absolute() or not path.is_dir() or path.resolve(strict=True) != path: raise PermissionError('Choose an existing local folder without links')
    for part in [path, *path.parents]:
        if part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & 0x400: raise PermissionError('Linked folders are not permitted')
    return path


class StudyCollections:
    def __init__(self, db, intelligence):
        self.db, self.intelligence = db, intelligence
        self.stop = threading.Event(); self.events = {}; self.guard = threading.Lock(); self.worker = None
        with db.connect() as con:
            con.execute("UPDATE collection_jobs SET state=CASE WHEN attempts<2 THEN 'queued' ELSE 'failed' END,error='Interrupted processing recovered' WHERE state='running'")
            con.execute("UPDATE collection_exports SET state='pending' WHERE state='writing'")

    def start(self):
        self.worker = threading.Thread(target=self._loop, daemon=True, name='sift-collections'); self.worker.start()

    def close(self):
        self.stop.set()
        if self.worker: self.worker.join(5)

    def attachment(self, path):
        source = Path(path)
        if source.suffix.lower() not in {'.pdf','.png','.jpg','.jpeg'} or not safe_path(str(source), str(source.parent)): raise PermissionError('Choose a readable PDF, PNG or JPEG without links')
        info = source.stat()
        if info.st_size > 64*1024**2: raise ValueError('Attachments are limited to 64 MB')
        with source.open('rb') as stream: digest = hashlib.file_digest(stream,'sha256').hexdigest()
        with self.db.connect() as con:
            existing = con.execute('SELECT id FROM syllabus_attachments WHERE path=? AND active=1',(str(source),)).fetchone()
            attachment = existing[0] if existing else str(uuid.uuid4())
            con.execute('INSERT INTO syllabus_attachments VALUES(?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash,size=excluded.size,modified_ns=excluded.modified_ns',
                        (attachment,str(source),source.name,digest,info.st_size,info.st_mtime_ns))
        return {'id':attachment,'name':source.name}

    def attachment_access(self, attachment, refresh=False):
        with self.db.connect() as con: row = con.execute('SELECT * FROM syllabus_attachments WHERE id=? AND active=1',(attachment,)).fetchone()
        if not row or not safe_path(row['path'],str(Path(row['path']).parent)): raise PermissionError('Attached source is unavailable')
        info = Path(row['path']).stat()
        if info.st_size != row['size'] or info.st_mtime_ns != row['modified_ns']:
            if refresh: self.attachment(row['path']); return self.attachment_access(attachment)
            raise PermissionError('Attached source changed; refresh the collection')
        return dict(row)

    def revoke_attachment(self, attachment):
        with self.db.connect() as con:
            con.execute('UPDATE syllabus_attachments SET active=0 WHERE id=?',(attachment,))
            con.execute("UPDATE study_collections SET state='unavailable' WHERE attachment_id=?",(attachment,))
            con.execute("UPDATE collection_exports SET state='stale' WHERE collection_id IN (SELECT id FROM study_collections WHERE attachment_id=?)",(attachment,))
        return {'revoked':True}

    def destination(self, path=None, base=None, destination_id=None):
        with self.db.connect() as con:
            if path:
                canonical_directory(path); canonical_directory(base); uuid.UUID(destination_id)
                Path(path).relative_to(Path(base))
                marker = json.loads((Path(path)/'.sift-output.json').read_text())
                if marker != {'id':destination_id,'app':'org.sift.local-library'}: raise PermissionError('Invalid output ownership marker')
                con.execute('UPDATE collection_destinations SET active=0')
                con.execute('INSERT INTO collection_destinations VALUES(?,?,?,1) ON CONFLICT(id) DO UPDATE SET active=1',(destination_id,path,base))
                con.execute("UPDATE collection_exports SET state='stale'")
            row = con.execute('SELECT * FROM collection_destinations WHERE active=1').fetchone()
        return dict(row) if row else None

    def vision_status(self):
        with self.db.connect() as con: pack = con.execute("SELECT value FROM collection_settings WHERE key='ocr_pack'").fetchone()[0]
        return {'ocr_ready':bool(pack and Path(pack,'sift-ocr/sift-ocr.exe').is_file()), 'ocr_pack':pack,
                'page_limit':MAX_PAGES,'languages':'English and simplified/traditional Chinese; handwriting requires review',
                'models': self.intelligence.status()}

    def revoke_destination(self):
        with self.db.connect() as con:
            con.execute('UPDATE collection_destinations SET active=0')
            con.execute("UPDATE collection_exports SET state='cancelled' WHERE state IN ('pending','writing','stale')")
        return {'revoked':True}

    def set_pack(self,path):
        canonical_directory(path); info = pack_info(path)
        with self.db.connect() as con: con.execute("UPDATE collection_settings SET value=? WHERE key='ocr_pack'",(path,))
        return {'installed':True,'engine':info['engine']}

    def create(self, text='', attachment_id=None, collection_id=None):
        if attachment_id: self.attachment_access(attachment_id)
        elif not text.strip() or len(text)>100000: raise ValueError('Paste a syllabus of at most 100,000 characters')
        with self.db.connect() as con:
            if not collection_id:
                existing = con.execute('SELECT id FROM study_collections WHERE attachment_id=?',(attachment_id,)).fetchone() if attachment_id else con.execute('SELECT id FROM study_collections WHERE attachment_id IS NULL AND pasted_text=?',(text,)).fetchone()
                collection_id = existing[0] if existing else str(uuid.uuid4())
            uuid.UUID(collection_id)
            con.execute('INSERT INTO study_collections(id,attachment_id,pasted_text,updated_at) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET attachment_id=excluded.attachment_id,pasted_text=excluded.pasted_text',
                        (collection_id,attachment_id,text,now()))
            con.execute("UPDATE collection_exports SET state='stale' WHERE collection_id=?",(collection_id,))
        return {'id':collection_id,'job':self.submit(collection_id)}

    def submit(self, collection):
        with self.guard, self.db.connect() as con:
            if not con.execute('SELECT 1 FROM study_collections WHERE id=?',(collection,)).fetchone(): raise KeyError('Collection not found')
            previous = con.execute("SELECT id FROM collection_jobs WHERE collection_id=? AND state IN ('queued','running')",(collection,)).fetchone()
            if previous: return previous[0]
            job = con.execute('INSERT INTO collection_jobs(collection_id) VALUES(?)',(collection,)).lastrowid
            con.execute("UPDATE study_collections SET state='queued' WHERE id=?",(collection,))
        return job

    def cancel(self, job):
        with self.guard, self.db.connect() as con:
            con.execute("UPDATE collection_jobs SET state='cancelled' WHERE id=? AND state IN ('queued','running')",(job,))
            if job in self.events: self.events[job].set()
        return {'cancelled':True}

    def job(self,job):
        with self.db.connect() as con: row=con.execute('SELECT * FROM collection_jobs WHERE id=?',(job,)).fetchone()
        if not row: raise KeyError('Job not found')
        return dict(row)

    def _progress(self,job,phase,processed,total):
        with self.db.connect() as con: con.execute('UPDATE collection_jobs SET phase=?,processed=?,total=? WHERE id=?',(phase,processed,total,job))

    def _loop(self):
        while not self.stop.is_set():
            try:
                with self.db.connect() as con:
                    row=con.execute("SELECT * FROM collection_jobs WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
                    if not row:
                        for attachment in con.execute('SELECT id FROM syllabus_attachments WHERE active=1'):
                            try: self.attachment_access(attachment[0],refresh=True)
                            except (PermissionError,OSError,ValueError): pass
                        # A corpus fingerprint schedules new/changed/missing/revoked files, including new matches.
                        corpus=[tuple(r) for r in con.execute('SELECT f.id,f.path,f.content_hash,f.status,r.state,i.state,i.engine_version FROM files f JOIN roots r ON r.id=f.root_id LEFT JOIN intelligence_documents i ON i.file_id=f.id ORDER BY f.id')]
                        sources=[tuple(r) for r in con.execute('SELECT id,content_hash,active FROM syllabus_attachments ORDER BY id')]
                        settings=[tuple(r) for r in con.execute("SELECT key,value FROM collection_settings WHERE key='ocr_pack'")]
                        model_ready=self.intelligence.models.status()['ready'] if self.intelligence.enabled() else {}
                        signature=hashlib.sha256(json.dumps([corpus,sources,settings,model_ready,CONFIG]).encode()).hexdigest()
                        previous=con.execute("SELECT value FROM collection_settings WHERE key='corpus'").fetchone()
                        if not previous or previous[0]!=signature:
                            con.execute("INSERT INTO collection_settings VALUES('corpus',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(signature,))
                            for item in con.execute("SELECT id FROM study_collections WHERE state NOT IN ('queued','running','unavailable')"):
                                con.execute('INSERT INTO collection_jobs(collection_id) VALUES(?)',(item[0],))
                    else:
                        job,collection=row['id'],row['collection_id']
                        con.execute("UPDATE collection_jobs SET state='running',attempts=attempts+1 WHERE id=?",(job,))
                if row is None:
                    self.stop.wait(2); continue
                event=threading.Event()
                with self.guard: self.events[job]=event
                try:
                    self._organize(collection,job,event)
                    with self.guard,self.db.connect() as con:
                        if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
                        con.execute("UPDATE collection_jobs SET state='done' WHERE id=? AND state='running'",(job,))
                except Exception as exc:
                    interrupted=isinstance(exc,InterruptedError)
                    if not interrupted: log.exception('Collection job failed')
                    with self.db.connect() as con:
                        con.execute('UPDATE collection_jobs SET state=?,error=? WHERE id=?',('queued' if self.stop.is_set() else 'cancelled' if interrupted else 'failed',str(exc)[:1000],job))
                        con.execute('UPDATE study_collections SET state=? WHERE id=?',('cancelled' if interrupted else 'failed',collection))
                finally:
                    with self.guard: self.events.pop(job,None)
            except Exception: log.exception('Collection worker failed'); self.stop.wait(2)

    def _read_pages(self,key,path,content_hash,event,allowed,job):
        with self.db.connect() as con: pack=con.execute("SELECT value FROM collection_settings WHERE key='ocr_pack'").fetchone()[0]
        config=CONFIG+(':ocr' if pack else ':native')
        if pack: config+=':'+hashlib.sha256((Path(pack)/'pack.json').read_bytes()).hexdigest()[:16]
        vision_ready=self.intelligence.enabled() and self.intelligence.models.status()['ready'].get('vision',False)
        if vision_ready: config+=':qwen3-vl-0635d9d857d4'
        stopped=lambda:event.is_set() or self.stop.is_set() or not allowed()
        if stopped(): raise InterruptedError('Cancelled or source access changed')
        with self.db.connect() as con:
            envelope=con.execute('SELECT regions_json FROM visual_pages WHERE source_key=? AND content_hash=? AND config=? LIMIT 1',(key,content_hash,config)).fetchone()
        cached_envelope=json.loads(envelope[0]) if envelope else {}
        pages=cached_envelope.get('page_count') if isinstance(cached_envelope,dict) else None
        if not pages: pages=inspect_source(path,stopped)
        regions,issues=[],[]
        for number in range(1,min(pages,MAX_PAGES)+1):
            if event.is_set() or self.stop.is_set() or not allowed(): raise InterruptedError('Cancelled or source access changed')
            self._progress(job,'analyzing pages',number-1,pages)
            with self.db.connect() as con: cached=con.execute('SELECT * FROM visual_pages WHERE source_key=? AND content_hash=? AND page=? AND config=?',(key,content_hash,number,config)).fetchone()
            data=json.loads(cached['regions_json']) if cached else None
            if not isinstance(data,dict): data=None
            if data and data.get('retry_vision'):
                data['thumbnail']=base64.b64encode(cached['thumbnail']).decode()
            if not data or data.get('retry_ocr'):
                try:
                    data=inspect_page(path,number,pack,stopped,**({'resume':data} if data else {}))
                except InterruptedError: raise
                except Exception as exc:
                    issues.append(f'Page {number} could not be analyzed: {type(exc).__name__}. Review or retry this page.')
                    continue
            if not cached or data.get('retry_ocr') or data.get('retry_vision') or 'thumbnail' in data:
                if not allowed(): raise InterruptedError('Source access changed')
                if vision_ready and not any(r['kind']=='description' for r in data['regions']) and data.get('needs_visual') and (data['issues'] or any(r.get('uncertain') for r in data['regions'])):
                    if not allowed(): raise InterruptedError('Source permission changed')
                    data['issues']=[issue for issue in data['issues'] if not issue.startswith('Local visual model unavailable')]
                    data['retry_vision']=False
                    try:
                        description=self.intelligence.models.describe(data['thumbnail'],event)
                        if description:
                            data['regions'].append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,f'{key}:{content_hash}:{number}:vision')),
                                'page':number,'text':description,'kind':'description','region_type':'visual region',
                                'bbox':[0,0,*data['dimensions']],'confidence':None,'uncertain':True,
                                'engine':'qwen3-vl:2b@0635d9d857d4','model_version':'0635d9d857d4','quality':{'generated':True}})
                    except InterruptedError: raise
                    except Exception:
                        data['issues'].append('Local visual model unavailable; page needs review. Refresh to retry.')
                        data['retry_vision']=True
                if not allowed(): raise InterruptedError('Source permission changed')
                thumbnail=base64.b64decode(data.pop('thumbnail')) if 'thumbnail' in data else cached['thumbnail']
                with self.db.connect() as con:
                    con.execute('INSERT OR REPLACE INTO visual_pages VALUES(?,?,?,?,?,?,?,?)',(key,content_hash,number,config,'partial' if data.get('retry_ocr') or data.get('retry_vision') else 'ready',json.dumps(data),thumbnail,json.dumps(data['issues'])))
            regions.extend(data['regions']); issues.extend(f'Page {number}: {issue}' for issue in data['issues'])
            if number>=pages: break
        if pages>MAX_PAGES: issues.append(f'Only the first {MAX_PAGES} pages were analyzed; remaining pages need a separate source.')
        return regions,issues

    def _organize(self,collection,job,event):
        with self.db.connect() as con: row=dict(con.execute('SELECT * FROM study_collections WHERE id=?',(collection,)).fetchone())
        attachment=self.attachment_access(row['attachment_id'],refresh=True) if row['attachment_id'] else None
        source_version=attachment['content_hash'] if attachment else hashlib.sha256(row['pasted_text'].encode()).hexdigest()
        def allowed():
            if not attachment: return True
            try: return self.attachment_access(attachment['id'])['content_hash']==source_version
            except PermissionError: return False
        self._progress(job,'reading',0,1)
        regions,issues=self._read_pages('attachment:'+attachment['id'],attachment['path'],source_version,event,allowed,job) if attachment else ([{'text':row['pasted_text'],'engine':'pasted-text','page':None}],[])
        for region in regions: region['content_hash']=source_version
        if row['corrected'] and row['source_version']!=source_version:
            issues.append('The syllabus changed. Your edited outline was retained; compare it with the updated source before accepting new coverage.')
        extracted=extract_outline(collection,regions)
        outline=json.loads(row['outline_json']) if row['corrected'] else extracted
        with self.db.transaction(immediate=True) as con:
            current=con.execute('SELECT * FROM study_collections WHERE id=?',(collection,)).fetchone()
            if not allowed(): raise PermissionError('Syllabus access changed')
            if current['corrected']: outline=json.loads(current['outline_json'])
            revision=current['revision']+(current['source_version']!=source_version or current['outline_json']!=json.dumps(outline))
            con.execute('UPDATE study_collections SET subject=?,revision=?,source_version=?,outline_json=?,extracted_json=?,state=?,issues_json=?,updated_at=? WHERE id=?',
                        (outline['subject'],revision,source_version,json.dumps(outline),json.dumps(extracted),'matching',json.dumps(issues+extracted['issues']),now(),collection))
            con.execute('INSERT OR IGNORE INTO syllabus_revisions VALUES(?,?,?,?,?)',(collection,revision,source_version,json.dumps(outline),now()))
        with self.db.connect() as con: eligible=self.intelligence._eligible(con,{})
        # Prepare image-bearing/scanned eligible PDFs only; text remains available if OCR is absent.
        capabilities=self.vision_status()
        ocr_ready=capabilities['ocr_ready']
        use_embeddings=capabilities['models']['enabled'] and capabilities['models']['ready'].get('embedding',False)
        for file in eligible.values():
            if file['extension']!='.pdf' or file['content_hash']==source_version: continue
            with self.db.connect() as con: warning=con.execute("SELECT 1 FROM parser_warnings WHERE file_id=? AND message LIKE '%extractable text%'",(file['id'],)).fetchone()
            if warning or ocr_ready:
                def file_allowed(file=file):
                    with self.db.connect() as con:
                        current=permitted_file(con,file['id'],current=True)
                        return bool(current and current['content_hash']==file['content_hash'])
                try:
                    with self.db.connect() as con: before=[tuple(r) for r in con.execute('SELECT page,config,regions_json FROM visual_pages WHERE source_key=? AND content_hash=? ORDER BY page,config',('file:'+str(file['id']),file['content_hash']))]
                    _,file_issues=self._read_pages('file:'+str(file['id']),file['path'],file['content_hash'],event,file_allowed,job)
                    issues.extend(f"{file['filename']}: {issue}" for issue in file_issues)
                    with self.db.connect() as con:
                        after=[tuple(r) for r in con.execute('SELECT page,config,regions_json FROM visual_pages WHERE source_key=? AND content_hash=? ORDER BY page,config',('file:'+str(file['id']),file['content_hash']))]
                        if before!=after: con.execute("UPDATE intelligence_documents SET state='pending' WHERE file_id=?",(file['id'],))
                    self.intelligence._build_file(file['id'],use_embeddings,event)
                except InterruptedError: raise
                except Exception as exc: issues.append(f'A library PDF needs review: {type(exc).__name__}')
        from .syllabus_matching import match_topics
        assignments=match_topics(self.db,self.intelligence,outline,source_version,event,lambda done,total:self._progress(job,'matching topics',done,total),lambda:allowed() and not self.stop.is_set())
        if event.is_set() or self.stop.is_set() or not allowed(): raise InterruptedError('Cancelled or syllabus unavailable')
        with self.guard,self.db.transaction(immediate=True) as con:
            if event.is_set(): raise InterruptedError('Cancelled')
            current=con.execute('SELECT revision FROM study_collections WHERE id=?',(collection,)).fetchone()
            if current[0]!=revision: raise InterruptedError('Outline changed during matching; refresh it')
            con.execute("DELETE FROM topic_assignments WHERE collection_id=? AND decision='auto'",(collection,))
            for item in assignments:
                permitted=permitted_file(con,item['file_id'],current=True)
                if not permitted or permitted['content_hash']!=item['content_hash']: continue
                con.execute('INSERT INTO topic_assignments VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(collection_id,topic_id,file_id) DO UPDATE SET content_hash=excluded.content_hash,classification=excluded.classification,evidence_json=excluded.evidence_json,reason=excluded.reason',
                    (collection,item['topic_id'],item['file_id'],item['content_hash'],item['classification'],'auto',json.dumps(item['evidence']),item['reason']))
            con.execute("UPDATE study_collections SET state=?,issues_json=?,updated_at=? WHERE id=?",('partial' if issues or not list(topics(outline)) else 'ready',json.dumps(issues+extracted['issues']),now(),collection))
        self._progress(job,'creating shortcuts',0,1)
        if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
        self.prepare_export(collection)

    def outline(self,collection,value):
        value=validate_outline(value)
        self.detail(collection)
        with self.db.connect() as con:
            con.execute('UPDATE study_collections SET outline_json=?,subject=?,corrected=1,revision=revision+1 WHERE id=?',(json.dumps(value),value['subject'],collection))
            con.execute("UPDATE collection_exports SET state='stale' WHERE collection_id=?",(collection,))
        return {'job':self.submit(collection)}

    def detail(self,collection,topic_id=None,offset=0,limit=25):
        with self.db.connect() as con:
            row=con.execute('SELECT * FROM study_collections WHERE id=?',(collection,)).fetchone()
            if not row: raise KeyError('Collection not found')
            result=dict(row)
            if row['attachment_id']: self.attachment_access(row['attachment_id'])
            outline=json.loads(row['outline_json'])
            if 'units' not in outline: outline={'subject':row['subject'],'units':[],'issues':[]}
            valid_topics={t['id'] for t in topics(outline)}
            entries=[]
            for item in con.execute('SELECT * FROM topic_assignments WHERE collection_id=?',(collection,)):
                if item['topic_id'] not in valid_topics: continue
                if row['state'] in {'queued','matching','failed','cancelled'} and item['decision']=='auto': continue
                file=permitted_file(con,item['file_id'],current=True)
                if not file or file['content_hash']!=item['content_hash']: continue
                evidence=json.loads(item['evidence_json'])
                evidence=[e for e in evidence if con.execute('SELECT 1 FROM chunks WHERE id=? AND file_id=? AND content_hash=?',(e['chunk_id'],file['id'],file['content_hash'])).fetchone()]
                if not evidence: continue
                entries.append({**dict(item),'filename':file['filename'],'path':file['path'],'evidence':evidence})
            export=con.execute('SELECT id,state,error FROM collection_exports WHERE collection_id=? ORDER BY rowid DESC LIMIT 1',(collection,)).fetchone()
            job=con.execute('SELECT * FROM collection_jobs WHERE collection_id=? ORDER BY id DESC LIMIT 1',(collection,)).fetchone()
        # Use a fresh connection after the retrieval snapshot before returning evidence.
        with self.db.connect() as con:
            current=[]
            for entry in entries:
                file=permitted_file(con,entry['file_id'],current=True)
                if file and file['content_hash']==entry['content_hash']:
                    current.append({**entry,'filename':file['filename'],'path':file['path']})
        entries=current
        if row['attachment_id']: self.attachment_access(row['attachment_id'])
        coverage=[]
        for topic in topics(outline):
            matches=[a for a in entries if a['topic_id']==topic['id'] and a['decision']!='rejected']
            strong=[a for a in matches if a['decision']=='approved' or (a['decision']=='auto' and a['classification']=='substantive')]
            coverage.append({'id':topic['id'],'name':topic['name'],'unit':topic['unit'],'matches':len(strong),'review':len(matches)-len(strong)})
        selected=[a for a in entries if not topic_id or a['topic_id']==topic_id]
        return {k:v for k,v in result.items() if k not in {'pasted_text','outline_json','extracted_json','issues_json'}} | {'outline':outline,'issues':json.loads(row['issues_json']),
                'coverage':coverage,'topics_with_material':sum(t['matches']>0 for t in coverage),'gaps':sum(t['matches']==0 for t in coverage),
                'items':selected[offset:offset+limit],'total':len(selected),'offset':offset,'has_more':offset+limit<len(selected),'export':dict(export) if export else None,'job':dict(job) if job else None}

    def list(self):
        with self.db.connect() as con: rows=list(con.execute('SELECT id,subject,revision,state,attachment_id FROM study_collections ORDER BY updated_at DESC'))
        result=[]
        for row in rows:
            try:
                if row['attachment_id']: self.attachment_access(row['attachment_id'])
                result.append(dict(row))
            except PermissionError: result.append({'id':row['id'],'subject':'Unavailable syllabus','state':'unavailable','revision':row['revision']})
        return result

    def decide(self,collection,topic,file_id,decision,target=None):
        detail=self.detail(collection)
        ids={t['id'] for t in topics(detail['outline'])}
        if topic not in ids or (target and target not in ids) or decision not in {'approved','rejected','auto'}: raise ValueError('Invalid assignment correction')
        with self.db.connect() as con:
            if not permitted_file(con,file_id,current=True): raise PermissionError('File unavailable')
            if target:
                original=con.execute('SELECT * FROM topic_assignments WHERE collection_id=? AND topic_id=? AND file_id=?',(collection,topic,file_id)).fetchone()
                if not original: raise KeyError('Assignment unavailable')
                con.execute('INSERT OR REPLACE INTO topic_assignments VALUES(?,?,?,?,?,?,?,?)',(collection,target,file_id,original['content_hash'],original['classification'],'approved',original['evidence_json'],'Moved by you; review source evidence'))
                decision='rejected'
            con.execute('UPDATE topic_assignments SET decision=? WHERE collection_id=? AND topic_id=? AND file_id=?',(decision,collection,topic,file_id))
        self.prepare_export(collection)
        return {'saved':True}

    def prepare_export(self,collection):
        destination=self.destination()
        if not destination: return None
        try:
            detail=self.detail(collection,limit=100000)
            outline=detail['outline']; topic_map={t['id']:t for t in topics(outline)}; items=[]
            for item in detail['items']:
                if item['decision']=='rejected' or (item['decision']!='approved' and item['classification']!='substantive'): continue
                topic=topic_map.get(item['topic_id'])
                if not topic: continue
                items.append({'id':f"{topic['id']}:{item['file_id']}", 'parts':[topic['unit']+' ['+topic['unit_id'][:6]+']',*topic['parents'],topic['name']+' ['+topic['id'][:6]+']'],
                              'name':item['filename'],'reference':'file:'+str(item['file_id'])})
            if detail['attachment_id']:
                items.append({'id':'syllabus','parts':[],'name':'Syllabus','reference':'attachment:'+detail['attachment_id']})
            subject=detail['subject']; revision=detail['revision']
        except PermissionError:
            items=[]; subject='Unavailable syllabus'; revision=0
        plan={'collection_id':collection,'destination':destination,'subject':subject,'revision':revision,'items':items}
        with self.db.connect() as con:
            previous=con.execute('SELECT * FROM collection_exports WHERE collection_id=? AND destination_id=?',(collection,destination['id'])).fetchone()
            export_id=previous['id'] if previous else str(uuid.uuid4())
            payload=json.dumps(plan)
            if previous and previous['plan_json']==payload and previous['state']=='done': return export_id
            con.execute("INSERT INTO collection_exports VALUES(?,?,?,?,?,'pending',NULL) ON CONFLICT(collection_id,destination_id) DO UPDATE SET revision=excluded.revision,plan_json=excluded.plan_json,state='pending',error=NULL",
                        (export_id,collection,destination['id'],revision,payload))
        return export_id

    def pending_exports(self):
        with self.db.connect() as con: stale=[row[0] for row in con.execute("SELECT collection_id FROM collection_exports WHERE state='stale'")]
        for collection in stale: self.prepare_export(collection)
        with self.db.connect() as con: rows=list(con.execute("SELECT e.* FROM collection_exports e JOIN collection_destinations d ON d.id=e.destination_id WHERE e.state='pending' AND d.active=1"))
        return [{**dict(row),'plan':json.loads(row['plan_json'])} for row in rows]

    def export_state(self,export_id,state,plan,error=None):
        if state not in {'writing','done','failed'}: raise ValueError('Invalid export state')
        with self.db.connect() as con:
            changed=con.execute("UPDATE collection_exports SET state=?,error=? WHERE id=? AND plan_json=? AND state IN ('pending','writing') AND destination_id IN (SELECT id FROM collection_destinations WHERE active=1)",(state,error,export_id,plan)).rowcount
        return {'accepted':bool(changed)}

    def export_access(self,export_id):
        with self.db.connect() as con:
            row=con.execute("SELECT e.* FROM collection_exports e JOIN collection_destinations d ON d.id=e.destination_id WHERE e.id=? AND d.active=1 AND e.state IN ('pending','writing')",(export_id,)).fetchone()
        if not row: raise PermissionError('Export was cancelled or its permission/revision changed')
        return {'plan':row['plan_json']}

    def cancel_export(self,export_id):
        with self.db.connect() as con: con.execute("UPDATE collection_exports SET state='cancelled' WHERE id=?",(export_id,))
        return {'cancelled':True}

    def reference(self,reference):
        kind,identifier=reference.split(':',1)
        if kind=='attachment':
            uuid.UUID(identifier); return self.attachment_access(identifier)
        if kind!='file' or not identifier.isdigit(): raise ValueError('Invalid document reference')
        with self.db.connect() as con:
            file=permitted_file(con,int(identifier),current=True)
            if not file: raise PermissionError('Source is unavailable')
            return dict(file)

    def page(self,key,version,page):
        source=self.reference(key)
        if source['content_hash']!=version: raise PermissionError('Source evidence is obsolete')
        with self.db.connect() as con: row=con.execute('SELECT thumbnail,regions_json FROM visual_pages WHERE source_key=? AND content_hash=? AND page=? ORDER BY config DESC LIMIT 1',(key,version,page)).fetchone()
        if not row: raise KeyError('Page preview unavailable')
        payload=json.loads(row['regions_json'])
        if self.reference(key)['content_hash']!=version: raise PermissionError('Page access changed')
        return {'image':'data:image/jpeg;base64,'+base64.b64encode(row['thumbnail']).decode(),'evidence':payload,'dimensions':payload.get('dimensions')}
