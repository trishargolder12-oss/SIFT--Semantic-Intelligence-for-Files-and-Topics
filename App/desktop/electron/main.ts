import { app, BrowserWindow, dialog, ipcMain, nativeTheme, shell } from 'electron';
import { spawn, spawnSync, ChildProcessByStdio } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { createInterface } from 'node:readline';
import path from 'node:path';
import fs from 'node:fs';
import type { Readable } from 'node:stream';
import { chooseOutput, checkedPath, reconcile, openPermittedReference, validReference, type ExportPlan } from './collection_shortcuts';

let window: BrowserWindow | null = null;
let service: ChildProcessByStdio<null, Readable, Readable> | null = null;
let servicePort: number | null = null;
const token = randomBytes(32).toString('hex');
let exportTimer: ReturnType<typeof setTimeout> | undefined;
let pendingReferences = process.argv.filter(arg=>arg.startsWith('--sift-document=')).map(arg=>arg.slice(16));

async function openReference(reference: string): Promise<void> {
  return openPermittedReference(reference,request);
}
async function openPendingReferences(): Promise<void> {
  const references=pendingReferences; pendingReferences=[];
  for (const reference of references) {
    try { await openReference(reference); }
    catch { dialog.showErrorBox('Source unavailable','This source has changed, moved without a verified identity, or is no longer permitted. Refresh its library folder or collection.'); }
  }
}

async function reconcileExports(): Promise<void> {
  try {
    const exports = await request('GET','/collections/exports/pending');
    for (const operation of exports) {
      const check = async (reference: string) => {
        const current=await request('GET',`/collections/exports/${operation.id}/access`);
        if (current.plan!==operation.plan_json) throw new Error('Collection revision changed');
        if(reference) await request('GET','/collections/reference/'+encodeURIComponent(reference));
      };
      try {
        const started=await request('POST',`/collections/exports/${operation.id}`,{state:'writing',plan:operation.plan_json});
        if (!started.accepted) continue;
        await reconcile(operation.plan as ExportPlan,path.join(app.getPath('userData'),'collection-export-journals'),process.execPath,check,app.isPackaged?undefined:app.getAppPath());
        await request('POST',`/collections/exports/${operation.id}`,{state:'done',plan:operation.plan_json});
      } catch (error) { await request('POST',`/collections/exports/${operation.id}`,{state:'failed',plan:operation.plan_json,error:String(error)}); }
    }
  } catch (error) { console.error('[collections]',String(error)); }
  exportTimer=setTimeout(()=>void reconcileExports(),2000);
}

function validId(value: unknown): number {
  if (!Number.isSafeInteger(value) || Number(value) < 1) throw new Error('Invalid ID');
  return Number(value);
}

function trusted(event: Electron.IpcMainInvokeEvent): void {
  if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) {
    throw new Error('Untrusted renderer');
  }
}

async function request(method: string, route: string, body?: unknown): Promise<any> {
  if (!servicePort) throw new Error('Local indexer is not ready');
  const response = await fetch(`http://127.0.0.1:${servicePort}${route}`, {
    method,
    headers: { 'X-SIFT-Token': token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30000),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `Indexer error ${response.status}`);
  return payload;
}

function startService(): Promise<void> {
  return new Promise((resolve, reject) => {
    const backendDir = path.resolve(__dirname, '../../backend');
    const binary = path.join(process.resourcesPath, 'service', 'sift-indexer.exe');
    const venvPython = path.join(backendDir, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    const command = app.isPackaged ? binary : (process.env.SIFT_PYTHON || (fs.existsSync(venvPython) ? venvPython : 'python'));
    const args = app.isPackaged ? [] : ['-m', 'sift_indexer'];
    if (app.isPackaged && !fs.existsSync(binary)) return reject(new Error('Bundled indexer executable is missing'));
    service = spawn(command, args, {
      cwd: app.isPackaged ? process.resourcesPath : backendDir,
      env: { ...process.env, SIFT_SERVICE_TOKEN: token, SIFT_DB_PATH: path.join(app.getPath('userData'), 'library.sqlite') },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let settled = false;
    const timeout = setTimeout(() => {
      if (!settled) { settled = true; reject(new Error('Local indexer startup timed out')); }
    }, 20000);
    service.once('error', error => {
      if (!settled) { settled = true; clearTimeout(timeout); reject(error); }
    });
    service.once('exit', code => {
      servicePort = null;
      if (!settled) { settled = true; clearTimeout(timeout); reject(new Error(`Local indexer exited (${code})`)); }
    });
    createInterface({ input: service.stdout }).on('line', async line => {
      try {
        const ready = JSON.parse(line);
        if (!ready.sift_ready || !Number.isInteger(ready.port)) return;
        servicePort = ready.port;
        for (let i = 0; i < 40; i++) {
          try {
            await request('GET', '/health');
            if (!settled) { settled = true; clearTimeout(timeout); resolve(); }
            return;
          } catch { await new Promise(done => setTimeout(done, 100)); }
        }
        if (!settled) { settled = true; clearTimeout(timeout); reject(new Error('Local indexer did not become ready')); }
      } catch { /* Other service output is diagnostic, not a protocol message. */ }
    });
    service.stderr.on('data', data => console.error(`[indexer] ${String(data).trim()}`));
  });
}

function registerIpc(): void {
  ipcMain.handle('library:choose-folder', async event => {
    trusted(event);
    const result = await dialog.showOpenDialog(window!, { properties: ['openDirectory'] });
    if (result.canceled || !result.filePaths[0]) return null;
    const root = await request('POST', '/folders', { path: result.filePaths[0] });
    let job: { id: number };
    try { job = await request('POST', '/scans', { root_id: root.id }); }
    catch (error) {
      const running = await request('GET', '/jobs/latest');
      if (!running || !['queued', 'running'].includes(running.state)) throw error;
      job = { id: running.id };
    }
    return { root, job };
  });
  ipcMain.handle('library:folders', event => { trusted(event); return request('GET', '/folders'); });
  ipcMain.handle('library:set-folder-state', (event, id: unknown, state: unknown) => {
    trusted(event);
    if (!['active', 'paused', 'removed'].includes(String(state))) throw new Error('Invalid state');
    return request('PATCH', `/folders/${validId(id)}`, { state });
  });
  ipcMain.handle('library:scan', (event, id?: unknown) => {
    trusted(event);
    return request('POST', '/scans', { root_id: id == null ? null : validId(id) });
  });
  ipcMain.handle('library:latest-job', event => { trusted(event); return request('GET', '/jobs/latest'); });
  ipcMain.handle('library:job', (event, id: unknown) => { trusted(event); return request('GET', `/jobs/${validId(id)}`); });
  ipcMain.handle('library:cancel-job', (event, id: unknown) => { trusted(event); return request('POST', `/jobs/${validId(id)}/cancel`); });
  ipcMain.handle('library:documents', (event, offset: unknown, status?: unknown) => {
    trusted(event);
    if (!Number.isSafeInteger(offset) || Number(offset) < 0) throw new Error('Invalid offset');
    if (status !== undefined && !['indexed', 'error', 'missing', 'excluded'].includes(String(status))) throw new Error('Invalid status');
    return request('GET', `/documents?offset=${offset}${status === undefined ? '' : `&status=${status}`}`);
  });
  ipcMain.handle('library:document', (event, id: unknown) => { trusted(event); return request('GET', `/documents/${validId(id)}`); });
  ipcMain.handle('library:search', (event, query: unknown, offset: unknown = 0, limit: unknown = 50) => {
    trusted(event);
    if (typeof query !== 'string' || query.length > 200) throw new Error('Invalid query');
    if (!Number.isSafeInteger(offset) || Number(offset) < 0 || !Number.isSafeInteger(limit) || Number(limit) < 1 || Number(limit) > 100) throw new Error('Invalid search page');
    return request('POST', '/search', { query, offset, limit });
  });
  async function verifiedDocument(id: unknown): Promise<string> {
    const document = await request('GET', `/documents/${validId(id)}/access`);
    if (document.status !== 'indexed') throw new Error('Document is not available');
    const roots = await request('GET', '/folders') as Array<{ id: number; path: string; state: string }>;
    const real = fs.realpathSync.native(document.path);
    if (!roots.some(root => {
      if (root.id !== document.root_id) return false;
      if (root.state !== 'active' && root.state !== 'paused') return false;
      try {
        const canonicalRoot = fs.realpathSync.native(root.path);
        const same = (a: string, b: string) => process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b;
        if (!same(path.resolve(root.path), canonicalRoot) || !same(path.resolve(document.path), real)) return false;
        let current = document.path;
        while (!same(current, root.path)) {
          if (fs.lstatSync(current).isSymbolicLink()) return false;
          const parent = path.dirname(current);
          if (parent === current) return false;
          current = parent;
        }
        const relative = path.relative(canonicalRoot, real);
        return relative === '' || (relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative));
      } catch { return false; }
    })) {
      throw new Error('Document is outside approved folders');
    }
    if (fs.lstatSync(document.path).isSymbolicLink()) throw new Error('Symlink is not allowed');
    await request('GET', `/documents/${validId(id)}/access`);
    return real;
  }
  ipcMain.handle('library:open-document', async (event, id: unknown) => {
    trusted(event);
    const error = await shell.openPath(await verifiedDocument(id));
    if (error) throw new Error(error);
    return true;
  });
  ipcMain.handle('library:reveal-document', async (event, id: unknown) => {
    trusted(event);
    shell.showItemInFolder(await verifiedDocument(id));
    return true;
  });

  function uuid(value: unknown): string {
    if (typeof value !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value)) throw new Error('Invalid conversation reference');
    return value;
  }
  function text(value: unknown, maximum: number): string {
    if (typeof value !== 'string' || !value.trim() || value.length > maximum) throw new Error('Invalid text');
    return value.trim();
  }
  ipcMain.handle('collections:attach',async event=>{
    trusted(event);
    const result=await dialog.showOpenDialog(window!,{properties:['openFile'],filters:[{name:'Syllabus',extensions:['pdf','png','jpg','jpeg']}]});
    if (result.canceled || !result.filePaths[0]) return null;
    return request('POST','/collections/attachments',{path:result.filePaths[0]});
  });
  ipcMain.handle('collections:destination',async event=>{
    trusted(event);
    const result=await dialog.showOpenDialog(window!,{properties:['openDirectory','createDirectory']});
    if (result.canceled || !result.filePaths[0]) return null;
    const selected=chooseOutput(result.filePaths[0]);
    return request('POST','/collections/destination',selected);
  });
  ipcMain.handle('collections:get-destination',event=>{trusted(event);return request('GET','/collections/destination');});
  ipcMain.handle('collections:disconnect-output',event=>{trusted(event);return request('DELETE','/collections/destination');});
  ipcMain.handle('collections:pack',async event=>{
    trusted(event);
    const result=await dialog.showOpenDialog(window!,{properties:['openDirectory'],title:'Select the extracted SIFT OCR pack'});
    if (result.canceled || !result.filePaths[0]) return null;
    return request('POST','/collections/vision/pack',{path:result.filePaths[0]});
  });
  ipcMain.handle('collections:vision',event=>{trusted(event);return request('GET','/collections/vision');});
  ipcMain.handle('collections:list',event=>{trusted(event);return request('GET','/collections');});
  ipcMain.handle('collections:create',(event,input:unknown)=>{
    trusted(event); if (!input || typeof input!=='object') throw new Error('Invalid syllabus');
    const value=input as Record<string,unknown>;
    return request('POST','/collections',{text:value.text==null?'':text(value.text,100000),attachment_id:value.attachment_id==null?null:uuid(value.attachment_id),collection_id:value.collection_id==null?null:uuid(value.collection_id)});
  });
  ipcMain.handle('collections:detail',(event,id:unknown,topic:unknown,offset:unknown=0)=>{
    trusted(event); if (!Number.isSafeInteger(offset) || Number(offset)<0) throw new Error('Invalid page');
    return request('GET',`/collections/${uuid(id)}?offset=${offset}${topic==null?'':'&topic='+uuid(topic)}`);
  });
  ipcMain.handle('collections:outline',(event,id:unknown,outline:unknown)=>{
    trusted(event); if (!outline || typeof outline!=='object' || JSON.stringify(outline).length>500000) throw new Error('Invalid syllabus outline');
    return request('PATCH',`/collections/${uuid(id)}/outline`,{outline});
  });
  ipcMain.handle('collections:refresh',(event,id:unknown)=>{trusted(event);return request('POST',`/collections/${uuid(id)}/refresh`);});
  ipcMain.handle('collections:cancel',(event,id:unknown)=>{trusted(event);return request('POST',`/collections/jobs/${validId(id)}/cancel`);});
  ipcMain.handle('collections:detach',(event,id:unknown)=>{trusted(event);return request('DELETE',`/collections/attachments/${uuid(id)}`);});
  ipcMain.handle('collections:decision',(event,id:unknown,topic:unknown,file:unknown,decision:unknown,target:unknown)=>{
    trusted(event);if (!['auto','approved','rejected'].includes(String(decision))) throw new Error('Invalid review decision');
    return request('POST',`/collections/${uuid(id)}/assignments`,{topic_id:uuid(topic),file_id:validId(file),decision,target:target==null?null:uuid(target)});
  });
  ipcMain.handle('collections:open',(event,reference:unknown)=>{trusted(event);if (typeof reference!=='string') throw new Error('Invalid reference');return openReference(reference);});
  ipcMain.handle('collections:page',(event,reference:unknown,version:unknown,page:unknown)=>{
    trusted(event);if (typeof reference!=='string' || !validReference(reference) || typeof version!=='string' || !/^[a-f0-9]{64}$/.test(version)) throw new Error('Invalid page reference');
    return request('GET',`/collections/page/${encodeURIComponent(reference)}/${version}/${validId(page)}`);
  });
  ipcMain.handle('collections:retry',(event,id:unknown)=>{trusted(event);return request('POST',`/collections/${uuid(id)}/export`);});
  ipcMain.handle('collections:cancel-export',(event,id:unknown)=>{trusted(event);return request('POST',`/collections/exports/${uuid(id)}/cancel`);});
  ipcMain.handle('collections:show-output',async event=>{
    trusted(event);const destination=await request('GET','/collections/destination');
    if (!destination) throw new Error('Select an output folder first');
    const error=await shell.openPath(checkedPath(destination.path));if(error) throw new Error(error);return true;
  });
  ipcMain.handle('discovery:status', event => { trusted(event); return request('GET', '/intelligence/status'); });
  ipcMain.handle('discovery:setup', async event => { trusted(event); await shell.openExternal('https://ollama.com/download/windows'); return true; });
  ipcMain.handle('discovery:models', (event, enabled: unknown) => { trusted(event); if (typeof enabled !== 'boolean') throw new Error('Invalid setting'); return request('PATCH', '/intelligence/models', { enabled }); });
  ipcMain.handle('discovery:download', (event, role: unknown) => { trusted(event); if (!['embedding', 'intent', 'vision'].includes(String(role))) throw new Error('Invalid model'); return request('POST', '/intelligence/models/download', { role, confirmed: true }); });
  ipcMain.handle('discovery:rebuild', event => { trusted(event); return request('POST', '/intelligence/rebuild'); });
  ipcMain.handle('discovery:chat', (event, message: unknown, conversationId: unknown, rawFilters: unknown, timezoneOffset: unknown, rawContext: unknown) => {
    trusted(event);
    if (!rawFilters || typeof rawFilters !== 'object' || Array.isArray(rawFilters)) throw new Error('Invalid discovery filters');
    const input = rawFilters as Record<string, unknown>;
    const filters: Record<string, unknown> = {};
    for (const key of ['root_id', 'group_id']) if (input[key] != null) filters[key] = validId(input[key]);
    if (input.extension != null) { if (!['.pdf', '.docx', '.txt'].includes(String(input.extension))) throw new Error('Invalid file type'); filters.extension = input.extension; }
    if (!Number.isInteger(timezoneOffset) || Math.abs(Number(timezoneOffset)) > 840) throw new Error('Invalid timezone');
    let result_context: {turn_id:string;offset:number}|null = null;
    if (rawContext != null) {
      const context = rawContext as {turn_id:unknown;offset:unknown};
      if (!Number.isSafeInteger(context.offset) || Number(context.offset)<0) throw new Error('Invalid result context');
      result_context = {turn_id:uuid(context.turn_id),offset:Number(context.offset)};
    }
    return request('POST', '/intelligence/chat', { message: text(message, 1000), conversation_id: conversationId == null ? null : uuid(conversationId), filters, timezone_offset: timezoneOffset, result_context });
  });
  ipcMain.handle('discovery:job', (event, id: unknown) => { trusted(event); return request('GET', `/intelligence/jobs/${validId(id)}`); });
  ipcMain.handle('discovery:cancel', (event, id: unknown) => { trusted(event); return request('POST', `/intelligence/jobs/${validId(id)}/cancel`); });
  ipcMain.handle('discovery:history', (event, id: unknown) => { trusted(event); return request('GET', `/intelligence/conversations/${uuid(id)}`); });
  ipcMain.handle('discovery:turn', (event, id: unknown, offset: unknown) => { trusted(event); if (!Number.isSafeInteger(offset) || Number(offset) < 0) throw new Error('Invalid result page'); return request('GET', `/intelligence/turns/${uuid(id)}?offset=${offset}`); });
  ipcMain.handle('discovery:groups', event => { trusted(event); return request('GET', '/intelligence/groups'); });
  ipcMain.handle('discovery:rename', (event, id: unknown, name: unknown) => { trusted(event); return request('PATCH', `/intelligence/groups/${validId(id)}`, { name: text(name, 100) }); });
  ipcMain.handle('discovery:correct', (event, id: unknown, input: unknown) => {
    trusted(event);
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid corrections');
    const assignments: Record<string, string[]> = {};
    for (const [kind, names] of Object.entries(input)) {
      if (!['subject', 'topic', 'type'].includes(kind) || !Array.isArray(names) || names.length > 12) throw new Error('Invalid correction');
      assignments[kind] = names.map(name => text(name, 100));
    }
    return request('PATCH', `/intelligence/documents/${validId(id)}/groups`, { assignments });
  });
  ipcMain.handle('discovery:preview', async (event, turnId: unknown, id: unknown) => {
    trusted(event);
    await request('GET', `/intelligence/turns/${uuid(turnId)}/files/${validId(id)}`);
    const detail = await request('GET', `/documents/${validId(id)}`);
    await request('GET', `/intelligence/turns/${uuid(turnId)}/files/${validId(id)}`);
    return detail;
  });
  ipcMain.handle('discovery:open', async (event, turnId: unknown, id: unknown, reveal: unknown) => {
    trusted(event);
    if (typeof reveal !== 'boolean') throw new Error('Invalid file action');
    await request('GET', `/intelligence/turns/${uuid(turnId)}/files/${validId(id)}`);
    const target = await verifiedDocument(id);
    if (reveal) shell.showItemInFolder(target);
    else { const error = await shell.openPath(target); if (error) throw new Error(error); }
    return true;
  });
}

async function createWindow(): Promise<void> {
  window = new BrowserWindow({
    width: 1200, height: 820, minWidth: 820, minHeight: 600,
    backgroundColor: '#08152E',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', event => event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  if (app.isPackaged) await window.loadFile(path.join(__dirname, '../dist/index.html'));
  else await window.loadURL('http://127.0.0.1:5173');
}

const singleInstance = app.requestSingleInstanceLock();
if (!singleInstance) app.quit();
else app.on('second-instance', (_event, argv) => {
  pendingReferences.push(...argv.filter(arg=>arg.startsWith('--sift-document=')).map(arg=>arg.slice(16)));
  if (window?.isMinimized()) window.restore();
  window?.focus();
  if (servicePort) void openPendingReferences();
});

if (singleInstance) app.whenReady().then(async () => {
  nativeTheme.themeSource = 'dark';
  registerIpc();
  try {
    await startService();
    await createWindow();
    void reconcileExports();
    await openPendingReferences();
  } catch (error) {
    dialog.showErrorBox('SIFT could not start', String(error));
    app.quit();
  }
});
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => {
  if (exportTimer) clearTimeout(exportTimer);
  if (!service?.pid) return;
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(service.pid), '/t', '/f'], { windowsHide: true, stdio: 'ignore' });
  } else service.kill();
});
