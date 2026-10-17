"""Repeatable isolated refresh/profile and held-out matching evaluation. Prints JSON."""
import cProfile
import ctypes
import hashlib
import json
import os
import platform
import pstats
import tempfile
import threading
import time
import textwrap
import sys
from ctypes import wintypes as w
from pathlib import Path

from sift_indexer.db import Database
from sift_indexer.indexer import Indexer
from sift_indexer.intelligence import Intelligence
from sift_indexer.study_collections import StudyCollections
from test_indexer import run_scan
from test_intelligence import pdf

TOPICS=['Cache Coherence','Virtual Memory','Pipeline Hazards','Branch Prediction','Interrupt Handling','Memory Hierarchy','Bus Arbitration','Address Translation','Instruction Decoding','Register Allocation','Direct Memory Access','Processor Scheduling']
PASSAGE=('Cache Coherence ensures that processors observe consistent values in shared memory. '
         'When a processor writes a cache line, the protocol invalidates other copies so subsequent reads obtain the updated data. '
         'Virtual Memory maps program addresses to physical storage using page tables. '
         'The processor consults these mappings on each access and raises a page fault when a required page is absent.')


def memory():
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong),*[(name,ctypes.c_size_t) for name in ['peak','working','poolpeak','pool','nonpoolpeak','nonpool','pagefile','peakpagefile']]]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=ctypes.c_void_p
    psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb): raise ctypes.WinError()
    return {'working_mib':round(counters.working/1024**2,2),'peak_working_mib':round(counters.peak/1024**2,2)}


def profile_data(profile):
    stats=pstats.Stats(profile)
    return [{'function':f'{Path(key[0]).name}:{key[1]}:{key[2]}','calls':value[1],'cumulative_seconds':round(value[3],4)} for key,value in sorted(stats.stats.items(),key=lambda item:-item[1][3])[:18]]


def processes():
    class Entry(ctypes.Structure):
        _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',ctypes.c_long),('flags',w.DWORD),('exe',w.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype=w.HANDLE
    kernel.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];kernel.Process32NextW.argtypes=kernel.Process32FirstW.argtypes
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.CreateToolhelp32Snapshot(2,0);entry=Entry();entry.size=ctypes.sizeof(entry);result={}
    try:
        more=kernel.Process32FirstW(handle,ctypes.byref(entry))
        while more:
            result[entry.pid]=(entry.parent,entry.exe)
            more=kernel.Process32NextW(handle,ctypes.byref(entry))
    finally:kernel.CloseHandle(handle)
    return result


def cancellation(base,pack):
    from PIL import Image
    from sift_indexer.document_vision import inspect_page
    source=base/'cancel.pdf';Image.new('RGB',(800,800),'white').save(source)
    began=time.perf_counter();cancelled_at=None;seen=set();ocr_seen=False;existing=set(processes())
    def stop():
        nonlocal cancelled_at,ocr_seen
        snapshot=processes();descendants={os.getpid()}
        while True:
            expanded=descendants|{pid for pid,(parent,_) in snapshot.items() if parent in descendants}
            if expanded==descendants:break
            descendants=expanded
        seen.update(descendants-existing-{os.getpid()})
        ocr_seen=ocr_seen or any(snapshot[pid][1].lower()=='sift-ocr.exe' for pid in descendants if pid in snapshot)
        if ocr_seen or time.perf_counter()-began>15:
            cancelled_at=time.perf_counter();return True
        return False
    try:inspect_page(source,1,str(pack),stop)
    except InterruptedError:pass
    else:raise AssertionError('Page completed before cancellation')
    latency=time.perf_counter()-cancelled_at
    deadline=time.monotonic()+3
    while seen & processes().keys() and time.monotonic()<deadline:time.sleep(.05)
    survivors=seen & processes().keys()
    assert ocr_seen and not survivors,(ocr_seen,survivors)
    return {'ocr_child_started':ocr_seen,'worker_and_descendants_observed':len(seen),'cancel_to_return_seconds':round(latency,4),'survivors':list(survivors)}


def main():
    with tempfile.TemporaryDirectory(prefix='sift-maintenance-measure-') as temporary:
        base=Path(temporary);library=base/'library';library.mkdir()
        # Held-out examples differ in topics and text from the rule-tuning tests.
        cases={'full-notes.txt':PASSAGE,
          'passing-mention.txt':'Cache Coherence is a topic for another course. '+'Coastal erosion reshapes beaches as waves transport sand along the shore. '*18,
          'bibliography.txt':'References\nCache Coherence, A. Writer, 2024.\n'+PASSAGE,
          'contents.txt':'Contents\nCache Coherence .... 5\nVirtual Memory .... 7',
          'headings.txt':('Cache Coherence\nVirtual Memory\n'*20),
          'other-subject.txt':'Subject: Business Administration\n'+PASSAGE}
        for name,text in cases.items():(library/name).write_text(text)
        for index in range(66):(library/f'noise-{index}.txt').write_text('Coursework about oceans, climate and ecology. '+ 'Waves carry sediment along coastlines. '*25)
        for index in range(8):pdf(library/f'notes-{index}.pdf',textwrap.wrap(PASSAGE,85))
        originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in library.iterdir()}
        db=Database(base/'index.sqlite');indexer=Indexer(db);intelligence=Intelligence(db);collections=StudyCollections(db,intelligence)
        try:
            pack=Path(__file__).parents[2]/'tmp/ocr-pack'
            if not (pack/'pack.json').exists(): raise RuntimeError('Existing local OCR pack needed for PDF refresh measurement')
            with db.connect() as con:con.execute("UPDATE collection_settings SET value=? WHERE key='ocr_pack'",(str(pack),))
            root=indexer.add_root(str(library));start=time.perf_counter();run_scan(indexer,root['id']);scan=time.perf_counter()-start
            with db.connect() as con:ids=[r[0] for r in con.execute('SELECT id FROM files')]
            for identifier in ids:intelligence._build_file(identifier,False,threading.Event())
            intake=collections.create('Subject: Computer Architecture\nUnit 1 - Core\n'+'; '.join(TOPICS))
            def snapshot():
                with db.connect() as con:
                    return {'documents':{r['file_id']:r['published_at'] for r in con.execute('SELECT * FROM intelligence_documents')},'chunks':[tuple(r) for r in con.execute('SELECT id,file_id,content_hash FROM chunks ORDER BY id')],'pages':con.execute('SELECT COUNT(*) FROM visual_pages').fetchone()[0]}
            results={}
            for stage in (['cold'] if '--quality-only' in sys.argv else ['cold','warm','one_document_update']):
                if stage=='one_document_update':
                    changed=library/'notes-0.pdf';pdf(changed,[PASSAGE+' Updated example.']);originals[changed]=hashlib.sha256(changed.read_bytes()).hexdigest()
                    run_scan(indexer,root['id'])
                    with db.connect() as con:identifier=con.execute('SELECT id FROM files WHERE path=?',(str(changed),)).fetchone()[0]
                    intelligence._build_file(identifier,False,threading.Event())
                before=snapshot();profile=cProfile.Profile();start=time.perf_counter();profile.enable()
                collections._organize(intake['id'],intake['job'],threading.Event())
                profile.disable();elapsed=time.perf_counter()-start;after=snapshot()
                results[stage]={'seconds':round(elapsed,4),**memory(),'issues':collections.detail(intake['id'])['issues'],'pages':after['pages'],'republished_documents':sum(before['documents'].get(k)!=v for k,v in after['documents'].items()),'chunk_ids_preserved':before['chunks']==after['chunks'],'profile':profile_data(profile)}
            detail=collections.detail(intake['id'],limit=10000)
            names={t['id']:t['name'] for u in detail['outline']['units'] for t in u['topics']}
            actual={(i['filename'],names[i['topic_id']]) for i in detail['items'] if i['classification']=='substantive'}
            truth={(name,topic) for name in ['full-notes.txt',*[f'notes-{i}.pdf' for i in range(8)]] for topic in TOPICS[:2]}
            result={'hardware':{'cpu':platform.processor(),'logical_cpus':os.cpu_count(),'platform':platform.platform()},'library_documents':len(ids),'topics':len(TOPICS),'pdf_pages':8,'scan_seconds':round(scan,4),'mode':'keyword/native PDF; existing OCR pack configured; no inference needed','refresh':results,'held_out_quality':{'expected':len(truth),'automatic':len(actual),'false_automatic':len(actual-truth),'missed_relevant':len(truth-actual),'false_pairs':sorted(actual-truth),'missed_pairs':sorted(truth-actual)},'original_hashes_preserved':all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in originals.items()),'model_status':intelligence.models.status()}
            result['cancellation']=cancellation(base,pack)
            print(json.dumps(result))
        finally:indexer.close()


if __name__=='__main__':main()
