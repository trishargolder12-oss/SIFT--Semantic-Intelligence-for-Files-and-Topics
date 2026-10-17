import hashlib,json,sys,zipfile
from pathlib import Path
root,release=map(Path,sys.argv[1:]);release.mkdir(parents=True,exist_ok=True)
files={}
for directory in ['sift-ocr','models']:
    for path in sorted((root/directory).rglob('*')):
        if path.is_file() and path.suffix!='.tar':
            with path.open('rb') as stream: files[path.relative_to(root).as_posix()]=hashlib.file_digest(stream,'sha256').hexdigest()
manifest={'engine':'paddleocr-3.2.0+paddlepaddle-3.2.1','files':files,'unpacked_bytes':sum((root/p).stat().st_size for p in files)}
(root/'pack.json').write_text(json.dumps(manifest,indent=2))
target=release/'SIFT OCR Pack 1.zip'
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
    for relative in [*files,'pack.json']: archive.write(root/relative,relative)
with target.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n')
print(json.dumps({'pack':str(target),'download_bytes':target.stat().st_size,'unpacked_bytes':manifest['unpacked_bytes']}))
