const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
if(!process.versions.electron){
  const child=spawnSync(require('electron'),[__filename],{stdio:'inherit',windowsHide:true});process.exit(child.status??1);
}
const {app,shell}=require('electron');
const assert=require('node:assert/strict');
app.disableHardwareAcceleration();
app.whenReady().then(async()=>{
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'sift-shortcuts-'));
 const {chooseOutput,reconcile,safeName,checkedPath,openPermittedReference}=require('../dist-electron/collection_shortcuts');
 try{
  const output=chooseOutput(temporary),collection=crypto.randomUUID();
  const journal=path.join(temporary,'journals');
  const source=path.join(temporary,'original.txt');fs.writeFileSync(source,'Original notes stay read-only.');
  const hash=()=>crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex');const before=hash();
  const target=path.join(temporary,'route-target.cjs');
  fs.writeFileSync(target,`const {app}=require('electron');const fs=require('fs'),path=require('path');app.setPath('userData',path.join(__dirname,'test-user-data'));const lock=app.requestSingleInstanceLock();function record(args){fs.appendFileSync(path.join(__dirname,'opened.txt'),JSON.stringify(args)+'\\n');}if(!lock)app.quit();else{app.on('second-instance',(_,args)=>record(args));app.whenReady().then(()=>{record(process.argv);setTimeout(()=>app.quit(),8000);});}`);
  const plan={collection_id:collection,subject:'COA',revision:1,destination:{...output,base_path:output.base},items:[
   {id:'one',parts:['Unit 1','CON'],name:'duplicate?.pdf',reference:'file:1'},
   {id:'two',parts:['Unit 1','CON'],name:'duplicate?.pdf',reference:'file:2'}]};
  const check=async reference=>{if(reference&&!/^file:[12]$/.test(reference))throw Error('Not permitted');};
  const root=await reconcile(plan,journal,process.execPath,check,target);
  const links=fs.readdirSync(path.join(root,'Unit 1','_CON')).filter(n=>n.endsWith('.lnk'));
  assert.equal(links.length,2);const link=path.join(root,'Unit 1','_CON',links[0]);
  assert.match(shell.readShortcutLink(link).args,/--sift-document=file:[12]$/);
  assert.ok(!shell.readShortcutLink(link).args.includes(source));
  await reconcile(plan,journal,process.execPath,check,target);
  assert.equal(fs.readdirSync(path.dirname(link)).length,2);
  let interrupted=false;
  await assert.rejects(()=>reconcile({...plan,items:[...plan.items,{id:'three',parts:['Unit 2'],name:'new.pdf',reference:'file:3'}]},journal,process.execPath,async reference=>{if(reference==='file:3'){interrupted=true;throw Error('Simulated access loss');}},target));
  assert.equal(interrupted,true);
  await reconcile(plan,journal,process.execPath,check,target);
  const unrelatedLink=path.join(path.dirname(link),'unrelated.lnk');shell.writeShortcutLink(unrelatedLink,'create',{target:process.execPath,args:'--help'});
  const marker=path.join(temporary,'opened.txt');
  assert.equal(await shell.openPath(link),'');
  for(let i=0;i<100&&!fs.existsSync(marker);i++)await new Promise(r=>setTimeout(r,50));
  assert.ok(fs.existsSync(marker),'Real Windows shortcut did not cold-launch its target');
  assert.equal(await shell.openPath(link),'');
  for(let i=0;i<100&&fs.readFileSync(marker,'utf8').trim().split('\n').length<2;i++)await new Promise(r=>setTimeout(r,50));
  assert.equal(fs.readFileSync(marker,'utf8').trim().split('\n').length,2,'Already-running target did not receive the reference');
  const route=async()=>({path:source,root_path:temporary,content_hash:before});let opened;
  await openPermittedReference('file:1',route,async file=>{opened=file;return '';});assert.equal(opened,source);
  await assert.rejects(()=>openPermittedReference('file:1',async()=>{throw Error('Revoked');},async()=>{throw Error('Must not open');}));
  const unrelated=path.join(root,'my-file.txt');fs.writeFileSync(unrelated,'User content');
  await reconcile({...plan,items:[]},journal,process.execPath,check,target);
  assert.equal(fs.readFileSync(unrelated,'utf8'),'User content');assert.ok(!fs.existsSync(link));
  assert.ok(fs.existsSync(unrelatedLink),'Unrelated shortcut was removed');
  assert.equal(hash(),before);assert.match(safeName('NUL.txt'),/^_/);assert.throws(()=>checkedPath(output.path,'../escape'));
  console.log('PASS real .lnk creation, cold/warm routing, idempotency, collision names, permission recheck, owned-only cleanup and original preservation');
  await new Promise(r=>setTimeout(r,8500));
 }finally{
  if(path.dirname(temporary)===os.tmpdir()&&path.basename(temporary).startsWith('sift-shortcuts-'))fs.rmSync(temporary,{recursive:true,force:true});
 }
 app.quit();
}).catch(error=>{console.error(error);app.exit(1);});
