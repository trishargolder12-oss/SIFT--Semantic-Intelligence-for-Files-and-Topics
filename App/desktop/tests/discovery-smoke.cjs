/* Real temporary-library API + production React flows; native file viewers are stubbed. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright-core');

(async () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'sift-discovery-ui-'));
  const library = path.join(temporary, 'library');
  fs.mkdirSync(path.join(library, 'COA'), { recursive: true });
  fs.writeFileSync(path.join(library, 'COA', 'full notes.txt'), 'Subject: Computer Organization and Architecture\nTopic: Von Neumann architecture\nFull notes: Instructions and data share memory in the stored program design.');
  fs.writeFileSync(path.join(library, 'COA', 'week-02.txt'), 'Subject: Computer Organization and Architecture\nTopic: Von Neumann architecture\nA processor, shared memory, input and output form the stored program machine.');
  fs.writeFileSync(path.join(library, 'COA', 'syllabus.txt'), 'Subject: Computer Organization and Architecture\nSyllabus: Units on the instruction cycle and memory hierarchy.');
  for(const name of ['full notes.txt','week-02.txt'])fs.appendFileSync(path.join(library,'COA',name),'\nThe shared bus carries instructions and values between the processor and memory. This explains the stored program organization and its data flow during execution.');
  const backend = path.resolve(__dirname, '../../backend');
  const secret = crypto.randomBytes(32).toString('hex');
  const processes = [];
  let browser, errors = [], serviceErrors = '', passed = 0;
  const output = path.resolve(__dirname, '../../docs/design/previews');
  fs.mkdirSync(output, { recursive: true });
  try {
    const python = path.join(backend, '.venv/Scripts/python.exe');
    const service = spawn(python, ['-m', 'sift_indexer'], { cwd: backend, env: { ...process.env, SIFT_SERVICE_TOKEN: secret, SIFT_DB_PATH: path.join(temporary, 'index.sqlite') }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    processes.push(service);
    service.stderr.on('data', data => { serviceErrors = (serviceErrors + data).slice(-12000); });
    const port = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Service startup timed out: ' + serviceErrors)), 20000);
      let text = '';
      service.stdout.on('data', data => { text += data; for (const line of text.split('\n')) { try { const item = JSON.parse(line); if (item.sift_ready) { clearTimeout(timer); resolve(item.port); } } catch {} } });
      service.once('exit', code => { clearTimeout(timer); reject(new Error('Service exited: ' + code + serviceErrors)); });
    });
    async function api(method, route, body) {
      const response = await fetch(`http://127.0.0.1:${port}${route}`, { method, headers: { 'X-SIFT-Token': secret, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      return payload;
    }
    const vite = path.join(path.dirname(require.resolve('vite/package.json')), 'bin/vite.js');
    const ui = spawn(process.execPath, [vite, '--host', '127.0.0.1', '--port', '5181', '--strictPort'], { cwd: path.resolve(__dirname, '..'), windowsHide: true, stdio: 'ignore' });
    processes.push(ui);
    const url = 'http://127.0.0.1:5181';
    for (let i = 0; i < 100; i++) { try { if ((await fetch(url)).ok) break; } catch {} await new Promise(resolve => setTimeout(resolve, 100)); }
    browser = await chromium.launch({ channel: process.env.SIFT_BROWSER_CHANNEL || 'msedge', headless: true });
    const page = await browser.newPage({ viewport: { width: 1200, height: 820 }, reducedMotion: 'reduce' });
    page.on('pageerror', error => errors.push(error.message));
    const outside = [];
    page.on('request', request => { if (!['localhost', '127.0.0.1'].includes(new URL(request.url()).hostname)) outside.push(request.url()); });
    const nativeActions = [];
    let collectionOutput;
    await page.exposeBinding('__testSiftBridge', async (_source, method, args) => {
      const [id, second] = args;
      switch (method) {
        case 'collections': return api('GET','/collections');
        case 'collectionVision': return api('GET','/collections/vision');
        case 'collectionGetDestination': return api('GET','/collections/destination');
        case 'collectionDestination': {
          if (!collectionOutput) { const selected=path.join(temporary,'study-output');fs.mkdirSync(selected);const key=crypto.randomUUID();fs.writeFileSync(path.join(selected,'.sift-output.json'),JSON.stringify({id:key,app:'org.sift.local-library'}));collectionOutput={id:key,path:selected,base:temporary}; }
          return api('POST','/collections/destination',collectionOutput);
        }
        case 'collectionCreate': return api('POST','/collections',id);
        case 'collectionDetail': return api('GET',`/collections/${id}?offset=${args[2]||0}${second?'&topic='+second:''}`);
        case 'collectionOutline': return api('PATCH',`/collections/${id}/outline`,{outline:second});
        case 'collectionRefresh': return api('POST',`/collections/${id}/refresh`);
        case 'collectionCancel': return api('POST',`/collections/jobs/${id}/cancel`);
        case 'collectionDecision': return api('POST',`/collections/${id}/assignments`,{topic_id:second,file_id:args[2],decision:args[3],target:args[4]||null});
        case 'collectionRetry': return api('POST',`/collections/${id}/export`);
        case 'collectionOpen': await api('GET','/collections/reference/'+encodeURIComponent(id));nativeActions.push('collectionOpen');return;
        case 'folders': return api('GET', '/folders');
        case 'documents': return api('GET', `/documents?offset=${id || 0}${second ? '&status='+second : ''}`);
        case 'latestJob': return api('GET', '/jobs/latest');
        case 'job': return api('GET', `/jobs/${id}`);
        case 'chooseFolder': { const root = await api('POST', '/folders', { path: library }); const job = await api('POST', '/scans', { root_id: root.id }); return { root, job }; }
        case 'setFolderState': return api('PATCH', `/folders/${id}`, { state: second });
        case 'scan': return api('POST', '/scans', { root_id: id || null });
        case 'cancelJob': return api('POST', `/jobs/${id}/cancel`);
        case 'document': return api('GET', `/documents/${id}`);
        case 'search': return api('POST', '/search', { query: id, offset: second || 0, limit: args[2] || 50 });
        case 'openDocument': case 'revealDocument': await api('GET', `/documents/${id}/access`); nativeActions.push(method); return true;
        case 'discoveryStatus': return api('GET', '/intelligence/status');
        case 'discoveryGroups': return api('GET', '/intelligence/groups');
        case 'discoveryHistory': return api('GET', `/intelligence/conversations/${id}`);
        case 'discoveryTurn': return api('GET', `/intelligence/turns/${id}?offset=${second}`);
        case 'discoveryChat': return api('POST', '/intelligence/chat', { message: id, conversation_id: second, filters: args[2], timezone_offset: args[3], result_context:args[4] });
        case 'discoveryJob': return api('GET', `/intelligence/jobs/${id}`);
        case 'discoveryCancel': return api('POST', `/intelligence/jobs/${id}/cancel`);
        case 'discoveryModels': return api('PATCH', '/intelligence/models', { enabled: id });
        case 'discoveryRebuild': return api('POST', '/intelligence/rebuild');
        case 'discoveryRename': return api('PATCH', `/intelligence/groups/${id}`, { name: second });
        case 'discoveryCorrect': return api('PATCH', `/intelligence/documents/${id}/groups`, { assignments: second });
        case 'discoveryPreview': await api('GET', `/intelligence/turns/${id}/files/${second}`); return api('GET', `/documents/${second}`);
        case 'discoveryOpen': await api('GET', `/intelligence/turns/${id}/files/${second}`); await api('GET', `/documents/${second}/access`); nativeActions.push('discoveryOpen'); return true;
        default: throw new Error('Unexpected test bridge action: ' + method);
      }
    });
    await page.addInitScript(() => {
      window.sift = Object.fromEntries(['collections','collectionVision','collectionGetDestination','collectionDestination','collectionCreate','collectionDetail','collectionOutline','collectionRefresh','collectionCancel','collectionDecision','collectionRetry','collectionOpen','folders','documents','latestJob','job','chooseFolder','setFolderState','scan','cancelJob','document','search','openDocument','revealDocument','discoveryStatus','discoveryGroups','discoveryHistory','discoveryTurn','discoveryChat','discoveryJob','discoveryCancel','discoveryModels','discoveryRebuild','discoveryRename','discoveryCorrect','discoveryPreview','discoveryOpen'].map(method => [method, (...args) => window.__testSiftBridge(method, args)]));
    });
    async function check(name, work) { await work(); passed++; console.log('PASS ' + name); }
    await page.goto(url);
    await check('Native-picker boundary connects a temporary folder and builds real sections', async () => {
      await page.getByRole('button', { name: 'Add your first folder' }).click();
      await page.waitForFunction(() => document.querySelectorAll('.file-row').length === 3);
      for (let i = 0; i < 100; i++) { if ((await api('GET', '/intelligence/status')).documents.ready === 3) break; await new Promise(resolve => setTimeout(resolve, 100)); }
      await page.getByRole('button', { name: 'Find files with SIFT', exact: true }).click();
      await page.getByRole('heading', { name: 'Find it with SIFT' }).waitFor();
      await page.locator('.section-link').filter({ hasText: 'Computer Organization' }).first().waitFor();
      assert.match(await page.locator('.discovery-scope').textContent(), /Approved folders only/);
      await page.screenshot({ path: path.join(output, 'discovery-welcome.png') });
    });
    const question = page.getByRole('textbox', { name: 'Ask SIFT to find a file' });
    await check('Chat has no outer border or white input focus outline',async()=>{
      await question.focus();
      assert.equal(await question.evaluate(el=>getComputedStyle(el).outlineStyle),'none');
      assert.equal(await page.locator('.discovery-dialog').evaluate(el=>getComputedStyle(el).borderTopWidth),'0px');
      assert.equal(await page.locator('.discovery-compose form').evaluate(el=>getComputedStyle(el).borderColor),'rgb(177, 155, 255)');
      await page.screenshot({path:path.join(output,'discovery-focus.png')});
    });
    async function send(value) { const before = await page.locator('.conversation-turn').count(); await question.fill(value); await page.getByRole('button', { name: 'Send', exact: true }).click(); await page.waitForFunction(count => document.querySelectorAll('.conversation-turn').length > count, before, { timeout: 15000 }); await page.waitForFunction(() => !document.querySelector('.discovery-pending')); }
    await check('Natural discovery returns real content evidence and actionable cards', async () => {
      await send('Bro, I cannot find my COA notes.');
      await page.locator('.discovery-result').first().waitFor();
      const current = page.locator('.conversation-turn').last();
      assert.match(await current.textContent(), /Computer Organization/);
      assert.match(await current.textContent(), /Matching words/);
      assert.match(await current.textContent(), /shared memory|share memory/);
      await current.getByRole('button', { name: 'Open file', exact: true }).first().click();
      for (let i = 0; i < 100 && nativeActions.at(-1) !== 'discoveryOpen'; i++) await new Promise(resolve => setTimeout(resolve, 20));
      assert.equal(nativeActions.at(-1), 'discoveryOpen');
      await page.screenshot({ path: path.join(output, 'discovery-results.png') });
      await current.getByRole('button', { name: 'Preview', exact: true }).first().click();
      await page.locator('.detail-dialog[open]').waitFor();
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('.discovery-dialog[open]').count(), 1);
    });
    await check('Follow-up, no-match and persisted conversation states', async () => {
      const previous = await page.locator('.conversation-turn').last().locator('.result-heading h3').first().textContent();
      await send('No, the other one.');
      assert.notEqual(await page.locator('.conversation-turn').last().locator('.result-heading h3').first().textContent(), previous);
      await send('Find quantum flibbertigibbet');
      assert.match(await page.locator('.conversation-turn').last().textContent(), /couldn’t find/);
      await page.getByRole('button', { name: 'Close file discovery' }).click();
      await page.getByRole('button', { name: 'Find files with SIFT', exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll('.conversation-turn').length === 3);
    });
    await check('Virtual section correction and rename are saved', async () => {
      await send('Find stored program');
      const last = page.locator('.conversation-turn').last();
      await last.getByRole('button', { name: 'Edit sections', exact: true }).first().click();
      await last.locator('.section-editor').getByLabel('Subjects', { exact: true }).fill('My architecture course');
      await last.getByRole('button', { name: 'Save sections', exact: true }).click();
      await page.getByRole('button', { name: 'Rename My architecture course', exact: true }).waitFor();
      await page.getByRole('button', { name: 'Rename My architecture course', exact: true }).click();
      await page.getByLabel('Section name', { exact: true }).fill('My COA course');
      await page.getByRole('button', { name: 'Save name', exact: true }).click();
      await page.getByRole('button', { name: 'Rename My COA course', exact: true }).waitFor();
    });
    await check('Compact chat keeps focus, readable cards, controls and model information', async () => {
      await page.setViewportSize({ width: 820, height: 600 });
      assert.equal(await page.locator('.discovery-dialog').evaluate(el => el.scrollWidth <= el.clientWidth), true);
      for (let i = 0; i < 15; i++) { await page.keyboard.press('Tab'); assert.equal(await page.evaluate(() => !!document.activeElement.closest('.discovery-dialog')), true); }
      await page.screenshot({ path: path.join(output, 'discovery-compact.png') });
      await page.locator('.model-setup summary').click();
      assert.match(await page.locator('.model-setup').textContent(), /46 MB/);
      assert.match(await page.locator('.model-setup').textContent(), /986 MB/);
      assert.match(await page.locator('.model-setup').textContent(), /Apache-2.0/);
      assert.equal(await page.getByRole('button', { name: 'Download 46 MB', exact: true }).isDisabled(), true);
      await page.locator('.model-setup summary').click();
      await page.setViewportSize({ width: 1200, height: 820 });
    });
    await check('Pasted syllabus organizes a real permitted library with visible gaps and review',async()=>{
      await page.getByRole('button',{name:'Organize syllabus',exact:true}).click();
      await page.getByRole('button',{name:'Paste syllabus text',exact:true}).click();
      await page.getByRole('textbox',{name:'Syllabus text',exact:true}).fill('Subject: COA\nUnit 1 - Fundamentals\nVon Neumann architecture; Matrix Algebra');
      await page.getByRole('button',{name:'Organize notes',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.collection-heading')?.textContent.includes('1 of 2 topics'),{},{timeout:20000}).catch(async error=>{await page.screenshot({path:path.join(output,'syllabus-error.png')});console.error('COLLECTION DEBUG',JSON.stringify(await api('GET','/collections')),await page.locator('.collections-panel').textContent(),errors,serviceErrors);throw error;});
      assert.match(await page.locator('.collection-heading').textContent(),/1 gaps/);
      assert.ok(await page.locator('.collection-content .discovery-result').count()>=1);
      await page.locator('.collection-content').screenshot({path:path.join(output,'syllabus-organizer.png')});
      await page.setViewportSize({width:820,height:600});
      assert.equal(await page.locator('.collections-panel').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
      await page.setViewportSize({width:1200,height:820});
    });
    await check('Outline editing and assignment correction survive collection refresh',async()=>{
      await page.getByRole('button',{name:'Edit outline',exact:true}).click();
      await page.getByRole('textbox',{name:'Subject',exact:true}).fill('My COA syllabus');
      await page.getByRole('button',{name:'Save and rematch',exact:true}).click();
      await page.getByRole('heading',{name:'My COA syllabus',exact:true}).waitFor();
      await page.waitForFunction(()=>document.querySelector('.collection-progress')?.textContent.includes('done'),{},{timeout:20000});
      await page.locator('.collection-content').getByRole('button',{name:'Reject',exact:true}).first().click();
      await page.waitForFunction(()=>document.querySelector('.collection-content .discovery-result')?.textContent.includes('rejected'));
      await page.getByRole('button',{name:'Find files',exact:true}).click();
    });
    await check('Removing an approved folder removes old cards and citations from chat', async () => {
      await page.getByRole('button', { name: 'Close file discovery' }).click();
      await page.locator('.folder-card').first().click({button:'right'});
      await page.getByRole('button', { name: 'Remove', exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll('.folder-card').length === 0);
      await page.getByRole('button', { name: 'Find files with SIFT', exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll('.conversation-turn').length === 4);
      assert.equal(await page.locator('.discovery-result').count(), 0);
      assert.match(await page.locator('.conversation').textContent(), /no longer available/);
      assert.equal(await page.locator('.section-link').count(), 0);
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(outside, []);
    assert.ok(!serviceErrors.includes('Traceback'), serviceErrors);
    console.log(`${passed} real-service discovery UI checks passed. No external renderer requests.`);
  } finally {
    await browser?.close();
    for (const child of processes.reverse()) { if (child.exitCode !== null) continue; if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' }); else child.kill(); }
    for (const process of processes) { if (process.exitCode === null) await new Promise(resolve => { process.once('exit', resolve); setTimeout(resolve, 5000); }); }
    // Only the exact directory created by mkdtemp above is eligible for removal.
    if (path.dirname(temporary) === os.tmpdir() && path.basename(temporary).startsWith('sift-discovery-ui-')) fs.rmSync(temporary, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
