"""Intended 0.3.1 behavior, isolated files and no model downloads."""
import json
import threading
import time
import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from test_intelligence import library, ask, wait_job, TOKEN, pdf
from test_collections import setup_library, organize, EXPLANATION
from sift_indexer.discovery_language import interpret
from sift_indexer import document_vision as vision
from sift_indexer import study_collections as collections_module
from sift_indexer.syllabus_matching import match_topics


def test_negative_formats_and_ordinal_identity(library):
    client, app, root, root_id = library
    first = ask(client, 'Find Von Neumann architecture')
    second = ask(client, 'the second one', first['conversation_id'])
    assert [item['id'] for item in second['items']] == [first['items'][1]['id']]
    assert all(item['extension'] != '.pdf' for item in ask(client, 'Find Von Neumann architecture but not PDFs')['items'])
    assert ask(client, 'Find Von Neumann architecture PDFs only but not PDFs')['kind']=='clarify'
    initial = ask(client, 'Find Von Neumann architecture')
    Path(initial['items'][0]['path']).unlink()
    selected = ask(client, 'the second one', initial['conversation_id'])
    assert [item['id'] for item in selected['items']]==[initial['items'][1]['id']]
    latest = ask(client, 'Find Von Neumann architecture')
    Path(latest['items'][0]['path']).unlink()
    assert ask(client, 'the first one', latest['conversation_id'])['kind']=='clarify'


@pytest.mark.parametrize('message,include,exclude',[
    ('architecture without Word files',[],['.docx']),
    ('architecture PDFs only',['.pdf'],[]),
    ('architecture PDF or TXT but not Word files',['.pdf','.txt'],['.docx']),
    ('architecture without PDF and Word files',[],['.docx','.pdf']),
])
def test_format_rules(message,include,exclude):
    intent,clarification,_=interpret(message,None,[],[],[])
    assert not clarification
    assert intent['included_extensions']==include and intent['excluded_extensions']==exclude
    assert intent['query']=='architecture'


@pytest.mark.parametrize('offset,expected',[(-330,'2026-10-14T18:30:00+00:00'),(420,'2026-10-15T07:00:00+00:00')])
def test_local_calendar_boundaries(offset,expected):
    intent,clarification,_=interpret('architecture modified before 2026-10-15',None,[],[],[],offset)
    assert not clarification and intent['before']==expected
    relative,_,_=interpret('architecture modified today',None,[],[],[],offset,datetime(2026,10,15,12,tzinfo=timezone.utc))
    assert relative['after']==expected
    after,_,_=interpret('architecture modified after 2026-10-14',None,[],[],[],offset)
    assert after['after']==expected
    span,_,_=interpret('architecture from 2026-10-15 through 2026-10-15',None,[],[],[],offset)
    assert span['after']==expected


def test_mixed_native_survives_ocr_failure(tmp_path,monkeypatch):
    source=tmp_path/'mixed.pdf';pdf(source,['Native readable content on this page.'])
    output=tmp_path/'result.json'
    monkeypatch.setattr(vision,'_memory_limit',lambda:None)
    monkeypatch.setattr(vision.subprocess,'run',lambda *a,**k: (_ for _ in ()).throw(TimeoutError('injected OCR timeout')))
    vision._page_worker(str(source),1,'missing-pack',str(output))
    data=json.loads(output.read_text())
    assert 'Native readable' in data['regions'][0]['text']
    assert data['retry_ocr'] and data['thumbnail']


def test_page_failure_continues_retry_and_cancellation(tmp_path,monkeypatch):
    db,indexer,intelligence,collections,root,library_dir=setup_library(tmp_path)
    image=tmp_path/'page.png';Image.new('RGB',(30,30),'white').save(image)
    calls=[]
    monkeypatch.setattr(collections_module,'inspect_source',lambda *a:3)
    def inspect(path,number,*args,**kwargs):
        calls.append(number)
        if number==1 and calls.count(1)==1: raise TimeoutError('first page failed')
        return {'regions':[],'issues':[],'page_count':3,'needs_visual':False,'thumbnail':'AA==','dimensions':[30,30]}
    monkeypatch.setattr(collections_module,'inspect_page',inspect)
    try:
        _,issues=collections._read_pages('test',str(image),'hash',threading.Event(),lambda:True,0)
        assert calls==[1,2,3] and 'Page 1' in issues[0]
        collections._read_pages('test',str(image),'hash',threading.Event(),lambda:True,0)
        assert calls==[1,2,3,1]
        event=threading.Event();event.set()
        with pytest.raises(InterruptedError):collections._read_pages('test',str(image),'hash',event,lambda:True,0)
    finally:indexer.close()


# Tuning examples intentionally differ from the evaluation corpus in maintenance_measurements.py.
@pytest.mark.parametrize('text,strong',[
    (EXPLANATION,True),
    ('Von Neumann Architecture uses one shared memory forinstructions and\ndata. The processor communicates with memory through a shared bus.\nInstruction Cycle explains the fetch decode execute sequence.\nRegisters hold temporary values and the control unit coordinates each\noperation as a program runs through the processor.',True),
    ('Von Neumann Architecture is mentioned here. '+ 'Gardeners cultivate flowers and prepare fertile soil for seasonal planting. '*12,False),
    ('Von Neumann Architecture uses registers. '+ 'Gardeners cultivate flowers and prepare fertile soil for seasonal planting. '*12,False),
    ('Bibliography\nVon Neumann Architecture. Smith, Academic Press, 2020. '+EXPLANATION,False),
    ('Table of contents\n'+EXPLANATION,False),
    ('Von Neumann Architecture\n'*16,False),
    ('Subject: Landscape Architecture\n'+EXPLANATION,False),
])
def test_contextual_topic_assignments(tmp_path,text,strong):
    db,indexer,intelligence,collections,root,library_dir=setup_library(tmp_path)
    try:
        source=library_dir/'notes0.txt';source.write_text(text)
        from test_indexer import run_scan
        run_scan(indexer,root['id'])
        intelligence._build_file(1,False,threading.Event())
        detail=organize(collections)
        assert any(i['classification']=='substantive' for i in detail['items'])==strong
    finally:indexer.close()


def test_real_pdf_page_count(tmp_path):
    source=tmp_path/'count.pdf';pdf(source,['Readable page'])
    assert vision.inspect_source(source,lambda:False)==1


def test_ordinal_page_slots_and_revocation(library):
    client,app,root,root_id=library
    for index in range(14):(root/f'extra-{index}.txt').write_text('Von Neumann architecture uses shared instruction and data memory. '+str(index))
    from test_indexer import run_scan
    run_scan(app.state.indexer,root_id)
    wait_job(client,client.post('/intelligence/rebuild',headers=TOKEN).json()['id'])
    first=ask(client,'Find Von Neumann architecture')
    page=client.get(f"/intelligence/turns/{first['id']}?offset=10",headers=TOKEN).json()
    expected=page['items'][1]['id']
    Path(page['items'][0]['path']).unlink()
    updated=client.get(f"/intelligence/turns/{first['id']}?offset=10",headers=TOKEN).json()
    assert updated['items'][0]['ordinal']==2 and updated['items'][0]['id']==expected
    job=client.post('/intelligence/chat',headers=TOKEN,json={'message':'the second one','conversation_id':first['conversation_id'],'result_context':{'turn_id':first['id'],'offset':10}}).json()
    assert wait_job(client,job['id'])['result']['items'][0]['id']==expected
    client.patch(f'/folders/{root_id}',headers=TOKEN,json={'state':'removed'})
    assert ask(client,'the first one',first['conversation_id'])['kind']=='clarify'


def test_filters_apply_to_hybrid_and_model_fallback(library):
    from test_intelligence import FakeModels
    client,app,root,root_id=library
    models=FakeModels();app.state.intelligence.models=models
    wait_job(client,app.state.intelligence.configure(True)['job']['id'])
    models.interpret=lambda *a:'Von Neumann architecture PDF'
    result=ask(client,'Find imaginaryplaceholder but not PDFs')
    assert result['items'] and all(item['extension']!='.pdf' for item in result['items'])


def test_ocr_stage_retry_and_vision_only_retry(tmp_path,monkeypatch):
    db,indexer,intelligence,collections,root,library_dir=setup_library(tmp_path)
    image=tmp_path/'page.png';Image.new('RGB',(20,20),'white').save(image)
    calls=[]
    monkeypatch.setattr(collections_module,'inspect_source',lambda *a:1)
    def inspect(*args,**kwargs):
        calls.append(kwargs.get('resume'))
        return {'regions':[{'id':'native','text':'Readable native text','kind':'transcription','engine':'pdfium-4.30.0'}],'issues':['OCR failed'] if len(calls)==1 else [],'retry_ocr':len(calls)==1,'page_count':1,'needs_visual':False,'thumbnail':'AA==','dimensions':[20,20]}
    monkeypatch.setattr(collections_module,'inspect_page',inspect)
    try:
        for _ in range(3):collections._read_pages('test',str(image),'hash',threading.Event(),lambda:True,0)
        assert len(calls)==2 and calls[1]['regions'][0]['text']=='Readable native text'
        class Models:
            count=0
            def status(self):return {'ready':{'vision':True}}
            def describe(self,*args):
                self.count+=1
                if self.count==1:raise TimeoutError('vision unavailable')
                return 'Generated diagram description'
        intelligence.models=Models();monkeypatch.setattr(intelligence,'enabled',lambda:True)
        monkeypatch.setattr(collections_module,'inspect_page',lambda *a,**k:{'regions':[],'issues':['Sparse image'],'page_count':1,'needs_visual':True,'thumbnail':'AA==','dimensions':[20,20]})
        collections._read_pages('vision',str(image),'hash',threading.Event(),lambda:True,0)
        monkeypatch.setattr(collections_module,'inspect_page',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Repeated successful OCR')))
        regions,issues=collections._read_pages('vision',str(image),'hash',threading.Event(),lambda:True,0)
        assert regions[0]['kind']=='description' and not any('unavailable' in i for i in issues)
    finally:indexer.close()


@pytest.mark.parametrize('kind,uncertain',[('transcription',True),('description',False)])
def test_uncertain_visual_evidence_requires_review(tmp_path,kind,uncertain):
    db,indexer,intelligence,collections,root,library_dir=setup_library(tmp_path)
    try:
        with db.connect() as con:
            version=con.execute('SELECT content_hash FROM files WHERE id=1').fetchone()[0]
            con.execute("UPDATE chunks SET region_id='visual' WHERE file_id=1")
            con.execute('INSERT INTO visual_pages VALUES(?,?,?,?,?,?,?,?)',('file:1',version,1,'test','ready',json.dumps({'regions':[{'id':'visual','kind':kind,'text':EXPLANATION,'uncertain':uncertain,'confidence':.99}]}),b'','[]'))
        detail=organize(collections)
        assert detail['items'] and all(i['classification']=='review' for i in detail['items'])
    finally:indexer.close()


def test_schema_five_manual_approve_reject_move_and_outline_survive_restart(tmp_path):
    from sift_indexer.db import Database
    from sift_indexer.study_collections import StudyCollections
    from sift_indexer.intelligence import Intelligence
    db,indexer,intelligence,collections,root,library_dir=setup_library(tmp_path,3)
    try:
        detail=organize(collections);items=detail['items'];topic=items[0]['topic_id'];target=detail['coverage'][1]['id']
        collections.decide(detail['id'],topic,items[0]['file_id'],'approved')
        collections.decide(detail['id'],topic,items[1]['file_id'],'rejected')
        collections.decide(detail['id'],topic,items[2]['file_id'],'approved',target)
        outline=detail['outline'];outline['subject']='User edited course'
        job=collections.outline(detail['id'],outline)['job']
        with db.connect() as con:
            before=[tuple(r) for r in con.execute("SELECT topic_id,file_id,decision FROM topic_assignments WHERE decision!='auto' ORDER BY topic_id,file_id")]
            assert con.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]==5
        reopened=Database(tmp_path/'index.sqlite');service=StudyCollections(reopened,Intelligence(reopened))
        service._organize(detail['id'],job,threading.Event())
        with reopened.connect() as con:
            assert [tuple(r) for r in con.execute("SELECT topic_id,file_id,decision FROM topic_assignments WHERE decision!='auto' ORDER BY topic_id,file_id")]==before
        assert service.detail(detail['id'])['outline']['subject']=='User edited course'
    finally:indexer.close()


@pytest.mark.parametrize('offset',[-330,420])
def test_midnight_files_use_exclusive_end_inclusive_start(library,offset):
    from datetime import timedelta
    client,app,root,root_id=library
    boundary=datetime(2026,10,15,tzinfo=timezone.utc)+timedelta(minutes=offset)
    with app.state.indexer.db.connect() as con:
        files=[r[0] for r in con.execute("SELECT id FROM files WHERE filename IN ('full notes.pdf','week-02.txt') ORDER BY id")]
        for file,delta in zip(files,[-1,0]):con.execute('UPDATE files SET discovered_at=? WHERE id=?',((boundary+timedelta(microseconds=delta)).isoformat(),file))
    for message,expected in [('Von Neumann architecture added before 2026-10-15',files[0]),('Von Neumann architecture added after 2026-10-14',files[1])]:
        job=client.post('/intelligence/chat',headers=TOKEN,json={'message':message,'timezone_offset':offset}).json()
        assert [i['id'] for i in wait_job(client,job['id'])['result']['items']]==[expected]


def test_ambiguous_ordinal_asks_and_late_content_change_cannot_shift_selection(library,monkeypatch):
    client,app,root,root_id=library
    first=ask(client,'Find Von Neumann architecture')
    assert ask(client,'the first or second one',first['conversation_id'])['kind']=='clarify'
    fresh=ask(client,'Find Von Neumann architecture')
    retrieve=app.state.intelligence.retrieve
    def change_after_resolution(intent,*args):
        if intent.get('only_id'):
            Path(fresh['items'][1]['path']).write_text('Changed while resolving selection')
        return retrieve(intent,*args)
    monkeypatch.setattr(app.state.intelligence,'retrieve',change_after_resolution)
    assert ask(client,'the second one',fresh['conversation_id'])['kind']=='clarify'
