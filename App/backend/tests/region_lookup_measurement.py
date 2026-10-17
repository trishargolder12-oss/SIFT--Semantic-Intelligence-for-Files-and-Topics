"""Compare original repeated lookup and scoped region map on identical visual fixtures."""
import inspect
import json
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from test_collections import setup_library, EXPLANATION
from sift_indexer.syllabus import extract_outline
from sift_indexer import syllabus_matching as matcher


def main():
    with tempfile.TemporaryDirectory(prefix='sift-region-profile-') as temporary:
        db,indexer,intelligence,collections,root,library=setup_library(Path(temporary),12)
        try:
            with db.connect() as con:
                for file in con.execute('SELECT id,content_hash FROM files').fetchall():
                    regions=[{'id':f'r-{i}','kind':'transcription','text':EXPLANATION,'uncertain':False,'confidence':.98} for i in range(100)]
                    con.execute('INSERT INTO visual_pages VALUES(?,?,?,?,?,?,?,?)',('file:'+str(file['id']),file['content_hash'],1,'profile','ready',json.dumps({'regions':regions}),b'','[]'))
                    con.execute("UPDATE chunks SET region_id='r-99' WHERE file_id=?",(file['id'],))
            outline=extract_outline(str(uuid.uuid4()),[{'text':'Subject: Computer Architecture\nUnit 1 - Foundations\nVon Neumann Architecture; Stored Program; Instruction Cycle','engine':'pasted-text'}])
            # Reproduce the pre-change loop in memory, using this exact module and corpus.
            source=inspect.getsource(matcher.match_topics)
            first=source.index('                        key=(file_id,')
            last=source.index('                        if not region: continue',first)
            original=source[:first]+'''                        for page in con.execute('SELECT regions_json FROM visual_pages WHERE source_key=? AND content_hash=?',('file:'+str(file_id),file['content_hash'])):
                            for candidate in json.loads(page[0]).get('regions',[]):
                                if candidate['id']==chunk['region_id']: region=candidate; break
'''+source[last:]
            namespace=dict(vars(matcher));exec(original,namespace)
            connect=db.connect;counts={};results={}
            @contextmanager
            def traced():
                with connect() as con:
                    con.set_trace_callback(lambda sql:counts.__setitem__('queries',counts.get('queries',0)+int(sql.startswith('SELECT regions_json FROM visual_pages'))))
                    yield con
            db.connect=traced
            for name,function in [('original_lookup',namespace['match_topics']),('scoped_region_map',matcher.match_topics)]:
                counts.clear();began=time.perf_counter();items=function(db,intelligence,outline,'not-syllabus',threading.Event(),lambda *a:None)
                results[name]={'seconds':round(time.perf_counter()-began,4),'region_queries':counts.get('queries',0),'assignments':len(items)}
            assert results['original_lookup']['assignments']==results['scoped_region_map']['assignments']
            print(json.dumps({'dataset':'12 synthetic files, 100 visual regions each, three topics; current evidence permissions checked per topic','comparison':results}))
        finally:indexer.close()


if __name__=='__main__':main()
