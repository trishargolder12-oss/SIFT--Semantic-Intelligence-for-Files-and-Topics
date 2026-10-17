"""Isolated review benchmark; execute directly, not as a pytest test."""
import json
import tempfile
import time
from pathlib import Path
from fastapi.testclient import TestClient
from sift_indexer.api import create_app
from sift_indexer.db import Database
from sift_indexer.indexer import Indexer

def main():
    with tempfile.TemporaryDirectory(prefix='sift-review-') as temporary:
        base = Path(temporary)
        root = base / 'library'
        root.mkdir()
        for i in range(200):
            (root / f'note-{i:04}.txt').write_text(f'benchmarkneedle document {i}\n' * 200, encoding='utf-8')
        db = Database(base / 'index.sqlite')
        indexer = Indexer(db)
        output = {}
        try:
            root_id = indexer.add_root(str(root))['id']
            for label in ['initial', 'unchanged', 'one_changed']:
                if label == 'one_changed':
                    (root / 'note-0000.txt').write_text('replacementonly', encoding='utf-8')
                start = time.perf_counter()
                job_id = indexer.start_scan(root_id)
                while True:
                    job = indexer.job(job_id)
                    if job['state'] in ('done','failed','cancelled'):
                        break
                    assert time.perf_counter() - start < 120
                    time.sleep(.02)
                assert job['state'] == 'done' and job['failed'] == 0, job
                output[label] = {'seconds': round(time.perf_counter()-start,3), 'processed':job['processed']}
        finally:
            indexer.close()
        app = create_app(base / 'index.sqlite', 'review')
        client = TestClient(app)
        try:
            durations = []
            for _ in range(10):
                start = time.perf_counter()
                response = client.post('/search', headers={'X-SIFT-Token':'review'}, json={'query':'benchmarkneedle'})
                assert response.status_code == 200
                durations.append((time.perf_counter()-start)*1000)
            output['search'] = {'total':response.json()['total'], 'returned':len(response.json()['items']), 'mean_ms':round(sum(durations)/10,2),'max_ms':round(max(durations),2)}
            with db.connect() as connection:
                output['edited_blocks'] = [r[0] for r in connection.execute("SELECT b.text FROM text_blocks b JOIN files f ON f.id=b.file_id WHERE f.filename='note-0000.txt'")]
                output['path_plan'] = [r[3] for r in connection.execute('EXPLAIN QUERY PLAN SELECT * FROM files WHERE path=? COLLATE NOCASE', (str(root / 'note-0000.txt'),))]
            print(json.dumps(output, indent=2))
        finally:
            client.close()
            app.state.indexer.close()
            app.state.intelligence.close()

if __name__ == '__main__':
    main()
