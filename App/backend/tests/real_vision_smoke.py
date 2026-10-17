"""Exercise actual frozen OCR on a mixed syllabus and scanned library PDF."""
import hashlib,json,tempfile,threading,textwrap,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from pypdf import PdfWriter
from sift_indexer.db import Database
from sift_indexer.indexer import Indexer
from sift_indexer.intelligence import Intelligence
from sift_indexer.study_collections import StudyCollections
from test_indexer import run_scan
from test_intelligence import pdf


def main():
    repo=Path(__file__).parents[2]
    with tempfile.TemporaryDirectory(prefix='sift-real-vision-') as temporary:
        base=Path(temporary);library=base/'notes';library.mkdir()
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32)
        def image(text,path):
            picture=Image.new('RGB',(1500,800),'white');ImageDraw.Draw(picture).multiline_text((60,60),text,font=font,fill='black',spacing=18);picture.save(path)
        digital=base/'digital.pdf';pdf(digital,['Subject: Computer Architecture','Unit 1 - Fundamentals','Von Neumann Architecture; Number Systems'])
        scanned=base/'scan.pdf';image('Unit 2 - Processing\nInstruction Cycle; Memory Hierarchy',base/'syllabus.png');Image.open(base/'syllabus.png').save(scanned)
        mixed=base/'syllabus.pdf';writer=PdfWriter();writer.append(digital);writer.append(scanned);writer.write(mixed)
        explanation='Von Neumann Architecture uses one shared memory for instructions and data. The processor communicates with memory through a shared bus. Instruction Cycle explains the fetch decode execute sequence. Registers hold temporary values and the control unit coordinates each operation as a program runs through the processor.'
        image('\n'.join(textwrap.wrap(explanation,70)),base/'notes.png');Image.open(base/'notes.png').save(library/'full notes.pdf')
        originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [mixed,library/'full notes.pdf']}
        db=Database(base/'index.sqlite');indexer=Indexer(db);intelligence=Intelligence(db);collections=StudyCollections(db,intelligence)
        try:
            collections.set_pack(str(repo/'tmp/ocr-pack'))
            root=indexer.add_root(str(library));run_scan(indexer,root['id'])
            with db.connect() as con:file_id=con.execute('SELECT id FROM files').fetchone()[0]
            intelligence._build_file(file_id,False,threading.Event())
            attached=collections.attachment(str(mixed));request=collections.create(attachment_id=attached['id'])
            start=time.perf_counter();collections._organize(request['id'],request['job'],threading.Event());elapsed=time.perf_counter()-start
            detail=collections.detail(request['id']);assert len(detail['outline']['units'])==2,detail
            assert detail['outline']['units'][0]['name'].startswith('Unit 1')
            assert detail['outline']['units'][1]['name'].startswith('Unit 2')
            assert detail['topics_with_material']>=1,detail
            assert any(e['origin']=='OCR transcription' for item in detail['items'] for e in item['evidence'])
            with db.connect() as con:pages=con.execute('SELECT COUNT(*) FROM visual_pages').fetchone()[0]
            assert pages==3
            # Cache reuse must not call the image worker a second time.
            import sift_indexer.study_collections as module
            original=module.inspect_page;module.inspect_page=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Unexpected re-extraction'))
            try:collections._organize(request['id'],request['job'],threading.Event())
            finally:module.inspect_page=original
            assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in originals.items())
            result={'real_engine':'frozen PaddleOCR3.2.0 PP-OCRv5 mobile CPU','mixed_pdf_units':2,'cached_pages':pages,'topics_with_material':detail['topics_with_material'],'seconds':round(elapsed,2),'originals_preserved':True,'vision_model_exercised':False}
            print(json.dumps(result))
        finally:indexer.close()


if __name__=='__main__':main()
