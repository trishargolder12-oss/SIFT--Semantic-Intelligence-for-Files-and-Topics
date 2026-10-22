import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, stat, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright-core';
import { publicOrigin, seoHead, sitemapXml } from '../scripts/seo.mjs';

const release = JSON.parse(await readFile('public/release.json','utf8'));
const root = path.resolve('dist');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.webp': 'image/webp', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.json': 'application/json', '.txt': 'text/plain' };
const server = createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const target = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!target.startsWith(root + path.sep) || !(await stat(target)).isFile()) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', mime[path.extname(target)] || 'application/octet-stream');
    res.end(await readFile(target));
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ channel: process.env.SIFT_BROWSER_CHANNEL || 'msedge', headless: true, args: ['--disable-gpu'] });
const results = [];
const check = (label, condition) => { assert.ok(condition, label); results.push(label); console.log(`PASS ${label}`); };
try {
 await mkdir('screenshots/revision-6', {recursive:true});
 const errors=[], external=[];
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`);});page.on('request',r=>{if(new URL(r.url()).origin!==base)external.push(r.url());});
 const routes=[['home','/','Home'],['features','/features.html','Features'],['how-it-works','/how-it-works.html','How It Works'],['preview','/preview.html','Preview'],['download','/download.html','Download']];
 for(const [name,url,label]of routes){
  await page.goto(base+url);await page.waitForLoadState('networkidle');
  check(`${label}: direct static page, heading and active navigation`,await page.locator('h1').count()===1&&await page.getByRole('main').count()===1&&await page.getByRole('navigation').getByRole('link',{name:label,exact:true}).getAttribute('aria-current')==='page');
  check(`${label}: crawlable metadata and structured data`,await page.title().then(title=>title.includes('SIFT'))&&await page.locator('meta[name="description"]').getAttribute('content').then(value=>value.length>100)&&await page.locator('script[type="application/ld+json"]').evaluate(el=>JSON.parse(el.textContent)['@graph'].some(node=>node['@type']==='WebPage')));
  check(`${label}: creator link is correct`,await page.locator('.creator-link').getAttribute('href')==='https://www.instagram.com/tris_haar/');
  if(name!=='home'){
   check(`${label}: separate local PNG and useful writeup`,await page.locator('.page-backdrop img').evaluate(img=>img.complete&&img.naturalWidth>0&&img.src.endsWith('.png'))&&await page.locator('.editorial-chapter').count()===3);
  } else check('Home reuses its room artwork behind lower content',await page.locator('.home-scroll-backdrop').count()===1&&await page.locator('.page-backdrop').count()===0);
  await page.reload();await page.waitForLoadState('networkidle');
  check(`${label}: refresh preserves page`,await page.getByRole('navigation').getByRole('link',{name:label,exact:true}).getAttribute('aria-current')==='page');
  for(const width of [1440,1024,768,390]){
   await page.setViewportSize({width,height:width===390?844:1000});
   check(`${label}: no overflow at ${width}px`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:`screenshots/revision-6/${name}-${width}.png`,fullPage:true});
   const backdrop=page.locator(name==='home'?'.home-scroll-backdrop':'.page-backdrop');
   const before=await backdrop.boundingBox();
   await page.evaluate(()=>scrollTo({top:document.documentElement.scrollHeight-innerHeight,behavior:'instant'}));
   check(`${label}: artwork stays in the viewport after scrolling at ${width}px`,await backdrop.evaluate(el=>getComputedStyle(el).position==='fixed')&&await backdrop.boundingBox().then(after=>Math.abs(after.y-before.y)<1&&after.height===before.height)&&await page.evaluate(()=>scrollY>100));
   if(name!=='home')check(`${label}: illustration intersects the lower viewport at ${width}px`,await backdrop.locator('img').evaluate(el=>{const r=el.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth;}));
   if(width===1440||width===390)await page.screenshot({path:`screenshots/revision-6/${name}-${width}-scrolled.png`});
   await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
  }
  await page.setViewportSize({width:1440,height:1000});
 }
 const phone=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
 phone.on('pageerror',e=>errors.push(e.message));
 for(const width of [320,360,375,390,430,600,601,767]){
  await phone.setViewportSize({width,height:844});
  for(const [name,url,label]of routes){
   await phone.goto(base+url);await phone.waitForLoadState('networkidle');
   const geometry=await phone.evaluate(()=>{
    const bounds=el=>el.getBoundingClientRect();
    const header=[...document.querySelectorAll('.header>.brand,.header-actions,.menu-toggle')].map(bounds);
    return {
     fits:document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('h1,h2,h3,p,.button,.footer-links,.footer-community')].filter(el=>el.getClientRects().length).every(el=>{const r=bounds(el);return r.left>=-1&&r.right<=innerWidth+1;}),
     centered:[...document.querySelectorAll('.section,.hero-copy,.feature-strip')].every(el=>{const r=bounds(el);return Math.abs(r.left+r.width/2-innerWidth/2)<1;}),
     headerFits:header.every(r=>r.left>=19&&r.right<=innerWidth-19)&&header.slice(1).every((r,i)=>r.left-header[i].right>=7),
     headingCentered:getComputedStyle(document.querySelector('h1').parentElement).textAlign==='center',
     footerCentered:getComputedStyle(document.querySelector('.footer-main')).alignItems==='center'&&getComputedStyle(document.querySelector('.footer-bottom')).justifyItems==='center'
    };
   });
   check(`${label}: ${width}px touch layout has centered containers, headings and fitted content`,geometry.fits&&geometry.centered&&geometry.headingCentered&&geometry.footerCentered);
   check(`${label}: ${width}px header controls stay separated inside equal gutters`,geometry.headerFits);
   if(name==='home'){
    check(`Home: ${width}px artwork follows wrapped text without overlap`,await phone.evaluate(()=>document.querySelector('.hero-scene').getBoundingClientRect().top>=document.querySelector('.hero-copy').getBoundingClientRect().bottom));
    await phone.getByRole('button',{name:'Grab us a coffee'}).click();
    check(`Home: ${width}px coffee popup is centered and contained`,await phone.locator('.coffee-popup').evaluate(el=>{const r=el.getBoundingClientRect();return Math.abs(r.left+r.width/2-innerWidth/2)<1&&r.left>=16&&r.right<=innerWidth-16;}));
    await phone.getByRole('button',{name:'Close coffee popup'}).click();
   }
   if(name==='features')check(`Features: ${width}px privacy illustration stays contained`,await phone.locator('.privacy-art .privacy-orbit,.privacy-art .orbit-file').evaluateAll(els=>els.every(el=>{const r=el.getBoundingClientRect();return r.left>=15&&r.right<=innerWidth-15;})));
   await phone.getByRole('button',{name:'Open navigation'}).click();
   check(`${label}: ${width}px open menu stays inside the phone`,await phone.locator('.navigation').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=19&&r.right<=innerWidth-19&&r.bottom<=innerHeight;}));
   await phone.keyboard.press('Escape');
   if([320,430,601].includes(width)){
    await phone.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
    await phone.screenshot({path:`screenshots/revision-6/${name}-${width}-phone.png`});
    await phone.locator('.footer').scrollIntoViewIfNeeded();
    await phone.screenshot({path:`screenshots/revision-6/${name}-${width}-phone-footer.png`});
   }
  }
 }
 await phone.setViewportSize({width:740,height:360});await phone.goto(base);await phone.waitForLoadState('networkidle');
 await phone.getByRole('button',{name:'Open navigation'}).click();
 check('Landscape phone navigation stays inside the viewport',await phone.locator('.navigation').evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
 await phone.keyboard.press('Escape');await phone.getByRole('button',{name:'Grab us a coffee'}).click();
 check('Landscape coffee popup stays inside the short viewport',await phone.locator('.coffee-popup').evaluate(el=>{const r=el.getBoundingClientRect();return r.top>=16&&r.bottom<=innerHeight-16;}));
 await phone.close();
 await page.goto(base);await page.waitForLoadState('networkidle');
 check('Home sample reviews are explicitly illustrative',await page.locator('.review-card').count()===3&&(await page.locator('.reviews-note').innerText()).includes('not submitted customer reviews'));
 check('Sample review cards use Amanda, Sonia and Alex with shared fictional-name disclosure',JSON.stringify(await page.locator('.review-label').allTextContents())===JSON.stringify(['Amanda','Sonia','Alex'])&&(await page.locator('.reviews-note').innerText()).includes('fictional names')&&!(await page.locator('.review-grid').innerText()).includes('ILLUSTRATIVE SCENARIO'));
 check('Home contains no long instructions, FAQ or fake application UI',await page.locator('.steps,.faq-section,.features-grid,.demo-window,.room-screen').count()===0);
 check('Laptop uses actual production screenshot',await page.locator('.actual-app-screen').evaluate(img=>img.complete&&img.naturalWidth===1200&&img.naturalHeight===820&&img.getAttribute('src')==='/assets/library-preview.png'));
 check('Screenshot corner projection matches measured artwork',await page.locator('.actual-app-screen').evaluate(img=>{const m=new DOMMatrix(getComputedStyle(img).transform);return [[0,0,942,221],[1200,0,1542,193],[1200,820,1545,577],[0,820,919,556]].every(([x,y,tx,ty])=>{const p=m.transformPoint(new DOMPoint(x,y));return Math.abs(p.x/p.w-tx)<.5&&Math.abs(p.y/p.w-ty)<.5;});}));
 await page.setViewportSize({width:1055,height:581});await page.screenshot({path:'screenshots/revision-6/home-1055.png',fullPage:true});
 await page.getByRole('link',{name:'Explore Demo',exact:true}).click();await page.waitForLoadState('networkidle');
 check('Explore Demo opens actual app gallery',new URL(page.url()).pathname==='/preview.html'&&await page.locator('.actual-preview-frame>img').getAttribute('src')==='/assets/library-preview.png');
 await page.getByRole('button',{name:/Find with SIFT/}).click();await page.waitForFunction(()=>document.querySelector('.actual-preview-frame>img')?.complete);
 check('Gallery shows the 0.4.3 local discovery capture and build disclosure',await page.locator('.actual-preview-frame>img').getAttribute('src')==='/assets/discovery-preview.png'&&(await page.locator('.actual-preview-caption').innerText()).includes('0.4.3 local build'));
 await page.getByRole('button',{name:'Expand app screenshot'}).click();await page.keyboard.press('Tab');
 check('Screenshot dialog contains keyboard focus',await page.getByRole('dialog').isVisible()&&await page.evaluate(()=>!!document.activeElement.closest('dialog')));
 await page.keyboard.press('Escape');check('Escape restores screenshot button focus',await page.getByRole('dialog').count()===0&&await page.evaluate(()=>document.activeElement.getAttribute('aria-label')==='Expand app screenshot'));
 await page.goto(base+'/download.html');await page.waitForLoadState('networkidle');
 check('Download identifies the published beta and exact hosted artifact',await page.getByRole('link',{name:`Download beta ${release.version}`,exact:true}).getAttribute('href')===release.downloadUrl);
 check('Public checksum and version match the configured release',await page.locator('.checksum code').innerText()===release.sha256&&(await page.locator('.release-status').innerText()).includes(release.version));
 check('The latest local build has its own non-download metadata',await page.locator('.local-release code').innerText()===release.candidate.sha256&&(await page.locator('.local-release').innerText()).includes(release.candidate.sizeBytes.toLocaleString('en-US'))&&(await page.locator('.local-release-status').innerText()).includes('awaiting publication'));
 check('No 0.4.3 download is invented',await page.locator('a[href*="/v0.4.3/"],.local-release a[href$=".exe"]').count()===0);
 check('Explanation limitations are visible on the download page',(await page.locator('.local-release').innerText()).includes('off by default')&&(await page.locator('.local-release').innerText()).includes('can be incorrect'));
 const notes = await (await page.request.get(base+'/release-notes.html')).text();
 check('Release notes render both distinct versions, hashes and the correct download destination',notes.includes(release.sha256)&&notes.includes(release.candidate.sha256)&&notes.includes('id="public-artifact"')&&notes.includes('id="local-artifact"')&&notes.includes('href="/download.html"')&&!notes.includes('0.1.2'));
 await page.goto(base+'/features.html');await page.waitForLoadState('networkidle');
 check('Features include discovery, collections and explicit optional setup',await page.locator('.feature-card').count()===8&&(await page.locator('main').innerText()).includes('Syllabus collections')&&(await page.locator('main').innerText()).includes('separate OCR pack'));
 await page.goto(base+'/download.html');await page.waitForLoadState('networkidle');
 await page.locator('#faq summary').first().click();check('Download FAQ expands',await page.locator('#faq details').first().getAttribute('open')!==null);
 for(const [name,title]of [['Privacy','Privacy & local processing'],['Terms','Website & preview terms'],['Asset licenses','Fonts & artwork']]){await page.locator('.footer-bottom').getByRole('link',{name,exact:true}).click();check(`${name} dialog works`,await page.getByRole('dialog',{name:title,exact:true}).isVisible());await page.keyboard.press('Escape');}
 await page.setViewportSize({width:390,height:844});await page.goto(base);await page.waitForLoadState('networkidle');
 await page.getByRole('button',{name:'Open navigation'}).click();check('Mobile menu focuses first destination',await page.evaluate(()=>document.activeElement.closest('nav')!==null));await page.keyboard.press('Escape');check('Mobile Escape closes menu and restores toggle',await page.locator('nav').isHidden()&&await page.evaluate(()=>document.activeElement.classList.contains('menu-toggle')));
 await page.getByRole('button',{name:'Open navigation'}).click();await page.getByRole('navigation').getByRole('link',{name:'Features',exact:true}).click();await page.waitForLoadState('networkidle');check('Mobile navigation opens separate Features page',new URL(page.url()).pathname==='/features.html'&&await page.locator('nav').isHidden());
 check('Reduced motion unmounts particles',await page.locator('.weather-layer i').count()===0&&await page.getByRole('button',{name:'Ambient effects'}).isDisabled());
 await page.locator('.footer').scrollIntoViewIfNeeded();await page.waitForFunction(()=>!!document.querySelector('.back-to-top'));await page.getByRole('button',{name:'Back to top'}).click();check('Reduced-motion back-to-top restores heading focus',await page.evaluate(()=>scrollY===0&&document.activeElement.tagName==='H1'));
 const noJs=await browser.newPage({javaScriptEnabled:false,viewport:{width:390,height:844}});
 for(const [name,url,label]of routes){await noJs.goto(base+url);check(`${label}: no-JavaScript content and navigation`,await noJs.locator('h1').isVisible()&&await noJs.getByRole('navigation').isVisible());}
 await noJs.locator('#faq summary').first().click();check('FAQ works without JavaScript',await noJs.locator('#faq details').first().getAttribute('open')!==null);await noJs.close();
 const motion=await browser.newPage({viewport:{width:1440,height:1000}});
 await motion.addInitScript(()=>{window.testHidden=false;Object.defineProperty(document,'hidden',{get:()=>window.testHidden,configurable:true});});
 await motion.goto(base);await motion.waitForFunction(()=>document.querySelectorAll('.weather-layer i').length===25);
 check('App-style leaves, rain and wind are enabled',await motion.locator('.leaf').count()===6&&await motion.locator('.raindrop').count()===16&&await motion.locator('.wind-trail').count()===3);
 check('Particles cannot capture pointer input',await motion.locator('.weather-layer').evaluate(el=>getComputedStyle(el).pointerEvents==='none'));
 await motion.evaluate(()=>{window.testHidden=true;document.dispatchEvent(new Event('visibilitychange'));});await motion.waitForFunction(()=>document.querySelectorAll('.weather-layer i').length===0);check('Hidden-page visibility handler removes particles',await motion.locator('.weather-layer i').count()===0);
 await motion.evaluate(()=>{window.testHidden=false;document.dispatchEvent(new Event('visibilitychange'));});await motion.waitForFunction(()=>document.querySelectorAll('.weather-layer i').length===25);
 await motion.getByRole('button',{name:'Ambient effects'}).click();check('Effects switch removes particles',await motion.locator('.weather-layer i').count()===0);await motion.reload();await motion.waitForLoadState('networkidle');check('Effects choice persists across page loads',await motion.getByRole('button',{name:'Ambient effects'}).getAttribute('aria-pressed')==='false'&&await motion.locator('.weather-layer i').count()===0);
 await motion.getByRole('button',{name:'Ambient effects'}).click();await motion.emulateMedia({reducedMotion:'reduce'});await motion.waitForFunction(()=>document.querySelectorAll('.weather-layer i').length===0);check('Changing system reduced motion stops effects live',await motion.locator('.weather-layer i').count()===0);await motion.close();

 const coffeeContext=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
 const coffeePage=await coffeeContext.newPage();await coffeePage.clock.install();
 await coffeePage.goto(base);await coffeePage.locator('html.motion-ready').waitFor();
 await coffeePage.clock.fastForward(16000);check('Coffee invitation waits before appearing',await coffeePage.locator('.coffee-popup').count()===0);
 await coffeePage.clock.fastForward(2500);await coffeePage.locator('.coffee-popup').waitFor();
 check('Home automatically shows a small non-modal coffee invitation',await coffeePage.locator('.coffee-popup').getAttribute('aria-modal')==='false'&&await coffeePage.evaluate(()=>!document.activeElement.closest('.coffee-popup')));
 check('Without a payment link the popup links honestly to Instagram',await coffeePage.getByRole('link',{name:'Say hello on Instagram'}).getAttribute('href')==='https://www.instagram.com/tris_haar/'&&await coffeePage.getByRole('link',{name:'Support SIFT'}).count()===0);
 await coffeePage.screenshot({path:'screenshots/revision-6/coffee-mobile.png'});
 await coffeePage.getByRole('button',{name:'Close coffee popup'}).click();
 await coffeePage.reload();await coffeePage.locator('html.motion-ready').waitFor();await coffeePage.clock.fastForward(21000);
 check('Coffee invitation does not repeat after reload in the same visit',await coffeePage.locator('.coffee-popup').count()===0);
 await coffeePage.goto(base+'/features.html');await coffeePage.locator('html.motion-ready').waitFor();await coffeePage.clock.fastForward(21000);
 check('No automatic coffee popup on inner pages',await coffeePage.locator('.coffee-popup').count()===0);
 await coffeePage.getByRole('button',{name:'Grab us a coffee'}).click();await coffeePage.locator('.coffee-popup').waitFor();await coffeePage.clock.runFor(100);
 check('Footer support button reopens invitation with keyboard focus',await coffeePage.locator('.coffee-popup').isVisible()&&await coffeePage.evaluate(()=>document.activeElement.getAttribute('aria-label')==='Close coffee popup'));
 await coffeePage.keyboard.press('Escape');check('Coffee Escape restores footer trigger focus',await coffeePage.locator('.coffee-popup').count()===0&&await coffeePage.evaluate(()=>document.activeElement.classList.contains('coffee-trigger')));
 await coffeeContext.close();
 const fresh=await browser.newContext({reducedMotion:'reduce'});const freshPage=await fresh.newPage();await freshPage.clock.install();await freshPage.goto(base+'/features.html');await freshPage.locator('html.motion-ready').waitFor();await freshPage.clock.fastForward(21000);check('Fresh visits also keep inner pages free of automatic popups',await freshPage.locator('.coffee-popup').count()===0);await freshPage.goto(base);await freshPage.locator('html.motion-ready').waitFor();await freshPage.clock.fastForward(21000);check('A new visit can show the Home invitation once',await freshPage.locator('.coffee-popup').isVisible());await fresh.close();
 const raw=await (await page.request.get(base+'/features.html')).text();check('Editorial text exists before JavaScript executes',raw.includes('A library is a map')&&raw.includes('separate local index'));
 check('Robots allows public crawling without fake domain data',(await (await page.request.get(base+'/robots.txt')).text()).includes('Allow: /')&&!raw.includes('https://example.com'));
 const seo=seoHead({page:'features',info:{href:'/features.html',title:'SIFT features',description:'Local study library',label:'Features'},site:{creatorName:'tris_haar',creatorUrl:'https://www.instagram.com/tris_haar/'},origin:publicOrigin('https://sift.test')});
 check('Configured hosting produces one canonical and matching structured URLs',(seo.match(/rel="canonical"/g)||[]).length===1&&seo.includes('https://sift.test/features.html')&&seo.includes('BreadcrumbList'));
 check('Sitemap uses the configured origin and correct paths',sitemapXml('https://sift.test',['/','/features.html']).includes('<loc>https://sift.test/features.html</loc>'));
 let rejected=false;try{publicOrigin('http://localhost:4175')}catch{rejected=true}check('SEO configuration rejects local or insecure production origins',rejected);
 for(const url of ['/release-notes.html','/privacy.html','/terms.html','/licenses.html','/licenses/sora-OFL.txt','/licenses/manrope-OFL.txt'])check(`Static destination ${url}`,(await page.request.get(base+url)).status()===200);
 check('No hydration, browser or asset errors',errors.length===0);check('All runtime assets remain local',external.length===0);
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Calcutta',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(part=>[part.type,part.value]));
 const filename=`test_log_${parts.year}-${parts.month}-${parts.day}_${parts.hour}-${parts.minute}-${parts.second}.md`;
 await mkdir('../test_logs',{recursive:true});
 await writeFile(path.join('../test_logs',filename),`# SIFT website revision 6 browser verification\n\n${results.length} checks passed. Production static pages tested with installed ${process.env.SIFT_BROWSER_CHANNEL || 'msedge'} headless. Screenshot evidence: website/screenshots/revision-6/. No application/backend/updater changes; no real installer download or installed upgrade exercised.\n\n`+results.map(label=>`- PASS: ${label}`).join('\n')+`\n\nBrowser errors: ${JSON.stringify(errors)}\nExternal runtime requests: ${JSON.stringify(external)}\n`);
 console.log(`${results.length} checks passed. Report: test_logs/${filename}`);
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
