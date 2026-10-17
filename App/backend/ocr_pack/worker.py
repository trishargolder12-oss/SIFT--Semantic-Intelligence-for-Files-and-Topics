"""Optional PP-OCRv5 worker: local models only, with all networking disabled."""
import json
import os
from pathlib import Path
import socket
import sys

os.environ.update(OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                  PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True', PADDLE_PDX_MODEL_SOURCE='BOS')


def deny_network(*args, **kwargs):
    raise OSError('Networking is disabled in the OCR worker')


socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.getaddrinfo = deny_network


def main(image_path, models, output):
    from PIL import Image
    import numpy as np
    from paddleocr import PaddleOCR
    models=Path(models)
    for name in ['PP-OCRv5_mobile_det','PP-OCRv5_mobile_rec']:
        if not (models/name/'inference.yml').is_file(): raise ValueError('Local OCR weights are missing')
    engine=PaddleOCR(text_detection_model_name='PP-OCRv5_mobile_det',text_detection_model_dir=str(models/'PP-OCRv5_mobile_det'),
        text_recognition_model_name='PP-OCRv5_mobile_rec',text_recognition_model_dir=str(models/'PP-OCRv5_mobile_rec'),
        use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False,
        device='cpu',cpu_threads=2,enable_mkldnn=False)
    original=Image.open(image_path).convert('RGB'); best,quality=[],0
    width,height=original.size
    for angle in [0,90,180,270]:
        image=original.rotate(angle,expand=True)
        payload=next(iter(engine.predict(np.asarray(image))))
        values=[]
        for text,confidence,polygon in zip(payload['rec_texts'],payload['rec_scores'],payload['rec_polys']):
            points=[]
            for x,y in polygon:
                x,y=float(x),float(y)
                points.append((width-y,x) if angle==90 else (width-x,height-y) if angle==180 else (y,height-x) if angle==270 else (x,y))
            values.append({'text':text if confidence>=.5 else '[unclear]', 'confidence':float(confidence),
                'bbox':[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)],
                'rotation':angle})
        score=sum(v['confidence']*len(v['text']) for v in values)
        if score>quality: best,quality=values,score
        if angle==0 and len(' '.join(v['text'] for v in values))>50 and sum(v['confidence'] for v in values)/max(1,len(values))>.93: break
    best.sort(key=lambda v:(round(v['bbox'][1]/12),v['bbox'][0]))
    Path(output).write_text(json.dumps(best,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__': main(*sys.argv[1:])
