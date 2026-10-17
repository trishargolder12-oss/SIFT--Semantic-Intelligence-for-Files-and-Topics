const {spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
const python=path.join(root,'tmp/ocr-env/Scripts/python.exe');
const output=path.join(root,'tmp/ocr-pack');
const args=['-m','PyInstaller','--noconfirm','--onedir','--name','sift-ocr','--distpath',output,
 '--workpath',path.join(root,'tmp/ocr-build'),'--specpath',path.join(root,'tmp/ocr-build'),
 '--collect-all','paddle','--collect-all','paddleocr','--collect-all','paddlex','--collect-all','cv2',
 '--collect-all','pyclipper','--collect-all','shapely','--recursive-copy-metadata','paddleocr',
 path.join(root,'backend/ocr_pack/worker.py')];
const result=spawnSync(python,args,{cwd:root,stdio:'inherit',env:{...process.env,PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:'True'}});
if(result.status!==0)process.exit(result.status||1);
const metadata=spawnSync(python,[path.join(root,'backend/ocr_pack/copy_metadata.py'),path.join(output,'sift-ocr/_internal')],{stdio:'inherit'});
if(metadata.status!==0)process.exit(metadata.status||1);
const packageResult=spawnSync(python,[path.join(root,'backend/ocr_pack/package_pack.py'),output,path.join(root,'desktop/release')],{stdio:'inherit'});
process.exit(packageResult.status||0);
