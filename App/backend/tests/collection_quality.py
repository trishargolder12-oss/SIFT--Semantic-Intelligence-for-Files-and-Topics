"""Small labeled matching measurement; synthetic data, no semantic-quality claim."""
import json,tempfile,threading,time,tracemalloc
from pathlib import Path
from sift_indexer.db import Database
from sift_indexer.indexer import Indexer
from sift_indexer.intelligence import Intelligence
from sift_indexer.study_collections import StudyCollections
from test_indexer import run_scan


def main():
    expected={'Von Neumann Architecture','Instruction Cycle'}
    with tempfile.TemporaryDirectory(prefix='sift-match-quality-') as temporary:
        root=Path(temporary);library=root/'library';library.mkdir()
        explanation='Von Neumann Architecture uses a stored program with shared memory for instructions and values. The processor communicates with memory through a common bus and executes stored instructions. Instruction Cycle describes fetching an instruction, decoding the operation and executing it through the processor, updating registers and returning to fetch the next instruction.'
        cases={'full-notes.txt':'Subject: Computer Architecture\n'+explanation,
          'brief.txt':'Von Neumann Architecture is listed here.',
          'contents.txt':'Table of contents\nVon Neumann Architecture .... 2\nInstruction Cycle .... 4',
          'Von Neumann Architecture.txt':'Buildings and landscape design use architectural plans and site surveys. These notes concern building materials and environmental design rather than the operation of computers or processors.',
          'business.txt':'Subject: Business Architecture\n'+explanation,
          'unrelated.txt':'A lesson about plant cells and photosynthesis.'}
        for name,text in cases.items():(library/name).write_text(text)
        db=Database(root/'index.sqlite');indexer=Indexer(db);intelligence=Intelligence(db)
        try:
            folder=indexer.add_root(str(library));run_scan(indexer,folder['id'])
            with db.connect() as con:files=[dict(r) for r in con.execute('SELECT * FROM files')]
            for file in files:intelligence._build_file(file['id'],False,threading.Event())
            collections=StudyCollections(db,intelligence)
            request=collections.create('Subject: Computer Architecture\nUnit 1 - Processor\nVon Neumann Architecture; Instruction Cycle; Cache Coherence')
            tracemalloc.start();start=time.perf_counter();collections._organize(request['id'],request['job'],threading.Event());latency=time.perf_counter()-start
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            detail=collections.detail(request['id'],limit=100)
            names={t['id']:t['name'] for unit in detail['outline']['units'] for t in unit['topics']}
            actual={(item['filename'],names[item['topic_id']]) for item in detail['items'] if item['classification']=='substantive'}
            truth={('full-notes.txt',name) for name in expected}
            result={'dataset':'Six synthetic English TXT documents, three syllabus topics; keyword mode',
                'expected_strong_assignments':len(truth),'actual_strong_assignments':len(actual),
                'false_matches':len(actual-truth),'missed_matches':len(truth-actual),
                'matching_seconds':round(latency,3),'peak_python_heap_mb':round(peak/1024**2,2),'gaps':detail['gaps']}
            assert result['false_matches']==result['missed_matches']==0,result
            (Path(__file__).parents[2]/'docs/MATCHING_QUALITY_MEASUREMENTS.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result))
        finally:indexer.close()


if __name__=='__main__':main()
