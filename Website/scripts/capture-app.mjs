// Read the existing production renderer; capture only synthetic, browser-local fixture data.
import { readFile, stat, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import path from 'node:path';
import { chromium } from 'playwright-core';
const desktop = path.resolve(process.env.SIFT_DESKTOP_SOURCE || '../App/desktop');
const root = path.join(desktop, 'dist');
const pkg = JSON.parse(await readFile(path.join(desktop, 'package.json'), 'utf8'));
const fixtureSource = await readFile(path.join(desktop, 'tests/ui-smoke.cjs'), 'utf8');
const fixture = fixtureSource.slice(fixtureSource.indexOf('function installFixture(mode)'), fixtureSource.indexOf('module.exports'));
const mime = { '.html':'text/html', '.js':'application/javascript', '.css':'text/css', '.png':'image/png', '.svg':'image/svg+xml', '.woff2':'font/woff2' };
const server = createServer(async (req,res) => {
  try {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const target = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!target.startsWith(root + path.sep) || !(await stat(target)).isFile()) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', mime[path.extname(target)] || 'application/octet-stream');
    res.end(await readFile(target));
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({ channel:'msedge', headless:true });
try {
  const page = await browser.newPage({viewport:{width:1200,height:820},reducedMotion:'reduce'});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript({content:`(${fixture})('populated');`});
  await page.addInitScript(() => {
    const model = {name:'Optional local model',size_bytes:0,memory_estimate:'Separate setup',license:'See setup',purpose:'Local inference',url:''};
    Object.assign(window.sift, {
      discoveryStatus:async()=>({enabled:false,experimental_explanations:false,available:false,ready:{embedding:false,intent:false,vision:false},mode:'keyword',documents:{ready:3,pending:0,deferred:0},storage:'Local library · sample documents',job:null,catalog:{embedding:model,intent:model,vision:model}}),
      discoveryGroups:async()=>[], discoveryHistory:async()=>[],
    });
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.locator('.file-row').first().waitFor();
  await page.waitForLoadState('networkidle');
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:'public/assets/library-preview.png'});
  await page.getByRole('button',{name:'Find with SIFT',exact:true}).click();
  await page.getByRole('textbox',{name:'Ask SIFT to find a file'}).waitFor();
  await page.waitForLoadState('networkidle');
  if (await page.locator('.discovery-notice').count()) throw new Error(await page.locator('.discovery-notice').innerText());
  await page.screenshot({path:'public/assets/discovery-preview.png'});
  if (errors.length) throw new Error(errors.join('\n'));
  await writeFile('public/assets/app-capture.json',JSON.stringify({version:pkg.version,width:1200,height:820,synthetic:true,source:'Local production renderer; browser-local fixture, no service or user library',capturedAt:new Date().toISOString()},null,2)+'\n');
  console.log(`Captured SIFT ${pkg.version} library and discovery at 1200 × 820 with synthetic data.`);
} finally { await browser.close(); await new Promise(resolve=>server.close(resolve)); }
