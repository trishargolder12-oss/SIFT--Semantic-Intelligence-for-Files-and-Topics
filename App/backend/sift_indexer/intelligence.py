"""Cancellable local discovery, versioned evidence and virtual library metadata."""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import struct
import threading
import uuid
from datetime import datetime, timezone

from .access import permitted_file
from .discovery_language import corrected_terms, interpret
from .grouping import KINDS, assignments, ensure_group, generated_groups, normalize
from .local_models import CATALOG, LocalModels

log = logging.getLogger(__name__)
ENGINE_VERSION = 1
EMBEDDING_VERSION = 'all-minilm:22m@1b226e2802db'


def now():
    return datetime.now(timezone.utc).isoformat()


def chunk_blocks(blocks: list[dict]):
    offset, position = 0, 0
    for block in blocks:
        text = block['text']
        words = list(re.finditer(r'\S+', text))
        start = 0
        while start < len(words):
            end = min(start + 160, len(words))
            while end > start + 1 and words[end - 1].end() - words[start].start() > 1100:
                end -= 1
            left, right = words[start].start(), words[end - 1].end()
            # Exceptionally long tokens are split without silently discarding characters.
            for part in range(left, right, 1100):
                yield {'position': position, 'location': block['location'], 'start_char': offset + part, 'text': text[part:min(part + 1100, right)], 'region_id':block.get('region_id')}
                position += 1
            if end == len(words): break
            start = max(start + 1, end - 24)
        offset += len(text) + 2
    if not position:
        yield {'position': 0, 'location': None, 'start_char': 0, 'text': ''}


class Intelligence:
    def __init__(self, db, models=None):
        self.db = db
        self.models = models or LocalModels()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.guard = threading.Lock()
        self.events: dict[int, threading.Event] = {}
        self.worker: threading.Thread | None = None
        self.chat_worker: threading.Thread | None = None
        with db.connect() as con:
            con.execute("UPDATE intelligence_jobs SET state=CASE WHEN kind='chat' THEN 'cancelled' ELSE 'queued' END,error='Service restarted; unfinished work recovered' WHERE state='running'")
            con.execute("UPDATE intelligence_documents SET state='pending' WHERE engine_version!=?", (ENGINE_VERSION,))

    def start(self):
        if not self.worker:
            self.worker = threading.Thread(target=self._loop, daemon=True, name='sift-discovery')
            self.chat_worker = threading.Thread(target=self._loop, args=(True,), daemon=True, name='sift-discovery-chat')
            self.worker.start()
            self.chat_worker.start()

    def close(self):
        self.stop.set(); self.wake.set()
        with self.guard:
            for event in self.events.values(): event.set()
        if self.worker: self.worker.join(timeout=17)
        if self.chat_worker: self.chat_worker.join(timeout=17)

    def enabled(self):
        with self.db.connect() as con:
            return con.execute("SELECT value FROM intelligence_settings WHERE key='models_enabled'").fetchone()[0] == 'true'

    def configure(self, enabled: bool):
        with self.db.connect() as con:
            con.execute("UPDATE intelligence_settings SET value=? WHERE key='models_enabled'", ('true' if enabled else 'false',))
        if enabled: self.submit('rebuild', {'all': True})
        else:
            with self.db.connect() as con:
                jobs = [r[0] for r in con.execute("SELECT id FROM intelligence_jobs WHERE kind='download' AND state IN ('queued','running')")]
            for job_id in jobs: self.cancel(job_id)
        return self.status()

    def status(self):
        enabled = self.enabled()
        status = self.models.status() if enabled else {'available': False, 'ready': {role: False for role in CATALOG}}
        with self.db.connect() as con:
            counts = dict(con.execute("SELECT i.state,COUNT(*) FROM intelligence_documents i JOIN files f ON f.id=i.file_id JOIN roots r ON r.id=f.root_id WHERE r.state IN ('active','paused') AND f.status='indexed' GROUP BY i.state"))
            job = con.execute("SELECT id,kind,state,processed,total,error FROM intelligence_jobs WHERE state IN ('queued','running') ORDER BY id LIMIT 1").fetchone()
        return {'enabled': enabled, **status, 'catalog': CATALOG, 'mode': 'hybrid' if enabled and status['ready']['embedding'] else 'keyword', 'documents': counts, 'job': dict(job) if job else None,
                'storage': 'Chunks, vectors, groups and conversations: SIFT app data. Models: Ollama local model directory (normally %USERPROFILE%\\.ollama\\models).'}

    def submit(self, kind: str, payload: dict) -> dict:
        if kind not in ('chat', 'rebuild', 'download'): raise ValueError('Invalid intelligence job')
        with self.db.transaction(immediate=True) as con:
            if kind == 'chat':
                conversation = payload.get('conversation_id') or str(uuid.uuid4())
                uuid.UUID(conversation)
                con.execute('INSERT INTO conversations VALUES(?,?) ON CONFLICT(id) DO NOTHING', (conversation, now()))
                if con.execute("SELECT 1 FROM intelligence_jobs WHERE kind='chat' AND conversation_id=? AND state IN ('queued','running')", (conversation,)).fetchone():
                    raise ValueError('Wait for or cancel the current request first')
                payload['conversation_id'] = conversation
            else: conversation = None
            cursor = con.execute("INSERT INTO intelligence_jobs(kind,state,payload_json,conversation_id,created_at) VALUES(?,'queued',?,?,?)", (kind, json.dumps(payload), conversation, now()))
            job_id = cursor.lastrowid
        self.wake.set()
        return {'id': job_id, 'conversation_id': conversation}

    def cancel(self, job_id: int):
        with self.guard:
            with self.db.connect() as con:
                job = con.execute('SELECT kind,state,payload_json FROM intelligence_jobs WHERE id=?', (job_id,)).fetchone()
                if not job or job['state'] not in ('queued', 'running'): return False
                event = self.events.get(job_id)
                if event: event.set()
                cursor = con.execute("UPDATE intelligence_jobs SET state='cancelled',finished_at=? WHERE id=? AND state IN ('queued','running')", (now(), job_id))
                changed = cursor.rowcount > 0
                if changed and job['kind'] == 'rebuild':
                    ids = json.loads(job['payload_json']).get('ids')
                    if ids: con.executemany("UPDATE intelligence_documents SET state='deferred' WHERE file_id=? AND state='pending'", [(i,) for i in ids])
                    else: con.execute("UPDATE intelligence_documents SET state='deferred' WHERE state='pending'")
                return changed

    def job(self, job_id: int):
        with self.db.connect() as con:
            row = con.execute('SELECT id,kind,state,processed,total,created_at,finished_at,error,turn_id,conversation_id FROM intelligence_jobs WHERE id=?', (job_id,)).fetchone()
        if not row: raise KeyError('Intelligence job not found')
        result = dict(row)
        if row['turn_id'] and row['state'] == 'done': result['result'] = self.turn(row['turn_id'])
        return result

    def _progress(self, job_id, processed, total):
        with self.db.connect() as con:
            con.execute('UPDATE intelligence_jobs SET processed=?,total=? WHERE id=?', (processed, total, job_id))

    def _loop(self, chat=False):
        while not self.stop.is_set():
            try:
                with self.db.connect() as con:
                    row = con.execute("SELECT * FROM intelligence_jobs WHERE state='queued' AND " + ("kind='chat'" if chat else "kind!='chat'") + " ORDER BY CASE kind WHEN 'download' THEN 0 ELSE 1 END,id LIMIT 1").fetchone()
                    if not row and not chat:
                        ids = [r[0] for r in con.execute("SELECT i.file_id FROM intelligence_documents i JOIN files f ON f.id=i.file_id JOIN roots r ON r.id=f.root_id WHERE i.state='pending' AND f.status='indexed' AND r.state IN ('active','paused') LIMIT 8")]
                        if ids:
                            con.execute("INSERT INTO intelligence_jobs(kind,state,payload_json,created_at) VALUES('rebuild','queued',?,?)", (json.dumps({'ids': ids}), now()))
                if not row:
                    self.wake.wait(.4); self.wake.clear(); continue
                job = dict(row); job_id = job['id']; event = threading.Event()
                with self.guard:
                    self.events[job_id] = event
                    with self.db.connect() as con:
                        cursor = con.execute("UPDATE intelligence_jobs SET state='running',error=NULL WHERE id=? AND state='queued'", (job_id,))
                    if not cursor.rowcount: self.events.pop(job_id); continue
                try:
                    payload = json.loads(job['payload_json'])
                    if job['kind'] == 'chat':
                        turn_id = self._chat(payload, event, job_id)
                        with self.db.connect() as con: con.execute('UPDATE intelligence_jobs SET turn_id=? WHERE id=?', (turn_id, job_id))
                    elif job['kind'] == 'download':
                        self.models.download(payload['role'], event, lambda a, b: self._progress(job_id, a, b))
                        if payload['role'] == 'embedding': self.submit('rebuild', {'all': True})
                    else: self._rebuild(payload, job_id, event)
                    if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
                    with self.db.connect() as con: con.execute("UPDATE intelligence_jobs SET state='done',finished_at=? WHERE id=? AND state='running'", (now(), job_id))
                except InterruptedError:
                    with self.db.connect() as con:
                        recovering = self.stop.is_set() and job['kind'] != 'chat'
                        con.execute("UPDATE intelligence_jobs SET state=?,finished_at=? WHERE id=? AND state IN ('queued','running')", ('queued' if recovering else 'cancelled', None if recovering else now(), job_id))
                        if job['kind'] == 'rebuild' and not recovering:
                            ids = payload.get('ids')
                            if ids: con.executemany("UPDATE intelligence_documents SET state='deferred' WHERE file_id=? AND state='pending'", [(i,) for i in ids])
                            else: con.execute("UPDATE intelligence_documents SET state='deferred' WHERE state='pending'")
                except Exception as exc:
                    log.exception('Intelligence job %s failed', job_id)
                    with self.db.connect() as con: con.execute("UPDATE intelligence_jobs SET state='failed',error=?,finished_at=? WHERE id=? AND state='running'", (str(exc)[:1000], now(), job_id))
                    if job['kind'] == 'rebuild':
                        with self.db.connect() as con: con.execute("UPDATE intelligence_documents SET state='deferred' WHERE state='pending'")
                finally:
                    with self.guard: self.events.pop(job_id, None)
            except Exception:
                log.exception('Discovery worker recovered from an error')
                self.stop.wait(1)

    def _rebuild(self, payload, job_id, event):
        with self.db.connect() as con:
            ids = payload.get('ids') if not payload.get('all') else [r[0] for r in con.execute("SELECT f.id FROM files f JOIN roots r ON r.id=f.root_id WHERE f.status='indexed' AND r.state IN ('active','paused')")]
        ready = self.models.status()['ready']['embedding'] if self.enabled() else False
        for index, file_id in enumerate(ids or []):
            if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
            self._build_file(file_id, ready, event)
            self._progress(job_id, index + 1, len(ids))

    def _build_file(self, file_id, embeddings, event):
        with self.db.transaction() as con:
            file = permitted_file(con, file_id, current=True)
            if not file or not file['content_hash']:
                con.execute("UPDATE intelligence_documents SET state='unavailable' WHERE file_id=?", (file_id,)); return
            file = dict(file)
            document = dict(con.execute('SELECT * FROM documents WHERE file_id=?', (file_id,)).fetchone())
            state = con.execute('SELECT * FROM intelligence_documents WHERE file_id=?', (file_id,)).fetchone()
            complete = state and state['state'] == 'ready' and state['content_hash'] == file['content_hash'] and state['engine_version'] == ENGINE_VERSION and state['parser_version'] == document['parser_version']
            if complete and (not embeddings or not con.execute('SELECT 1 FROM chunks WHERE file_id=? AND (embedding IS NULL OR embedding_model!=?) LIMIT 1', (file_id, EMBEDDING_VERSION)).fetchone()): return
            blocks = [dict(b) for b in con.execute('SELECT location,text FROM text_blocks WHERE file_id=? ORDER BY position', (file_id,))]
            previous_chunks = [dict(c) for c in con.execute('SELECT * FROM chunks WHERE file_id=? AND content_hash=? ORDER BY position', (file_id, file['content_hash']))]
        if not blocks and document['text']: blocks = [{'location': 'Extracted text', 'text': document['text']}]
        with self.db.connect() as con:
            for page in con.execute('SELECT page,regions_json FROM visual_pages WHERE rowid IN (SELECT MAX(rowid) FROM visual_pages WHERE source_key=? AND content_hash=? GROUP BY page)',('file:'+str(file_id),file['content_hash'])):
                payload=json.loads(page['regions_json'])
                for region in payload.get('regions',[]):
                    if region['engine']=='pdfium-4.30.0': continue
                    if region['engine'].startswith('PP-OCR') and not region.get('index_only'): continue
                    label='Generated visual description' if region['kind']=='description' else 'OCR transcription'
                    blocks.append({'location':f"Page {page['page']} · {label}",'text':region['text'],'region_id':region['id']})
        chunks = list(chunk_blocks(blocks))
        same_chunks = len(previous_chunks) == len(chunks) and all(all(old.get(key) == chunk.get(key) for key in ['position', 'location', 'start_char', 'text', 'region_id']) for old, chunk in zip(previous_chunks, chunks))
        vectors = [chunk['embedding'] if chunk['embedding_model'] == EMBEDDING_VERSION else None for chunk in previous_chunks] if same_chunks else [None] * len(chunks)
        if embeddings:
            missing = [i for i, vector in enumerate(vectors) if vector is None]
            for start in range(0, len(missing), 12):
                with self.db.connect() as con:
                    current = permitted_file(con, file_id, current=True)
                    if not current or current['content_hash'] != file['content_hash']: return
                if not self.enabled(): break
                indices = missing[start:start+12]
                try:
                    for index, vector in zip(indices, self.models.embed([chunks[i]['text'] or file['filename'] for i in indices], event)):
                        vectors[index] = vector
                except InterruptedError: raise
                except Exception:
                    log.warning('Local embeddings unavailable; publishing keyword evidence', exc_info=True); break
        known = self._subject_profiles()
        generated = generated_groups(file, document['text'], document['title'], known)
        if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
        with self.db.transaction(immediate=True) as con:
            current = permitted_file(con, file_id, current=True)
            if not current or current['content_hash'] != file['content_hash']: return
            if same_chunks:
                con.executemany('UPDATE chunks SET embedding=?,embedding_model=? WHERE id=?', [(vectors[i], EMBEDDING_VERSION if vectors[i] else None, chunk['id']) for i, chunk in enumerate(previous_chunks)])
            else:
                con.execute('DELETE FROM chunks WHERE file_id=?', (file_id,))
                con.executemany('INSERT INTO chunks(file_id,content_hash,position,location,start_char,text,embedding,embedding_model,region_id) VALUES(?,?,?,?,?,?,?,?,?)',
                    [(file_id, file['content_hash'], c['position'], c['location'], c['start_char'], c['text'], vectors[i], EMBEDDING_VERSION if vectors[i] else None,c.get('region_id')) for i, c in enumerate(chunks)])
            con.execute("DELETE FROM group_assignments WHERE file_id=? AND source='auto'", (file_id,))
            for kind, name, reason in generated:
                group_id = ensure_group(con, kind, name)
                con.execute("INSERT OR IGNORE INTO group_assignments VALUES(?,?,'auto',?,?)", (file_id, group_id, file['content_hash'], reason))
            con.execute("UPDATE intelligence_documents SET content_hash=?,parser_version=?,engine_version=?,state='ready',published_at=? WHERE file_id=?", (file['content_hash'], document['parser_version'], ENGINE_VERSION, now(), file_id))
            if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')

    def _subject_profiles(self):
        with self.db.connect() as con:
            rows = list(con.execute("SELECT g.*,MIN(f.id) AS sample_id FROM library_groups g JOIN group_assignments a ON a.group_id=g.id JOIN files f ON f.id=a.file_id JOIN roots r ON r.id=f.root_id WHERE g.kind='subject' AND f.status='indexed' AND r.state IN ('active','paused') GROUP BY g.id"))
            return [dict(row) for row in rows if permitted_file(con, row['sample_id'], current=True)]

    def groups(self):
        visible: dict[int, dict] = {}
        with self.db.connect() as con:
            ids = con.execute("SELECT f.id FROM files f JOIN roots r ON r.id=f.root_id JOIN intelligence_documents i ON i.file_id=f.id WHERE f.status='indexed' AND r.state IN ('active','paused') AND i.state='ready' AND i.content_hash=f.content_hash")
            for (file_id,) in list(ids):
                file = permitted_file(con, file_id, current=True)
                if not file: continue
                for group in assignments(con, file_id, file['content_hash']):
                    entry = visible.setdefault(group['id'], {**group, 'count': 0})
                    entry['count'] += 1
        return sorted(visible.values(), key=lambda x: (KINDS.index(x['kind']), x['name'].casefold()))

    def correct(self, file_id: int, kinds: dict):
        with self.db.transaction(immediate=True) as con:
            file = permitted_file(con, file_id, current=True)
            if not file: raise PermissionError('Document is no longer accessible')
            for kind, names in kinds.items():
                if kind not in KINDS or not isinstance(names, list) or len(names) > 12 or any(not isinstance(n, str) or not n.strip() or len(n) > 100 for n in names): raise ValueError('Invalid section correction')
                con.execute('INSERT INTO group_corrections VALUES(?,?,?) ON CONFLICT(file_id,kind) DO UPDATE SET updated_at=excluded.updated_at', (file_id, kind, now()))
                con.execute("DELETE FROM group_assignments WHERE file_id=? AND source='user' AND group_id IN (SELECT id FROM library_groups WHERE kind=?)", (file_id, kind))
                for name in names or (['Uncategorized'] if kind == 'subject' else []):
                    group_id = ensure_group(con, kind, name)
                    con.execute("INSERT OR IGNORE INTO group_assignments VALUES(?,?,'user',NULL,'Your correction')", (file_id, group_id))
        return self.file_groups(file_id)

    def file_groups(self, file_id):
        with self.db.connect() as con:
            file = permitted_file(con, file_id, current=True)
            if not file: raise PermissionError('Document is no longer accessible')
            return assignments(con, file_id, file['content_hash'])

    def rename(self, group_id: int, name: str):
        if not isinstance(name, str) or not name.strip() or len(name) > 100: raise ValueError('Use a section name of 1–100 characters')
        if group_id not in {g['id'] for g in self.groups()}: raise PermissionError('Section is not available in approved folders')
        with self.db.connect() as con: con.execute('UPDATE library_groups SET name=? WHERE id=?', (name.strip(), group_id))
        return {'id': group_id, 'name': name.strip()}

    def _eligible(self, con, intent):
        rows = con.execute("SELECT f.*,r.path AS root_path,r.state AS root_state,d.title FROM files f JOIN roots r ON r.id=f.root_id JOIN documents d ON d.file_id=f.id JOIN intelligence_documents i ON i.file_id=f.id WHERE r.state IN ('active','paused') AND f.status='indexed' AND i.state='ready' AND i.content_hash=f.content_hash AND i.engine_version=?", (ENGINE_VERSION,))
        result = {}
        for row in rows:
            if row['id'] in intent.get('excluded_ids', []): continue
            if intent.get('root_id') and row['root_id'] != intent['root_id']: continue
            if intent.get('extension') and row['extension'] != intent['extension']: continue
            if intent.get('included_extensions') and row['extension'] not in intent['included_extensions']: continue
            if row['extension'] in intent.get('excluded_extensions', []): continue
            if intent.get('only_id') and row['id'] != intent['only_id']: continue
            if intent.get('only_version') and row['content_hash'] != intent['only_version']: continue
            if not permitted_file(con, row['id'], current=True): continue
            if intent.get('after') or intent.get('before'):
                try:
                    stamp = datetime.fromtimestamp(row['modified_ns']/1e9, timezone.utc).isoformat() if intent.get('date_field') == 'modified' else row['discovered_at']
                    if intent.get('after') and stamp < intent['after']: continue
                    if intent.get('before') and stamp >= intent['before']: continue
                except (TypeError, ValueError, OverflowError): continue
            groups = assignments(con, row['id'], row['content_hash'])
            if intent.get('document_type') and not any(g['kind'] == 'type' and normalize(intent['document_type']) in (normalize(g['name']), normalize(g['original_name'])) for g in groups): continue
            if intent.get('group_id') and not any(g['id'] == intent['group_id'] for g in groups): continue
            result[row['id']] = {**dict(row), 'group_context': ' '.join(g['name'] + ' ' + g['original_name'] for g in groups)}
        return result

    def retrieve(self, intent, event, model_ready=None):
        model_ready = model_ready or {'embedding': False, 'intent': False}
        query_vector = None
        semantic_used = False
        if model_ready['embedding'] and intent.get('query') and self.enabled():
            try: query_vector = struct.unpack('<384f', self.models.embed([intent['query']], event)[0])
            except InterruptedError: raise
            except Exception: log.warning('Semantic query unavailable; using keywords')
        with self.db.transaction() as con:
            eligible = self._eligible(con, intent)
            con.execute('CREATE TEMP TABLE discovery_allowed(file_id INTEGER PRIMARY KEY)')
            con.executemany('INSERT INTO discovery_allowed VALUES(?)', [(file_id,) for file_id in eligible])
            vocabulary = set()
            # Build spelling vocabulary only from permitted, current evidence.
            for file in eligible.values(): vocabulary.update(normalize(file['filename'] + ' ' + file['title'] + ' ' + file['group_context']).split())
            for row in con.execute('SELECT c.file_id,c.text FROM chunks c JOIN discovery_allowed a ON a.file_id=c.file_id'):
                if event.is_set(): raise InterruptedError('Cancelled')
                if row['file_id'] in eligible: vocabulary.update(normalize(row['text']).split())
            terms, corrections = corrected_terms(intent.get('query', ''), vocabulary)
            lexical = set()
            if terms:
                expression = ' OR '.join('"' + term.replace('"', '') + '"' for term in terms)
                lexical = {r[0] for r in con.execute("SELECT c.id FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid JOIN discovery_allowed a ON a.file_id=c.file_id JOIN files f ON f.id=c.file_id JOIN roots r ON r.id=f.root_id JOIN intelligence_documents i ON i.file_id=f.id WHERE chunks_fts MATCH ? AND r.state IN ('active','paused') AND f.status='indexed' AND i.state='ready' AND c.content_hash=f.content_hash", (expression,)) if r[0]}
            ranked = {}
            for chunk in con.execute('SELECT c.* FROM chunks c JOIN discovery_allowed a ON a.file_id=c.file_id'):
                if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
                file = eligible.get(chunk['file_id'])
                if not file or chunk['content_hash'] != file['content_hash']: continue
                title = normalize(file['filename'] + ' ' + file['title'] + ' ' + file['group_context'])
                words = set(normalize(chunk['text'] + ' ' + title).split())
                matched = [term for term in terms if any(word == term or (len(term) >= 4 and word.startswith(term)) for word in words)]
                coverage = len(matched) / max(len(terms), 1)
                lexical_score = coverage * .8 + (sum(term in title for term in terms) / max(len(terms), 1)) * .2
                semantic = 0.
                if query_vector and chunk['embedding'] and len(chunk['embedding']) == 1536 and chunk['embedding_model'] == EMBEDDING_VERSION:
                    vector = struct.unpack('<384f', chunk['embedding'])
                    if all(math.isfinite(v) for v in vector) and abs(sum(v*v for v in vector)-1) < .01:
                        semantic_used = True
                        semantic = sum(a*b for a, b in zip(query_vector, vector))
                structured = not terms and any(intent.get(key) for key in ['document_type', 'root_id', 'extension', 'included_extensions', 'excluded_extensions', 'only_id', 'group_id', 'after', 'before'])
                if not structured and not ((chunk['id'] in lexical or any(term in title for term in terms)) and coverage >= .5) and semantic < .45: continue
                score = max(lexical_score, .7*semantic + .3*lexical_score) if terms else .7
                reason = 'Section membership' if intent.get('group_id') else 'Matches your filters' if structured else 'Matching words: ' + ', '.join(matched) if matched else 'Related meaning from the local embedding model; review this likely match'
                ref = {'file_id': file['id'], 'chunk_id': chunk['id'], 'version': file['content_hash'], 'root_id': file['root_id'], 'score': round(score, 5), 'reason': reason, 'likely': score < .6 or (not matched and bool(terms))}
                if file['id'] not in ranked or ranked[file['id']]['score'] < score: ranked[file['id']] = ref
        refs = sorted(ranked.values(), key=lambda r: (-r['score'], r['file_id']))
        return refs, corrections, 'hybrid' if semantic_used else 'keyword'

    def _chat(self, payload, event, job_id):
        conversation = payload['conversation_id']
        previous, prior_refs = None, []
        previous_detail = {}
        with self.db.connect() as con:
            row = con.execute('SELECT * FROM discovery_turns WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1', (conversation,)).fetchone()
            if row:
                previous = json.loads(row['intent_json'])
                previous_detail = json.loads(row['detail_json'])
                context = payload.get('result_context')
                if context and context['turn_id'] != row['id']:
                    previous = None
                else:
                    offset = context['offset'] if context else 0
                    # Immutable slots, not a compacted list of currently permitted cards.
                    for ref in json.loads(row['refs_json'])[offset:offset+10]:
                        prior_refs.append({**ref, 'available': bool(self._card(con, ref))})
            roots = [dict(r) for r in con.execute("SELECT id,path,state FROM roots WHERE state IN ('active','paused')")]
        intent, clarification, options = interpret(payload['message'], previous, prior_refs, self.groups(), roots, payload.get('timezone_offset', 0))
        if previous and normalize(payload['message']) in {normalize(option) for option in previous_detail.get('options', [])}:
            intent = {**previous}
            if 'folder' in (previous_detail.get('clarification') or '').lower():
                matches = [root for root in roots if normalize(root['path'].replace('\\', '/').split('/')[-1]) == normalize(payload['message'])]
                if len(matches) == 1:
                    intent['root_id'] = matches[0]['id']; clarification, options = None, []
            else:
                intent['query'] = payload['message']; clarification, options = None, []
        # Explicit UI filters can narrow access but never expand the approved root registry.
        for key, value in payload.get('filters', {}).items():
            if key in ('root_id', 'extension', 'group_id') and value: intent[key] = value
        if intent.get('extension') and (intent['extension'] in intent.get('excluded_extensions', []) or (intent.get('included_extensions') and intent['extension'] not in intent['included_extensions'])):
            clarification = 'The selected file type conflicts with your message. Which file formats should I use?'
        if payload.get('filters', {}).get('group_id'):
            intent['query'] = ''; clarification = None
        refs, corrections, mode = [], [], 'keyword'
        ready = self.models.status()['ready'] if self.enabled() else {'embedding': False, 'intent': False}
        if not clarification:
            if not intent.get('query') and not any(intent.get(k) for k in ['document_type', 'extension', 'included_extensions', 'excluded_extensions', 'only_id', 'root_id', 'group_id', 'after', 'before']):
                clarification = 'What subject, topic or file would you like me to find?'
            else:
                if ready['intent'] and self.enabled() and not previous and intent.get('query'):
                    try:
                        suggested = self.models.interpret(payload['message'], event)
                        if suggested: intent['model_query'] = suggested
                    except InterruptedError: raise
                    except Exception: log.warning('Local interpretation unavailable; using offline rules')
                refs, corrections, mode = self.retrieve(intent, event, ready)
                if not refs and intent.get('model_query'):
                    refs, corrections, mode = self.retrieve({**intent, 'query': intent['model_query']}, event, ready)
                if not refs and intent.get('only_id'):
                    clarification = 'That numbered result is no longer available or has changed. Please search again.'
        if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
        turn_id = str(uuid.uuid4())
        detail = {'clarification': clarification, 'options': options, 'corrections': corrections, 'expansion': intent.get('expansion'), 'mode': mode}
        # Serialize publication with cancel(): a request cannot report cancellation after it published.
        with self.guard:
            with self.db.transaction(immediate=True) as con:
                if event.is_set() or self.stop.is_set(): raise InterruptedError('Cancelled')
                refs = [ref for ref in refs if (file := permitted_file(con, ref['file_id'], current=True)) and file['content_hash'] == ref['version']]
                con.execute('INSERT INTO discovery_turns VALUES(?,?,?,?,?,?,?,?)', (turn_id, conversation, now(), payload['message'], json.dumps(intent), 'clarify' if clarification else 'found' if refs else 'no_match', json.dumps(refs), json.dumps(detail)))
                con.execute("UPDATE intelligence_jobs SET state='done',turn_id=?,finished_at=? WHERE id=? AND state='running'", (turn_id, now(), job_id))
        return turn_id

    def _card(self, con, ref):
        file = permitted_file(con, ref['file_id'], current=True)
        if not file or file['content_hash'] != ref['version']: return None
        chunk = con.execute("SELECT c.* FROM chunks c JOIN intelligence_documents i ON i.file_id=c.file_id JOIN documents d ON d.file_id=c.file_id WHERE c.id=? AND c.file_id=? AND c.content_hash=? AND i.state='ready' AND i.content_hash=c.content_hash AND i.engine_version=? AND i.parser_version=d.parser_version", (ref['chunk_id'], ref['file_id'], ref['version'], ENGINE_VERSION)).fetchone()
        if not chunk: return None
        return {'id': file['id'], 'filename': file['filename'], 'title': file['title'], 'path': file['path'], 'root_id': file['root_id'], 'folder': file['root_path'], 'extension': file['extension'], 'added_at': file['discovered_at'], 'modified_ns': file['modified_ns'], 'location': chunk['location'], 'excerpt': chunk['text'], 'reason': ref['reason'], 'likely': ref['likely'], 'groups': assignments(con, file['id'], file['content_hash'])}

    def turn(self, turn_id, offset=0, limit=10):
        with self.db.connect() as con:
            row = con.execute('SELECT * FROM discovery_turns WHERE id=?', (turn_id,)).fetchone()
            if not row: raise KeyError('Conversation turn not found')
            detail = json.loads(row['detail_json'])
            refs = json.loads(row['refs_json'])
            cards = [{**card, 'ordinal': index-offset+1} for index, ref in enumerate(refs) if offset <= index < offset+limit and (card := self._card(con, ref))]
            total = len(refs)
            kind = row['response_kind']
            options = detail.get('options', [])
            if kind == 'clarify' and options:
                current_names = {normalize(g['name']): g['name'] for g in self.groups()}
                current_names.update({normalize(r[0].replace('\\', '/').split('/')[-1]): r[0].replace('\\', '/').split('/')[-1] for r in con.execute("SELECT path FROM roots WHERE state IN ('active','paused')")})
                options = [current_names[normalize(option)] for option in options if normalize(option) in current_names]
                if not options: kind = 'unavailable'
            if kind == 'found' and not cards: kind = 'unavailable'
            reply = detail.get('clarification') if kind == 'clarify' else 'Those files are no longer available in your approved library. Try a fresh search.' if kind == 'unavailable' else 'I couldn’t find a matching accessible file in the selected folders.' if not cards else f"{'Here are likely matches' if all(c['likely'] for c in cards) else 'I found matching files'} in your approved library ({total})."
            # Never return cached document text, paths or model context directly from a job record.
            return {'id': row['id'], 'conversation_id': row['conversation_id'], 'created_at': row['created_at'], 'message': row['message'], 'reply': reply, 'kind': kind, 'mode': detail['mode'], 'options': options if kind == 'clarify' else [], 'corrections': detail.get('corrections', []) if cards else [], 'expansion': detail.get('expansion') if cards else None, 'items': cards, 'total': total, 'offset': offset, 'has_more': offset+limit < total}

    def history(self, conversation):
        uuid.UUID(conversation)
        with self.db.connect() as con:
            ids = [r[0] for r in con.execute('SELECT id FROM discovery_turns WHERE conversation_id=? ORDER BY created_at DESC LIMIT 50', (conversation,))]
        return [self.turn(turn_id) for turn_id in reversed(ids)]

    def citation(self, turn_id, file_id):
        with self.db.connect() as con:
            row = con.execute('SELECT refs_json FROM discovery_turns WHERE id=?', (turn_id,)).fetchone()
            if not row: raise KeyError('Citation not found')
            for ref in json.loads(row[0]):
                if ref['file_id'] == file_id and (card := self._card(con, ref)): return card
        raise PermissionError('This citation is no longer accessible or its document has changed')
