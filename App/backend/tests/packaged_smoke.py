"""Exercise the frozen service in a temporary library, with no user data."""
import json
import hashlib
import os
import queue
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from docx import Document
from pypdf import PdfWriter


def main():
    binary = Path(__file__).resolve().parents[1] / 'dist' / 'sift-indexer.exe'
    assert binary.is_file(), 'Build the service before running this check'
    secret = secrets.token_hex(32)
    process = None
    with tempfile.TemporaryDirectory(prefix='sift-packaged-') as temporary:
        base = Path(temporary)
        library = base / 'library'
        library.mkdir()
        text_file = library / 'notes.txt'
        text_file.write_text('benchmarkneedle original notes', encoding='utf-8')
        word = Document()
        word.add_paragraph('benchmarkneedle word document')
        word.save(library / 'lesson.docx')
        pdf = PdfWriter()
        pdf.add_blank_page(width=200, height=200)
        with (library / 'scan.pdf').open('wb') as stream:
            pdf.write(stream)
        originals = {path: path.read_bytes() for path in library.iterdir()}

        def stop():
            nonlocal process
            if process and process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/pid', str(process.pid), '/t', '/f'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process.terminate()
                process.wait(timeout=10)
            if process:
                process.stdout.close()
                process.stderr.close()
            process = None

        def start():
            nonlocal process
            environment = {**os.environ, 'SIFT_SERVICE_TOKEN': secret, 'SIFT_DB_PATH': str(base / 'index.sqlite')}
            process = subprocess.Popen([str(binary)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            lines = queue.Queue()
            threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            ready = json.loads(lines.get(timeout=25))
            assert ready['sift_ready']
            return f'http://127.0.0.1:{ready["port"]}'

        def request(method, route, payload=None, auth=True):
            body = json.dumps(payload).encode() if payload is not None else None
            headers = {'Content-Type': 'application/json'}
            if auth:
                headers['X-SIFT-Token'] = secret
            with urllib.request.urlopen(urllib.request.Request(address + route, data=body, headers=headers, method=method), timeout=10) as response:
                return json.load(response)

        def scan(root_id):
            job_id = request('POST', '/scans', {'root_id': root_id})['id']
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                job = request('GET', f'/jobs/{job_id}')
                if job['state'] in {'done', 'failed', 'cancelled'}:
                    assert job['state'] == 'done', job
                    return
                time.sleep(.05)
            raise AssertionError(f'Packaged scan deadline exceeded: {job!r}')

        try:
            address = start()
            health = request('GET', '/health')
            assert health['schema_version'] == 5
            try:
                request('GET', '/health', auth=False)
                raise AssertionError('Unauthenticated service request succeeded')
            except urllib.error.HTTPError as error:
                assert error.code == 401
            root = request('POST', '/folders', {'path': str(library)})
            scan(root['id'])
            assert request('GET', '/documents')['total'] == 3
            indexed_pdf=next(item for item in request('GET','/documents')['items'] if item['extension']=='.pdf')
            assert request('POST', '/search', {'query': 'benchmarkneedle'})['total'] == 2
            assert all(path.read_bytes() == content for path, content in originals.items())
            text_file.write_text('replacementonly current notes', encoding='utf-8')
            scan(root['id'])
            matched = request('POST', '/search', {'query': 'replacementonly'})
            assert matched['total'] == 1
            detail = request('GET', f'/documents/{matched["items"][0]["id"]}')
            assert [block['text'] for block in detail['blocks']] == ['replacementonly current notes']
            assert request('POST', '/search', {'query': 'benchmarkneedle'})['total'] == 1
            stop()
            address = start()
            assert request('GET', '/documents')['total'] == 3
            assert request('POST', '/search', {'query': 'replacementonly'})['total'] == 1
            assert all(path == text_file or path.read_bytes() == content for path, content in originals.items())
            rebuild = request('POST', '/intelligence/rebuild')['id']
            deadline=time.monotonic()+10.0
            while time.monotonic()<deadline:
                work = request('GET', f'/intelligence/jobs/{rebuild}')
                if work['state'] in ('done', 'failed', 'cancelled'): break
                time.sleep(.05)
            assert work['state'] == 'done', work
            assert request('GET', '/intelligence/status')['mode'] == 'keyword'
            job = request('POST', '/intelligence/chat', {'message': 'Find replacementonly'})
            deadline=time.monotonic()+10.0
            while time.monotonic()<deadline:
                work = request('GET', f'/intelligence/jobs/{job["id"]}')
                if work['state'] in ('done', 'failed', 'cancelled'): break
                time.sleep(.05)
            assert work['state'] == 'done' and work['result']['total'] == 1, work
            turn = work['result']
            assert 'replacementonly' in turn['items'][0]['excerpt']
            # Exercise citation continuity through the actual frozen-service boundary.
            reference=f'/intelligence/turns/{turn["id"]}/files/{turn["items"][0]["id"]}'
            digest=hashlib.sha256(text_file.read_bytes()).hexdigest()
            renamed=text_file.with_name('renamed-notes.txt')
            text_file.rename(renamed)
            try:
                # A watcher may reconcile before this request; never accept the old path.
                assert request('GET',reference)['path']==str(renamed)
            except urllib.error.HTTPError as error: assert error.code==403
            scan(root['id'])
            rebuild=request('POST','/intelligence/rebuild')['id']
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                work=request('GET',f'/intelligence/jobs/{rebuild}')
                if work['state'] in ('done','failed','cancelled'):break
                time.sleep(.05)
            assert work['state']=='done',work
            assert request('GET',reference)['path']==str(renamed)
            assert hashlib.sha256(renamed.read_bytes()).hexdigest()==digest
            assert request('GET', '/intelligence/groups')
            collection=request('POST','/collections',{'text':'Subject: Offline course\nUnit 1 - Notes\nreplacementonly'})
            deadline=time.monotonic()+20.0
            while time.monotonic()<deadline:
                work=request('GET',f'/collections/jobs/{collection["job"]}')
                if work['state'] in ('done','failed','cancelled'):break
                time.sleep(.05)
            assert work['state']=='done',work
            organized=request('GET',f'/collections/{collection["id"]}')
            assert organized['total']==1 and organized['outline']['units'][0]['name']=='Unit 1 - Notes'
            from PIL import Image
            image=base/'syllabus.pdf';Image.new('RGB',(240,160),'white').save(image)
            attached=request('POST','/collections/attachments',{'path':str(image)})
            scanned=request('POST','/collections',{'attachment_id':attached['id']})
            deadline=time.monotonic()+40.0
            while time.monotonic()<deadline:
                work=request('GET',f'/collections/jobs/{scanned["job"]}')
                if work['state'] in ('done','failed','cancelled'):break
                time.sleep(.05)
            assert work['state']=='done',work
            assert request('GET',f'/collections/{scanned["id"]}')['issues']
            source=request('GET','/collections/reference/attachment:'+attached['id'])
            assert request('GET',f'/collections/page/attachment:{attached["id"]}/{source["content_hash"]}/1')['image'].startswith('data:image/jpeg')
            request('PATCH', f'/folders/{root["id"]}', {'state': 'removed'})
            assert request('GET', f'/intelligence/turns/{turn["id"]}')['items'] == []
            assert request('GET',f'/collections/{collection["id"]}')['items']==[]
            request('DELETE',f'/collections/attachments/{attached["id"]}')
            for route in [f'/documents/{turn["items"][0]["id"]}/access',
                          f'/intelligence/turns/{turn["id"]}/files/{turn["items"][0]["id"]}',
                          f'/collections/page/file:{indexed_pdf["id"]}/{indexed_pdf["content_hash"]}/1',
                          f'/collections/page/attachment:{attached["id"]}/{source["content_hash"]}/1']:
                try:
                    request('GET',route)
                    raise AssertionError('Revoked evidence remained accessible: '+route)
                except urllib.error.HTTPError as error: assert error.code==403,(route,error.code)

            print(json.dumps({'packaged_service': 'passed', 'schema_version': health['schema_version'], 'formats': ['PDF', 'DOCX', 'TXT'], 'checks': ['token authentication', 'indexing', 'search', 'edited document replacement', 'restart persistence', 'original file preservation', 'offline discovery', 'rename citation continuity', 'automatic grouping', 'revoked chat citations','syllabus organization','frozen PDFium page rendering','missing OCR fallback','revoked collection evidence']}))
        finally:
            stop()


if __name__ == '__main__':
    main()
