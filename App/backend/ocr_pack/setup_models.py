"""Explicit development/setup download. Never called during document processing."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import urllib.request

root=Path(sys.argv[1]).resolve(); root.mkdir(parents=True,exist_ok=True)
pins={'PP-OCRv5_mobile_det':'50446e5d01ac2a73d5319c89513281f6578414c888c602f9af13f93feefffc58',
      'PP-OCRv5_mobile_rec':'566b9512b34e34a9f0db54d87b51fa5a0b9ed2cf1ab7e49728cc0b8b5a64f414'}
for name in ['PP-OCRv5_mobile_det','PP-OCRv5_mobile_rec']:
    destination=root/name
    if destination.is_dir(): continue
    url=f'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/{name}_infer.tar'
    archive=root/(name+'.tar')
    urllib.request.urlretrieve(url,archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=pins[name]: raise ValueError('OCR model artifact changed; review before updating the supported version')
    with tarfile.open(archive) as contents:
        contents.extractall(root,filter='data')
    extracted=root/(name+'_infer')
    if extracted.exists(): extracted.rename(destination)
    print(name,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())
