import { shell } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';

export type ExportItem = { id: string; parts: string[]; name: string; reference: string };
export type ExportPlan = { collection_id: string; subject: string; revision: number; destination: { id: string; path: string; base_path: string }; items: ExportItem[] };
type Entry = { path: string; sha256: string; reference: string };
type Journal = { collection: string; destination: string; root: string; files: Entry[]; directories: string[] };
const hash = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');
export const validReference = (value: string) => /^(file:[1-9]\d*|attachment:[a-f0-9-]{36})$/.test(value);
export function safeName(value: string, maximum=60): string {
  const clean = value.normalize('NFKC').replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/[. ]+$/g, '').trim() || 'Untitled';
  const reserved = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(clean);
  const result = (reserved ? '_' : '') + clean;
  return result.length > maximum ? result.slice(0, maximum-9) + '-' + hash(value).slice(0,8) : result;
}
export function checkedPath(root: string, relative=''): string {
  const base = path.resolve(root), target = path.resolve(base, relative), rel = path.relative(base,target);
  if (rel === '..' || rel.startsWith('..'+path.sep) || path.isAbsolute(rel)) throw new Error('Output escapes the selected destination');
  let current = target;
  while (true) {
    if (fs.existsSync(current)) {
      if (fs.lstatSync(current).isSymbolicLink() || fs.realpathSync.native(current).toLowerCase() !== current.toLowerCase()) throw new Error('Linked output paths are not permitted');
    }
    const parent = path.dirname(current); if (parent === current) break; current = parent;
  }
  if (target.length > 240) throw new Error('Collection path is too long. Select a destination closer to the drive root.');
  return target;
}
export function chooseOutput(base: string): { id: string; path: string; base: string } {
  checkedPath(base);
  let selected = path.join(base,'SIFT Study Collections');
  if (fs.existsSync(selected)) selected += ' - ' + randomUUID().slice(0,8);
  const id = randomUUID(); checkedPath(base,path.relative(base,selected));
  fs.mkdirSync(selected);
  fs.writeFileSync(path.join(selected,'.sift-output.json'),JSON.stringify({id,app:'org.sift.local-library'}),{flag:'wx'});
  return {id,path:selected,base};
}

export async function openPermittedReference(reference: string, request: (method:string,route:string)=>Promise<any>, openFile: (file:string)=>Promise<string> = file=>shell.openPath(file)): Promise<void> {
  if (!validReference(reference)) throw new Error('Invalid document reference');
  const route='/collections/reference/'+encodeURIComponent(reference);
  const source=await request('GET',route);
  const root=reference.startsWith('file:')?source.root_path:path.dirname(source.path);
  checkedPath(root,path.relative(root,source.path));
  const fresh=await request('GET',route);
  if (fresh.path!==source.path || fresh.content_hash!==source.content_hash) throw new Error('Source changed while opening');
  const error=await openFile(source.path);if(error)throw new Error(error);
}

export async function reconcile(plan: ExportPlan, journalDirectory: string, executable: string, check: (reference: string)=>Promise<unknown>, developmentApp?: string): Promise<string> {
  if (!/^[a-f0-9-]{36}$/.test(plan.collection_id) || !/^[a-f0-9-]{36}$/.test(plan.destination.id)) throw new Error('Invalid collection identity');
  const base = checkedPath(plan.destination.path);
  const marker = JSON.parse(fs.readFileSync(path.join(base,'.sift-output.json'),'utf8'));
  if (marker.id !== plan.destination.id || marker.app !== 'org.sift.local-library') throw new Error('Output permission or marker changed');
  fs.mkdirSync(journalDirectory,{recursive:true});
  const journalFile = path.join(journalDirectory,plan.collection_id+'-'+plan.destination.id+'.json');
  let journal: Journal = fs.existsSync(journalFile) ? JSON.parse(fs.readFileSync(journalFile,'utf8')) : {collection:plan.collection_id,destination:plan.destination.id,root:safeName(plan.subject)+' ['+plan.collection_id.slice(0,8)+']',files:[],directories:[]};
  if (journal.collection!==plan.collection_id || journal.destination!==plan.destination.id || path.basename(journal.root)!==journal.root) throw new Error('Invalid export journal');
  const save = () => { const temp=journalFile+'.tmp'; fs.writeFileSync(temp,JSON.stringify(journal)); fs.renameSync(temp,journalFile); };
  const owned = (entry: Entry) => {
    const file=checkedPath(base,entry.path);
    if (!fs.existsSync(file) || hash(fs.readFileSync(file))!==entry.sha256) return false;
    try { const link=shell.readShortcutLink(file); return link.target.toLowerCase()===executable.toLowerCase() && link.args===argumentsFor(entry.reference); } catch { return false; }
  };
  const argumentsFor = (reference: string) => (developmentApp ? '"'+developmentApp+'" ' : '')+'--sift-document='+reference;
  const ensure = (relative: string) => {
    const parts=relative.split(path.sep); let prefix='';
    for (const part of parts) {
      prefix=path.join(prefix,part); const directory=checkedPath(base,prefix);
      if (!fs.existsSync(directory)) { journal.directories.push(prefix); save(); fs.mkdirSync(directory); }
      if (!fs.statSync(directory).isDirectory()) throw new Error('A user file occupies a collection folder name');
    }
  };
  const desired = new Set<string>();
  await check('');
  for (const item of plan.items) {
    if (!validReference(item.reference)) throw new Error('Invalid shortcut reference');
    await check(item.reference);
    const relative=path.join(journal.root,...item.parts.map(part=>safeName(part)),safeName(item.name.replace(/\.(pdf|docx|txt|png|jpe?g)$/i,''),65)+' ['+hash(item.id).slice(0,8)+'].lnk');
    const destination=checkedPath(base,relative); desired.add(relative);
    const old=journal.files.find(entry=>entry.path===relative);
    if (fs.existsSync(destination)) {
      if (old && owned(old)) continue;
      throw new Error('A modified or unrelated file occupies a shortcut name. It has been preserved.');
    }
    ensure(path.dirname(relative));
    const stageRelative=path.join(path.dirname(relative),'.sift-stage-'+randomUUID()+'.lnk');
    const stage=checkedPath(base,stageRelative);
    if (!shell.writeShortcutLink(stage,'create',{target:executable,args:argumentsFor(item.reference),description:'Open this permitted source through SIFT',cwd:path.dirname(executable)})) throw new Error('Windows could not create a shortcut');
    const digest=hash(fs.readFileSync(stage));
    // Record ownership before publishing; a crash after copy is recoverable by hash/link checks.
    const entry={path:relative,sha256:digest,reference:item.reference};
    journal.files=journal.files.filter(e=>e.path!==relative); journal.files.push(entry,{...entry,path:stageRelative}); save();
    await check(item.reference);
    fs.copyFileSync(stage,destination,fs.constants.COPYFILE_EXCL);
    fs.unlinkSync(stage); journal.files=journal.files.filter(e=>e.path!==stageRelative); save();
  }
  for (const entry of [...journal.files]) {
    await check('');
    if (desired.has(entry.path)) continue;
    if (owned(entry)) fs.unlinkSync(checkedPath(base,entry.path));
    else if (fs.existsSync(checkedPath(base,entry.path))) throw new Error('An old shortcut was modified and was preserved. Resolve it before retrying export.');
    journal.files=journal.files.filter(e=>e.path!==entry.path); save();
  }
  for (const relative of [...new Set(journal.directories)].sort((a,b)=>b.length-a.length)) {
    const directory=checkedPath(base,relative);
    if (!fs.existsSync(directory)) { journal.directories=journal.directories.filter(d=>d!==relative); continue; }
    if (fs.readdirSync(directory).length===0) { fs.rmdirSync(directory); journal.directories=journal.directories.filter(d=>d!==relative); }
  }
  save();
  return checkedPath(base,journal.root);
}
