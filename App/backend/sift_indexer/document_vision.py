"""Page-bounded local extraction. Native text, OCR, and descriptions stay distinct."""
import base64
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

CONFIG = 'pdfium4.30-pillow11.3-ppocr5-mobile-v2'
MAX_PAGES = 200
MAX_BYTES = 64 * 1024 * 1024


def pack_info(directory):
    root = Path(directory)
    manifest = json.loads((root / 'pack.json').read_text())
    if manifest.get('engine') != 'paddleocr-3.2.0+paddlepaddle-3.2.1': raise ValueError('Unsupported OCR pack')
    for relative, digest in manifest['files'].items():
        path = root / relative
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        if path.is_symlink() or path.is_junction(): raise ValueError('Linked OCR assets are not allowed')
        with path.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != digest: raise ValueError('OCR pack checksum mismatch')
    if 'sift-ocr/sift-ocr.exe' not in manifest['files']: raise ValueError('Missing OCR runtime')
    return manifest


def _memory_limit():
    # This worker and its OCR descendants share a 1.5 GB Windows job limit.
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024**2, 1536 * 1024**2))
        return
    import ctypes
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
                    ('ActiveProcessLimit', w.DWORD), ('Affinity', ctypes.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
    class Extended(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]; kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.GetCurrentProcess.restype = w.HANDLE
    limits = Extended(); limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x200
    limits.JobMemoryLimit = 1536 * 1024**2
    handle = kernel.CreateJobObjectW(None, None)
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise RuntimeError('Could not establish the visual worker memory boundary')
    # Keep the handle open until process exit; terminating this worker kills its children.


def _page_worker(path, page_number, ocr_pack, output, resume=None):
    document=page=text_page=None
    try:
        _memory_limit()
        from PIL import Image, ImageOps, ImageStat
        Image.MAX_IMAGE_PIXELS = 20_000_000
        native, page_count, image_content = '', 1, True
        if Path(path).suffix.lower() == '.pdf':
            import pypdfium2 as pdfium
            document = pdfium.PdfDocument(path)
            page_count = len(document)
            page = document[page_number-1]
            text_page = page.get_textpage()
            native = next((r['text'] for r in (resume or {}).get('regions',[]) if r['engine']=='pdfium-4.30.0'), '')
            if not native: native = text_page.get_text_range().replace('\r\n', '\n')[:100000]
            image_content = any(obj.type in (2,3) for obj in page.get_objects())
            scale = min(2.0, 2000 / max(page.get_size()))
            image = page.render(scale=scale).to_pil().convert('RGB')
        else:
            image = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
            image.thumbnail((2000, 2000))
        width, height = image.size
        preview = image.copy(); preview.thumbnail((850, 1100))
        stream = io.BytesIO(); preview.save(stream, format='JPEG', quality=75)
        regions, issues = [], []
        if native.strip(): regions.append({'text': native, 'kind': 'transcription', 'engine': 'pdfium-4.30.0', 'confidence': None, 'bbox': None, 'uncertain': False})
        needs_ocr = len(native.strip()) < 60 or image_content
        if needs_ocr and ocr_pack:
            try:
                with tempfile.TemporaryDirectory(prefix='sift-page-') as temporary:
                    png, result = Path(temporary)/'page.png', Path(temporary)/'result.json'
                    ImageOps.autocontrast(image).save(png)
                    command = Path(ocr_pack)/'sift-ocr/sift-ocr.exe'
                    subprocess.run([str(command), str(png), str(Path(ocr_pack)/'models'), str(result)], check=True, timeout=70,
                                   creationflags=0x08000000 if os.name=='nt' else 0, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    recognized = json.loads(result.read_text(encoding='utf-8'))
                    for item in recognized:
                        if native and item['text'].strip() in native: continue
                        item.update(kind='transcription', engine='PP-OCRv5-mobile@paddleocr3.2.0', uncertain=item['confidence'] < .85)
                        regions.append(item)
            except Exception as exc:
                issues.append(f'OCR failed ({type(exc).__name__}); native text retained. Refresh to retry OCR.')
        elif needs_ocr:
            issues.append('Image regions need the optional OCR pack; native text was retained.')
        contrast = ImageStat.Stat(image.convert('L')).stddev[0]
        if contrast < 18: issues.append('Low contrast image; check the page manually.')
        if not any(r['text'].strip() for r in regions): issues.append('No readable text; this page needs review.')
        for index, region in enumerate(regions):
            region.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'{path}:{page_number}:{index}:{region["text"]}')), page=page_number,
                          region_type='text', quality={'contrast_stddev': round(contrast, 2)}, model_version=CONFIG)
            if any(symbol in region['text'] for symbol in ['=','∫','∑','±','√']):
                region['region_type']='possible formula';region['uncertain']=True
                issues.append('Formula transcription is unverified; inspect symbols on the source page.')
        ocr=[region for region in regions if region['engine'].startswith('PP-OCR')]
        if ocr:
            boxes=[r['bbox'] for r in ocr]
            regions.append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,f'{path}:{page_number}:ocr-page')), 'page':page_number,
                'text':'\n'.join(r['text'] for r in ocr),'kind':'transcription','engine':'PP-OCRv5-mobile@paddleocr3.2.0',
                'confidence':min(r['confidence'] for r in ocr),'uncertain':any(r['uncertain'] for r in ocr),
                'bbox':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)],
                'region_type':'reading-order text','model_version':CONFIG,'index_only':True,'quality':{'layout':'top-to-bottom OCR lines; complex columns need review'}})
        if needs_ocr and sum(len(r['text'].split()) for r in regions if not r.get('index_only'))<24 and contrast>18:
            issues.append('Sparse labels or a visual region may need diagram interpretation; connections have not been inferred from OCR.')
        # A successful generated stage is reusable while retrying OCR; it stays labeled.
        regions.extend(r for r in (resume or {}).get('regions',[]) if r['kind']=='description')
        payload = {'regions': regions, 'issues': issues, 'thumbnail': base64.b64encode(stream.getvalue()).decode(),
                   'page_count': page_count, 'needs_visual': needs_ocr, 'dimensions': [width,height], 'retry_ocr': any(i.startswith('OCR failed') for i in issues)}
        Path(output).write_text(json.dumps(payload), encoding='utf-8')
    except Exception as exc:
        Path(output).write_text(json.dumps({'error': f'{type(exc).__name__}: {exc}'}), encoding='utf-8')
    finally:
        for resource in (text_page,page,document):
            if resource is not None: resource.close()


def _count_worker(path, output):
    try:
        _memory_limit()
        if Path(path).suffix.lower()=='.pdf':
            import pypdfium2 as pdfium
            document=pdfium.PdfDocument(path)
            try: count=len(document)
            finally: document.close()
        else:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS=20_000_000
            with Image.open(path) as image: image.verify()
            count=1
        if count<1: raise ValueError('Empty source')
        Path(output).write_text(json.dumps({'page_count':count}),encoding='utf-8')
    except Exception as exc:
        Path(output).write_text(json.dumps({'error':f'Invalid source: {type(exc).__name__}: {exc}'}),encoding='utf-8')


def inspect_source(path, should_stop):
    return _inspect(path, should_stop, 15, _count_worker, ())['page_count']


def inspect_page(path, page, ocr_pack, should_stop, timeout=90, resume=None):
    if not 1<=page<=MAX_PAGES: raise ValueError('Page exceeds analysis limit')
    return _inspect(path, should_stop, timeout, _page_worker, (page,ocr_pack), resume)


def _inspect(path, should_stop, timeout, target, arguments, resume=None):
    if Path(path).stat().st_size > MAX_BYTES: raise ValueError('Visual documents are limited to 64 MB')
    with tempfile.TemporaryDirectory(prefix='sift-vision-') as temporary:
        output = Path(temporary)/'page.json'
        args=(str(path),*arguments,str(output)) + ((resume,) if target is _page_worker else ())
        process = multiprocessing.get_context('spawn').Process(target=target, args=args)
        process.start(); deadline = time.monotonic() + timeout
        try:
            while process.is_alive():
                if should_stop(): raise InterruptedError('Page analysis cancelled or access changed')
                if time.monotonic() > deadline: raise TimeoutError(f'Visual analysis exceeded {timeout} seconds')
                process.join(.05)
            if should_stop(): raise InterruptedError('Cancelled')
            if not output.exists(): raise ValueError('Visual worker stopped before publishing a page')
            data = json.loads(output.read_text(encoding='utf-8'))
            if data.get('error'): raise ValueError(data['error'])
            return data
        finally:
            if process.is_alive(): process.terminate(); process.join(3)
            if process.is_alive(): process.kill(); process.join(2)
            process.close()
