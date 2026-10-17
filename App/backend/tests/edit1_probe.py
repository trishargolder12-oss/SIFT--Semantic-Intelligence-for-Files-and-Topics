"""Standalone, isolated review probes; no user library is accessed."""
import json
import gc
import tempfile
import time
from pathlib import Path
from fastapi.testclient import TestClient
from sift_indexer.api import create_app
from sift_indexer.db import Database
from sift_indexer.indexer import Indexer

def scan(indexer, root):
    start = time.perf_counter()
    job_id = indexer.start_scan(root)
    indexer._worker.join(120)
    job = indexer.job(job_id)
    assert job['state'] == 'done', job
    return {'seconds': round(time.perf_counter()-start, 3), **{k: job[k] for k in ('processed','created','changed','unchanged')}}

with tempfile.TemporaryDirectory(prefix='sift-edit1-') as temporary:
    base = Path(temporary)
    root = base / 'library'
    root.mkdir()
    for i in range(200):
        (root / f'note-{i:04}.txt').write_text(f'benchmarkneedle document {i}\n' * 200, encoding='utf-8')
    db = Database(base / 'index.sqlite')
    indexer = Indexer(db)
    root_id = indexer.add_root(str(root))['id']
    output = {'dataset': {'files': 200, 'bytes': sum(p.stat().st_size for p in root.iterdir())}}
    output['initial_scan'] = scan(indexer, root_id)
    output['unchanged_scan'] = scan(indexer, root_id)
    target = root / 'note-0000.txt'
    target.write_text('replacementonly', encoding='utf-8')
    output['changed_scan'] = scan(indexer, root_id)
    with db.connect() as conn:
        file_id = conn.execute('SELECT id FROM files WHERE path=?', (str(target),)).fetchone()[0]
        output['blocks_after_edit'] = [dict(r) for r in conn.execute('SELECT position, substr(text,1,65) AS sample FROM text_blocks WHERE file_id=?', (file_id,))]
    # No lifespan context: watcher is intentionally disabled for deterministic probes.
    client = TestClient(create_app(base / 'index.sqlite', 'probe'))
    headers = {'X-SIFT-Token': 'probe'}
    durations = []
    for _ in range(10):
        start = time.perf_counter()
        response = client.post('/search', headers=headers, json={'query':'benchmarkneedle'})
        assert response.status_code == 200
        durations.append((time.perf_counter()-start)*1000)
    page = response.json()
    output['search'] = {'matching_documents':page['total'], 'returned':len(page['items']), 'has_more':page['has_more'], 'mean_ms':round(sum(durations)/len(durations),2), 'max_ms':round(max(durations),2)}
    with db.connect() as conn:
        output['path_lookup_plan'] = [r[3] for r in conn.execute('EXPLAIN QUERY PLAN SELECT * FROM files WHERE path=? COLLATE NOCASE',(str(target),))]
    print(json.dumps(output, indent=2))
    client.close()
    conn.close()
    del conn
    gc.collect()
