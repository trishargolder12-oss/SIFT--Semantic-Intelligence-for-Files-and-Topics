"""Small labeled synthetic visual set. Does not claim real handwriting/vision quality."""
import collections,ctypes,json,re,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageEnhance


def memory(pid):
    from ctypes import wintypes as w
    class Counters(ctypes.Structure):
        _fields_=[('cb',w.DWORD),('faults',w.DWORD),*[(n,ctypes.c_size_t) for n in ['peak','working','pagedpeak','paged','nonpagedpeak','nonpaged','pagefile','pagefilepeak','private']]]
    kernel=ctypes.WinDLL('kernel32');psapi=ctypes.WinDLL('psapi')
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE];psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.c_void_p,w.DWORD]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return 0
    try:
        data=Counters();data.cb=ctypes.sizeof(data)
        return data.working if psapi.GetProcessMemoryInfo(handle,ctypes.byref(data),data.cb) else 0
    finally:kernel.CloseHandle(handle)


def main():
    root=Path(__file__).resolve().parents[2];directory=root/'tmp/visual-quality';directory.mkdir(parents=True,exist_ok=True)
    pack=root/'tmp/ocr-pack';font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',34)
    text='Subject: Computer Architecture\nUnit 1 - Fundamentals\nVon Neumann Architecture; Number Systems\nUnit 2 - Processor Organization\nInstruction Cycle; Memory Hierarchy'
    image=Image.new('RGB',(1300,620),'white');ImageDraw.Draw(image).multiline_text((60,60),text,font=font,fill='black',spacing=24)
    cases=[('printed',image,text),('rotated',image.rotate(90,expand=True),text),('blurred_low_contrast',ImageEnhance.Contrast(image.filter(ImageFilter.GaussianBlur(4))).enhance(.2),text)]
    handwriting=Image.new('RGB',(1300,620),'white');handfont=ImageFont.truetype('C:/Windows/Fonts/segoepr.ttf',32)
    ImageDraw.Draw(handwriting).multiline_text((60,60),text,font=handfont,fill='#4b4b4b',spacing=20)
    cases.append(('synthetic_handwriting_font',handwriting,text))
    difficult=handwriting.filter(ImageFilter.GaussianBlur(3)).rotate(-8,fillcolor='white')
    cases.append(('difficult_synthetic_handwriting',difficult,text))
    for labeled in [True,False]:
        diagram=Image.new('RGB',(1200,500),'white');draw=ImageDraw.Draw(diagram)
        for x,name in [(70,'Input'),(450,'CPU'),(850,'Memory')]:
            draw.rectangle((x,150,x+240,300),outline='black',width=3)
            if labeled:draw.text((x+30,190),name,font=font,fill='black')
        draw.line((310,225,450,225),fill='black',width=4);draw.line((690,225,850,225),fill='black',width=4)
        cases.append(('labeled_diagram' if labeled else 'unlabeled_diagram',diagram,'Input CPU Memory' if labeled else ''))
    table=Image.new('RGB',(1200,600),'white');draw=ImageDraw.Draw(table)
    table_text='Unit Topic Hours\n1 Architecture 6\n2 Processor 8\nE = m c 2'
    draw.multiline_text((80,70),table_text,font=font,fill='black',spacing=35)
    draw.line((70,120,1000,120),fill='black',width=2)
    cases.append(('table_and_equation',table,table_text))
    results=[]
    for name,image,expected in cases:
        source=directory/(name+'.png');output=directory/(name+'.json');log=directory/(name+'.log');image.save(source)
        start=time.perf_counter();peak=0
        with log.open('wb') as diagnostics:
            process=subprocess.Popen([str(pack/'sift-ocr/sift-ocr.exe'),str(source),str(pack/'models'),str(output)],stdout=diagnostics,stderr=diagnostics,creationflags=0x08000000)
            while process.poll() is None and time.perf_counter()-start<90:
                peak=max(peak,memory(process.pid));time.sleep(.05)
            if process.poll() is None:process.kill();process.wait()
        extracted=json.loads(output.read_text()) if output.exists() else []
        predicted=' '.join(r['text'] for r in extracted)
        tokens=lambda s:collections.Counter(re.findall(r'\w+',s.casefold()))
        truth,actual=tokens(expected),tokens(predicted);correct=sum((truth&actual).values())
        results.append({'case':name,'exit':process.returncode,'seconds':round(time.perf_counter()-start,2),'peak_working_mb':round(peak/1024**2,1),
            'expected_tokens':sum(truth.values()),'recognized_tokens':sum(actual.values()),'correct_tokens':correct,
            'token_precision':round(correct/max(1,sum(actual.values())),3),'token_recall':round(correct/max(1,sum(truth.values())),3),
            'low_confidence_regions':sum(r['confidence']<.85 for r in extracted),'real_handwriting':False})
        print(json.dumps(results[-1]),flush=True)
    (root/'docs/VISUAL_QUALITY_MEASUREMENTS.json').write_text(json.dumps({'engine':'PaddleOCR3.2.0 PP-OCRv5 mobile CPU; frozen worker; networking blocked','cases':results,
        'limits':'Synthetic English set only. Segoe Print is a handwriting-style font, not real handwritten samples. No Qwen3-VL or PP-StructureV3 quality claims.'},indent=2))


if __name__=='__main__':main()
