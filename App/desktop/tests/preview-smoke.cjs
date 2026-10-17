/* Deliberately controlled out-of-order page responses against the real React view. */
const assert=require('node:assert/strict');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright-core');
const {installFixture}=require('./ui-smoke.cjs');
(async()=>{
  const vite=path.join(path.dirname(require.resolve('vite/package.json')),'bin/vite.js');
  const server=spawn(process.execPath,[vite,'--host','127.0.0.1','--port','5193','--strictPort'],{cwd:path.resolve(__dirname,'..'),windowsHide:true,stdio:'ignore'});
  let browser;
  try {
    const deadline=Date.now()+15000;
    while(true){try{if((await fetch('http://127.0.0.1:5193')).ok)break;}catch{}if(Date.now()>deadline)throw Error('Preview test server deadline');await new Promise(r=>setTimeout(r,100));}
    browser=await chromium.launch({channel:process.env.SIFT_BROWSER_CHANNEL||'msedge',headless:true});
    const page=await browser.newPage({reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(installFixture,'populated');
    await page.addInitScript(()=>{
      localStorage.setItem('sift.collection','collection-a');
      const state=window.__previewTest={pending:[],version:'a'.repeat(64)};
      const models={enabled:false,available:false,ready:{},catalog:{embedding:{name:'MiniLM',size_bytes:46000000},intent:{name:'Qwen',size_bytes:986000000}},mode:'keyword',documents:{},job:null};
      const evidence=()=>({chunk_id:1,source:'file:1',version:state.version,page:1,location:'Page 1',text:'Current source evidence',origin:'native transcription',bbox:null,ocr_confidence:null,uncertain:false,relevance:{}});
      const topics=[{id:'topic-a',name:'Memory',original:'Memory',aliases:[],source:{},subtopics:[]},{id:'topic-b',name:'Processor',original:'Processor',aliases:[],source:{},subtopics:[]}];
      Object.assign(window.sift,{
        discoveryStatus:async()=>models,discoveryGroups:async()=>[],discoveryHistory:async()=>[],
        collections:async()=>[{id:'collection-a',subject:'Course A',state:'ready',revision:1},{id:'collection-b',subject:'Course B',state:'ready',revision:1}],
        collectionGetDestination:async()=>null,collectionVision:async()=>({models,ocr_ready:false}),
        collectionDetail:async(id,topic)=>{state.returned=state.version;return ({id,subject:id==='collection-a'?'Course A':'Course B',revision:1,state:'ready',source_version:state.version,outline:{subject:'Course',units:[{id:'unit',name:'Fundamentals',topics}],issues:[]},coverage:topics.map(t=>({id:t.id,name:t.name,unit:'Fundamentals',matches:1,review:0})),issues:[],topics_with_material:2,gaps:0,items:[{topic_id:topic||'topic-a',file_id:1,content_hash:state.version,filename:'notes.pdf',path:'C:/Study/notes.pdf',classification:'substantive',decision:'auto',reason:'Evidence',evidence:[evidence()]}],total:1,offset:0,has_more:false,job:null,export:null});},
        collectionPage:()=>new Promise((resolve,reject)=>state.pending.push({resolve,reject})),
      });
      state.finish=(failure=false)=>{const next=state.pending.shift();if(failure)next.reject(Error('Obsolete preview failure'));else next.resolve({image:'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==',dimensions:[1,1]});};
    });
    await page.goto('http://127.0.0.1:5193');await page.getByRole('button',{name:'Find files with SIFT',exact:true}).click();await page.getByRole('button',{name:'Organize syllabus',exact:true}).click();
    const inspect=page.getByRole('button',{name:'Inspect page & evidence',exact:true});
    async function pending(){await inspect.first().click();await page.waitForFunction(()=>window.__previewTest.pending.length===1);}
    async function finish(failure=false){await page.evaluate(value=>window.__previewTest.finish(value),failure);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));assert.equal(await page.locator('.collection-preview').count(),0);assert.equal(await page.getByText('Obsolete preview failure',{exact:false}).count(),0);}
    await pending();await page.locator('.collection-tree').getByRole('button',{name:/Processor/}).click();await finish(true);console.log('PASS late failure after topic change');
    await pending();await page.locator('.collection-tree').getByRole('button',{name:/Course B/}).click();await page.getByRole('heading',{name:'Course B',exact:true}).waitFor();await finish();console.log('PASS late response after collection change');
    await pending();await page.evaluate(()=>{window.dispatchEvent(new Event('sift-permissions-changing'));});await finish();await page.evaluate(()=>window.dispatchEvent(new Event('sift-permissions-settled')));console.log('PASS late response after permission change');
    await pending();await page.evaluate(()=>{window.__previewTest.version='b'.repeat(64);});await page.waitForFunction(()=>window.__previewTest.returned==='b'.repeat(64));await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await finish();console.log('PASS late response after source version change');
    await pending();await page.evaluate(()=>window.__previewTest.finish());await page.getByRole('region',{name:'Source page preview'}).waitFor();await page.getByRole('button',{name:'Close page preview',exact:true}).click();assert.equal(await page.locator('.collection-preview').count(),0);console.log('PASS current response and close');
    assert.deepEqual(errors,[]);console.log('5 preview race checks passed');
  } finally {await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
