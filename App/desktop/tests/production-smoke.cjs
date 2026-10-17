/* Check the built renderer, rather than Vite's development transform. */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright-core');
const { installFixture } = require('./ui-smoke.cjs');

(async () => {
  const root = path.resolve(__dirname, '../dist');
  const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
  const server = http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const target = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!target.startsWith(root + path.sep) || !fs.existsSync(target) || !fs.statSync(target).isFile()) { response.writeHead(404).end(); return; }
    response.setHeader('Content-Type', mime[path.extname(target)] || 'application/octet-stream');
    fs.createReadStream(target).pipe(response);
  });
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch({ channel: process.env.SIFT_BROWSER_CHANNEL || 'msedge', headless: true });
    const page = await browser.newPage({ viewport: { width: 1200, height: 820 }, reducedMotion: 'reduce' });
    const errors = [];
    const outsideRequests = [];
    page.on('request', request => { if (!['127.0.0.1', 'localhost'].includes(new URL(request.url()).hostname)) outsideRequests.push(request.url()); });
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
    await page.addInitScript(installFixture, 'populated');
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.locator('.file-row').first().waitFor();
    await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('.file-row').count(), 4);
    assert.deepEqual(errors, []);
    assert.deepEqual(outsideRequests, [], 'Production must not request external resources');
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.evaluate(() => document.fonts.check('500 15px Manrope') && document.fonts.check('700 42px Sora')), true);
    assert.equal(await page.getByRole('heading', { name: 'Stop Searching. Start Studying.' }).count(), 1);
    assert.match(await page.locator('.hero-art').evaluate(element => getComputedStyle(element).backgroundImage), /midnight-study/);
    const output = path.resolve(__dirname, '../../docs/design/previews');
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: path.join(output, 'library-production.png') });
    console.log('PASS production renderer: document list, local artwork, and no page/asset errors');
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
