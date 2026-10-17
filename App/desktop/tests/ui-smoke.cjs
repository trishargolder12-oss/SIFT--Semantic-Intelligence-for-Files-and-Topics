/* Renderer integration checks with an isolated, in-memory IPC fixture. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright-core');

const url = 'http://127.0.0.1:5173';
const output = path.resolve(__dirname, '../../.superdesign/tmp/qa');
fs.mkdirSync(output, { recursive: true });
let server;

async function saveDesignSnapshot(page, name, drawer = false) {
  let html = await page.evaluate(() => {
    const clone = document.documentElement.cloneNode(true);
    clone.querySelectorAll('script,style,link,meta[http-equiv]').forEach(element => element.remove());
    clone.querySelector('#root').classList.add('min-h-screen');
    return '<!DOCTYPE html>' + clone.outerHTML;
  });
  const image = 'https://vgbujcuwptvheqijyjbe.supabase.co/storage/v1/object/public/hmac-uploads/projects/89da2184-8714-4235-a43b-b5adb2184e99/content-assets/sift-midnight-study/midnight-study.png';
  let css = fs.readFileSync(path.resolve(__dirname, '../src/style.css'), 'utf8').replaceAll('./assets/midnight-study.png', image);
  css = css.replace(/@font-face[^}]+}/g, '');
  if (drawer) {
    css += '.detail-dialog { position:fixed; inset:0 0 0 auto; z-index:10; } .draft-backdrop {position:fixed;inset:0;z-index:9;background:rgb(8 21 46 / .72);backdrop-filter:blur(4px)}';
    html = html.replace('<dialog ', '<div class="draft-backdrop"></div><dialog ');
  }
  html = html.replace('</head>', `<script src="https://cdn.tailwindcss.com"></script><style>${css}</style></head>`);
  fs.writeFileSync(path.join(output, name + '.html'), html);
}

async function ensureServer() {
  try { if ((await fetch(url)).ok) return; } catch {}
  const vite = path.join(path.dirname(require.resolve('vite/package.json')), 'bin/vite.js');
  server = spawn(process.execPath, [vite, '--host', '127.0.0.1'], { cwd: path.resolve(__dirname, '..'), stdio: 'ignore', windowsHide: true });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Vite did not start');
}

function installFixture(mode) {
  const stamp = '2026-10-14T16:00:00Z';
  const file = (id, filename, status = 'indexed') => ({ id, root_id: 1, path: 'C:\\Study\\Semester 03\\' + filename, filename, extension: '.' + filename.split('.').pop(), size: 24600, content_hash: 'a'.repeat(64), status, error: status === 'error' ? 'Password-protected PDF' : null, title: filename, preview: 'Study notes', warning_count: 0, duplicate_of: null, indexed_at: stamp });
  const files = [file(1, 'Theory of Computation.pdf'), file(2, 'Database systems - lecture 04.docx'), file(3, 'Weekend revision checklist.txt'), file(4, 'Linear algebra exercises.pdf', 'missing')];
  const state = { folders: mode === 'empty' ? [] : [{ id: 1, path: 'C:\\Study\\Semester 03', state: 'active', last_scan_at: stamp, last_error: null }], files: mode === 'empty' ? [] : files, revision: 0, job: mode === 'empty' ? null : { id: 1, state: 'done', source: 'manual', total: 4, processed: 4, created: 4, changed: 0, moved: 0, unchanged: 0, missing: 0, failed: 0, skipped: 0, current_path: null, error: null, errors: [], started_at: stamp, finished_at: stamp } };
  window.__siftFixture = state;
  window.sift = {
    folders: async () => structuredClone(state.folders),
    documents: async (offset = 0, status) => {
      const items = state.files.filter(file => !status || file.status === status);
      return { total: items.length, library_total: state.files.length, items: structuredClone(items.slice(offset, offset + 200)) };
    },
    latestJob: async () => structuredClone(state.job),
    job: async () => structuredClone(state.job),
    scan: async () => ({ id: state.job.id }),
    chooseFolder: async () => null,
    cancelJob: async () => { state.job = { ...state.job, state: 'cancelled' }; return { cancel_requested: true }; },
    setFolderState: async (id, status) => {
      if (status === 'removed') { state.folders = []; state.files = state.files.map(file => ({ ...file, status: 'excluded' })); }
      else state.folders[0].state = status;
      return { id, state: status };
    },
    document: async id => ({ ...state.files.find(file => file.id === id), text: 'A finite state machine is a model of computation.', metadata_json: '{}', blocks: [{ position: 0, location: 'Page 1', text: 'A finite state machine is a model of computation.' }], warnings: [], path_history: [] }),
    openDocument: async () => true,
    revealDocument: async () => true,
    search: async (query, offset = 0, limit = 50) => {
      const removed = !state.folders.length;
      const revision = state.revision;
      if (query === 'slow') await new Promise(resolve => setTimeout(resolve, 600));
      const count = removed ? 0 : query === 'automata' ? 125 : 1;
      const items = Array.from({ length: count }, (_, index) => ({ id: index + 1, path: 'C:\\Study\\notes.txt', filename: query === 'slow' ? 'Old response.txt' : query === 'fresh' ? `${revision ? 'Updated' : 'Fresh'} response.txt` : `Automata notes ${String(index).padStart(3, '0')}.pdf`, title: query, snippet: 'Notes about [automata] and computation.', rank: -1, status: 'indexed', match_kind: 'content' }));
      return { items: items.slice(offset, offset + limit), total: count, offset, limit, has_more: offset + limit < count };
    },
  };
}

module.exports = { installFixture };

if (require.main === module) (async () => {
  let browser;
  let passed = 0;
  const errors = [];
  try {
    await ensureServer();
    browser = await chromium.launch({ channel: process.env.SIFT_BROWSER_CHANNEL || 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1200, height: 820 }, reducedMotion: 'reduce' });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const outsideRequests = [];
    page.on('request', request => { if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) outsideRequests.push(request.url()); });
    await page.addInitScript(installFixture, 'populated');
    await page.goto(url);
    await page.locator('.file-row').first().waitFor();
    async function check(name, work) { await work(); passed++; console.log('PASS ' + name); }
    const searchInput = page.getByLabel('Search words or filenames in your library');
    const submit = async text => { await searchInput.fill(text); await page.getByRole('button', { name: 'Search', exact: true }).click(); };

    await check('Folder names stay compact; right-click and keyboard reveal details', async () => {
      const card=page.locator('.folder-card').first();
      assert.equal((await card.textContent()).trim(),'Semester 03');
      assert.equal(await card.locator('.folder-path,.folder-status,.folder-time,.folder-actions').count(),0);
      await card.click({button:'right'});
      const details=page.getByRole('dialog',{name:'Semester 03',exact:true});
      await details.waitFor();
      assert.match(await details.textContent(),/C:\\Study\\Semester 03/);
      assert.match(await details.textContent(),/Watching for changes/);
      await page.screenshot({path:path.join(output,'folder-details.png')});
      await page.keyboard.press('Escape');
      assert.equal(await details.count(),0);
      const name=card.getByRole('button');await name.focus();await page.keyboard.press('Shift+F10');await details.waitFor();
      await details.getByRole('button',{name:'Pause',exact:true}).click();
      await page.waitForFunction(()=>window.__siftFixture.folders[0].state==='paused');
      await name.click();await details.getByRole('button',{name:'Resume',exact:true}).click();
      await page.waitForFunction(()=>window.__siftFixture.folders[0].state==='active');
    });
    await check('Midnight palette, local assets, and populated layout', async () => {
      assert.equal(await page.locator('.file-row').count(), 4);
      assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()), '#08152E');
      assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--pink').trim()), '#FF91BA');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({ path: path.join(output, 'workspace-1200.png') });
      await saveDesignSnapshot(page, 'workspace');
      assert.deepEqual(outsideRequests, []);
    });
    await check('Weather toggle persists and respects system and in-app reduced motion', async () => {
      const toggle = page.getByRole('switch', { name: 'Leaves, rain and wind effects' });
      assert.equal(await toggle.isDisabled(), true);
      assert.equal(await page.locator('.weather-layer .leaf').count(), 0);
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await page.waitForFunction(() => document.querySelector('[role=switch]').getAttribute('aria-checked') === 'true');
      assert.equal(await page.locator('.weather-layer .leaf').count(), 6);
      await toggle.focus(); await page.keyboard.press('Space');
      assert.equal(await toggle.getAttribute('aria-checked'), 'false');
      assert.equal(await page.locator('.weather-layer i').count(), 0);
      await page.reload();
      await page.locator('.file-row').first().waitFor();
      assert.equal(await toggle.getAttribute('aria-checked'), 'false');
      await toggle.click();
      assert.equal(await page.locator('.weather-layer .raindrop').count(), 16);
      await page.getByRole('button', { name: 'Reduce motion', exact: true }).click();
      assert.equal(await toggle.isDisabled(), true);
      assert.equal(await page.locator('.weather-layer i').count(), 0);
      await page.reload(); await page.locator('.file-row').first().waitFor();
      assert.equal(await toggle.isDisabled(), true);
      await page.getByRole('button', { name: 'Reduce motion', exact: true }).click();
      assert.equal(await toggle.getAttribute('aria-checked'), 'true');
      await page.locator('.workspace').evaluate(el => el.scrollTop = el.scrollHeight);
      await page.waitForFunction(() => document.querySelector('.app-shell').style.getPropertyValue('--room-presence') === '1');
      assert.equal(await toggle.isVisible(), true);
      await page.screenshot({ path: path.join(output, 'workspace-scrolled.png') });
      await page.getByRole('button', { name: 'Back to top' }).click();
      await page.waitForTimeout(80);
      const stopped = await page.locator('.workspace').evaluate(el => { el.dispatchEvent(new Event('wheel')); return el.scrollTop; });
      await page.waitForTimeout(150);
      assert.equal(await page.locator('.workspace').evaluate(el => el.scrollTop), stopped);
      await page.locator('.workspace').evaluate(el => el.scrollTop = el.scrollHeight);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.waitForFunction(() => document.querySelector('[role=switch]').disabled);
      await page.getByRole('button', { name: 'Back to top' }).click();
      await page.waitForFunction(() => document.querySelector('.workspace').scrollTop === 0);
      assert.deepEqual(outsideRequests, []);
    });
    await check('Minimum window has no horizontal overflow', async () => {
      await page.setViewportSize({ width: 820, height: 600 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.equal(await page.locator('.workspace').evaluate(element => element.scrollWidth <= element.clientWidth), true);
      await page.screenshot({ path: path.join(output, 'workspace-820.png') });
      await page.getByRole('button', { name: 'Show approved folders' }).click();
      await page.locator('.folder-dialog[open]').waitFor();
      await page.locator('.folder-dialog .folder-card').first().click({button:'right'});
      await page.locator('.folder-details-dialog[open]').waitFor();
      for(let i=0;i<9;i++){await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>!!document.activeElement.closest('.folder-details-dialog')),true);}
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('.folder-dialog[open]').count(),1);
      await page.getByRole('button',{name:'Close folders',exact:true}).focus();
      for (let i = 0; i < 9; i++) {
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(() => !!document.activeElement.closest('.folder-dialog')), true);
      }
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('.folder-dialog[open]'));
      assert.equal(await page.getByRole('button', { name: 'Show approved folders' }).evaluate(el => el === document.activeElement), true);

      await page.setViewportSize({ width: 1200, height: 820 });
    });
    await check('Document drawer traps focus, closes with Escape, and restores focus', async () => {
      await page.locator('.file-row').first().click();
      await page.locator('dialog[open]').waitFor();
      for (let i = 0; i < 8; i++) {
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(() => !!document.activeElement.closest('dialog')), true);
      }
      await page.screenshot({ path: path.join(output, 'document-drawer.png') });
      await saveDesignSnapshot(page, 'document-drawer', true);
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('dialog'));
      assert.equal(await page.evaluate(() => document.activeElement.classList.contains('file-row')), true);
    });
    await check('Status filters keep the global document count accurate', async () => {
      await page.getByLabel('Show', { exact: true }).selectOption('missing');
      await page.waitForFunction(() => document.querySelectorAll('.file-row').length === 1);
      assert.equal(await page.locator('.nav-count').innerText(), '4');
      assert.equal((await page.locator('.file-row .status-badge').innerText()).trim(), 'Missing');
      await page.getByLabel('Show', { exact: true }).selectOption('');
      await page.waitForFunction(() => document.querySelectorAll('.file-row').length === 4);
    });
    await check('Keyboard search shortcut and complete result pagination', async () => {
      await page.keyboard.press('Control+k');
      assert.equal(await searchInput.evaluate(element => element === document.activeElement), true);
      await submit('automata');
      await page.getByText('1–50 of 125 matches', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      await page.getByText('51–100 of 125 matches', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      await page.getByText('101–125 of 125 matches', { exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Next', exact: true }).isDisabled(), true);
    });
    await check('An older search response cannot overwrite a newer query', async () => {
      await submit('slow');
      await submit('fresh');
      await page.getByText('Fresh response.txt', { exact: true }).waitFor();
      await page.waitForTimeout(750);
      assert.equal(await page.getByText('Old response.txt', { exact: true }).count(), 0);
      assert.equal(await page.getByText('Fresh response.txt', { exact: true }).count(), 1);
    });
    await check('Clearing a pending query does not reopen old results', async () => {
      await submit('slow');
      await page.getByRole('button', { name: 'Clear search' }).click();
      await page.waitForTimeout(750);
      assert.equal(await page.getByRole('heading', { name: 'Your documents', exact: true }).count(), 1);
      assert.equal(await page.getByText('Old response.txt', { exact: true }).count(), 0);
    });
    await check('Scan completion refreshes the active query', async () => {
      await submit('fresh');
      await page.getByText('Fresh response.txt', { exact: true }).waitFor();
      await page.evaluate(() => { window.__siftFixture.revision = 1; window.__siftFixture.job = { ...window.__siftFixture.job, id: 2 }; });
      await page.getByText('Updated response.txt', { exact: true }).waitFor({ timeout: 7000 });
      assert.equal(await searchInput.inputValue(), 'fresh');
    });
    await check('Folder removal refreshes results and discards pending older responses', async () => {
      await submit('slow');
      await page.locator('.folder-card').first().click({button:'right'});
      await page.getByRole('button', { name: 'Remove', exact: true }).click();
      await page.getByRole('heading', { name: 'Your documents', exact: true }).waitFor();
      await page.waitForTimeout(750);
      assert.equal(await page.getByText('Old response.txt', { exact: true }).count(), 0);
      await page.waitForFunction(() => [...document.querySelectorAll('.file-row .status-badge')].every(el => el.textContent.trim() === 'Excluded'));
      assert.equal(await searchInput.inputValue(), '');
    });
    await check('Empty onboarding and scanning states render', async () => {
      const emptyPage = await context.newPage();
      await emptyPage.addInitScript(installFixture, 'empty');
      await emptyPage.goto(url);
      await emptyPage.getByRole('button', { name: 'Add your first folder' }).waitFor();
      await emptyPage.screenshot({ path: path.join(output, 'empty-library.png') });
      await saveDesignSnapshot(emptyPage, 'empty-library');
      await emptyPage.evaluate(() => { window.__siftFixture.job = { id: 3, state: 'running', source: 'manual', total: 100, processed: 26, created: 26, changed: 0, moved: 0, unchanged: 0, missing: 0, failed: 0, skipped: 0, current_path: 'C:\\Study\\notes.pdf', error: null, errors: [], started_at: '2026-10-14T16:00:00Z', finished_at: null }; });
      await emptyPage.getByRole('button', { name: 'Cancel scan', exact: true }).waitFor({ timeout: 7000 });
      await emptyPage.screenshot({ path: path.join(output, 'scan-progress.png') });
      await emptyPage.getByRole('button', { name: 'Cancel scan', exact: true }).click();
      await emptyPage.getByRole('heading', { name: 'Scan cancelled', exact: true }).waitFor();
      await emptyPage.close();
    });
    assert.deepEqual(errors, [], 'Renderer exceptions');
    console.log(`${passed} renderer checks passed. Screenshots: ${output}`);
  } finally {
    await browser?.close();
    server?.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
