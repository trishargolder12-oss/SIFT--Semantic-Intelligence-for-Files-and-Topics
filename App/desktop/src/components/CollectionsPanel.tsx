import { useCallback, useEffect, useRef, useState } from 'react';
import type { CollectionDestination, CollectionEvidence, CollectionSummary, CollectionVision, StudyCollection, SyllabusOutline, SyllabusTopic } from '../types';
import { Icon } from './Icon';

function topicList(outline: SyllabusOutline): SyllabusTopic[] {
  const visit=(topics:SyllabusTopic[]):SyllabusTopic[]=>topics.flatMap(topic=>[topic,...visit(topic.subtopics)]);
  return outline.units.flatMap(unit=>visit(unit.topics));
}
function OutlineEditor({ initial,onSave,onCancel }: {initial:SyllabusOutline;onSave:(value:SyllabusOutline)=>Promise<void>;onCancel:()=>void}) {
  const [value,setValue]=useState(()=>structuredClone(initial));
  const [busy,setBusy]=useState(false); const [error,setError]=useState('');
  function mutate(work: (copy:SyllabusOutline)=>void) {const copy=structuredClone(value);work(copy);setValue(copy);}
  function renderTopics(topics:SyllabusTopic[],depth=0):React.ReactNode {
    return topics.map((topic,index)=><div className="outline-topic" key={topic.id} style={{marginLeft:depth*12}}>
      <label>Topic<input value={topic.name} maxLength={500} onChange={event=>mutate(copy=>{topicList(copy).find(t=>t.id===topic.id)!.name=event.target.value;})}/></label>
      <label>Supported aliases<input value={topic.aliases.join('; ')} maxLength={1000} onChange={event=>mutate(copy=>{topicList(copy).find(t=>t.id===topic.id)!.aliases=event.target.value.split(';').map(t=>t.trim()).filter(Boolean);})}/></label>
      <small>{topic.source.page ? `Source page ${topic.source.page}` : 'Source text'} Â· {topic.source.method || 'edited'}{topic.source.uncertain?' Â· needs review':''}<br/>Original: {topic.original}</small>
      <div className="outline-controls"><button type="button" disabled={!index} onClick={()=>mutate(copy=>{const find=(items:SyllabusTopic[]):boolean=>{const at=items.findIndex(t=>t.id===topic.id);if(at>=0){[items[at-1],items[at]]=[items[at],items[at-1]];return true;}return items.some(t=>find(t.subtopics));};copy.units.some(u=>find(u.topics));})}>Move up</button>
      <button type="button" disabled={index===topics.length-1} onClick={()=>mutate(copy=>{const find=(items:SyllabusTopic[]):boolean=>{const at=items.findIndex(t=>t.id===topic.id);if(at>=0){[items[at+1],items[at]]=[items[at],items[at+1]];return true;}return items.some(t=>find(t.subtopics));};copy.units.some(u=>find(u.topics));})}>Move down</button>
      <button type="button" disabled={!index} onClick={()=>mutate(copy=>{const find=(items:SyllabusTopic[]):boolean=>{const at=items.findIndex(t=>t.id===topic.id);if(at>=0){items[at-1].name+='; '+items[at].name;items[at-1].subtopics.push(...items[at].subtopics);items.splice(at,1);return true;}return items.some(t=>find(t.subtopics));};copy.units.some(u=>find(u.topics));})}>Merge with previous</button>
      <button type="button" onClick={()=>mutate(copy=>{const find=(items:SyllabusTopic[]):boolean=>{const at=items.findIndex(t=>t.id===topic.id);if(at>=0){const parts=items[at].name.split(';').map(t=>t.trim()).filter(Boolean);if(parts.length<2)throw new Error('Separate the topic names with a semicolon before splitting.');items[at].name=parts[0];items.splice(at+1,0,...parts.slice(1).map(name=>({...structuredClone(items[at]),id:crypto.randomUUID(),name,subtopics:[]})));return true;}return items.some(t=>find(t.subtopics));};try{copy.units.some(u=>find(u.topics));}catch(cause){setError(String(cause));}})}>Split at semicolon</button></div>
      {renderTopics(topic.subtopics,depth+1)}
    </div>);
  }
  return <form className="outline-editor" onSubmit={event=>{event.preventDefault();setBusy(true);void onSave(value).catch(cause=>setError(String(cause))).finally(()=>setBusy(false));}}>
    <h3>Edit syllabus outline</h3><p>Your changes survive refreshes. Original wording remains available.</p>
    <label>Subject<input value={value.subject} maxLength={120} onChange={event=>setValue({...value,subject:event.target.value})}/></label>
    {value.units.map((unit,index)=><fieldset key={unit.id}><legend>Unit {index+1}</legend><label>Unit name<input value={unit.name} maxLength={200} onChange={event=>mutate(copy=>{copy.units[index].name=event.target.value;})}/></label><div className="outline-controls"><button type="button" disabled={!index} onClick={()=>mutate(copy=>{[copy.units[index-1],copy.units[index]]=[copy.units[index],copy.units[index-1]];})}>Move unit up</button><button type="button" onClick={()=>mutate(copy=>copy.units[index].topics.push({id:crypto.randomUUID(),name:'New topic',original:'Added by you',source:{method:'user'},aliases:[],subtopics:[]}))}>Add topic</button></div>{renderTopics(unit.topics)}</fieldset>)}
    <button type="button" className="text-button" onClick={()=>mutate(copy=>copy.units.push({id:crypto.randomUUID(),name:'New unit',original:'Added by you',source:{method:'user'},topics:[]}))}>Add unit</button>
    {error&&<p role="alert">{error}</p>}<div className="result-actions"><button className="button button-primary" disabled={busy}>Save and rematch</button><button type="button" className="button" onClick={onCancel} disabled={busy}>Cancel editing</button></div>
  </form>;
}

export function CollectionsPanel({initialText='',initialAttachment=false}:{initialText?:string;initialAttachment?:boolean}) {
  const [list,setList]=useState<CollectionSummary[]>([]),[selected,setSelected]=useState<string|null>(()=>localStorage.getItem('sift.collection'));
  const [detail,setDetail]=useState<StudyCollection|null>(null),[topic,setTopic]=useState<string|null>(null),[offset,setOffset]=useState(0);
  const [text,setText]=useState(initialText),[attachment,setAttachment]=useState<{id:string;name:string}|null>(null),[intake,setIntake]=useState(!selected||!!initialText||initialAttachment);
  const [updatingSource,setUpdatingSource]=useState(false);
  const [destination,setDestination]=useState<CollectionDestination|null>(null),[vision,setVision]=useState<CollectionVision|null>(null);
  const [notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[editing,setEditing]=useState(false);
  const [preview,setPreview]=useState<{image:string;evidence:CollectionEvidence;dimensions?:number[]}|null>(null);
  const alive=useRef(true),generation=useRef(0),first=useRef(true),scopeChanging=useRef(false);
  const previewGeneration=useRef(0);
  const viewKey=JSON.stringify([selected,topic,offset,detail?.revision,detail?.items.map(item=>[item.topic_id,item.file_id,item.content_hash])]);
  const currentView=useRef(viewKey);currentView.current=viewKey;
  const clearPreview=useCallback(()=>{previewGeneration.current++;setPreview(null);},[]);
  useEffect(()=>{clearPreview();},[viewKey,clearPreview]);
  async function inspectEvidence(evidence:CollectionEvidence) {
    const request=++previewGeneration.current,view=currentView.current;
    setPreview(null);
    const current=()=>alive.current&&!scopeChanging.current&&request===previewGeneration.current&&view===currentView.current;
    try {
      const page=await window.sift.collectionPage(evidence.source,evidence.version,evidence.page!);
      if(current())setPreview({image:page.image,evidence,dimensions:page.dimensions});
    } catch(cause) {if(current())setNotice(String(cause));}
  }
  const fail=useCallback((cause:unknown)=>setNotice(String(cause)),[]);
  const refresh=useCallback(async()=>{
    const request=++generation.current;
    const [collections,output,capabilities]=await Promise.all([window.sift.collections(),window.sift.collectionGetDestination(),window.sift.collectionVision()]);
    const current=selected?await window.sift.collectionDetail(selected,topic,offset).catch(cause=>{if(request===generation.current){setDetail(null);fail(cause);}return null;}):null;
    if (!alive.current||request!==generation.current||scopeChanging.current)return;
    setList(collections);setDestination(output);setVision(capabilities);setDetail(current);
  },[selected,topic,offset]);
  async function action(work:()=>Promise<unknown>) {setBusy(true);setNotice('');try{await work();await refresh();}catch(cause){fail(cause);}finally{setBusy(false);}}
  async function attach(){const value=await window.sift.collectionAttach();if(value){setAttachment(value);setText('');setIntake(true);}}
  useEffect(()=>{alive.current=true;let stopped=false,timer:number;const changing=()=>{scopeChanging.current=true;generation.current++;setDetail(null);clearPreview();};const settled=()=>{scopeChanging.current=false;void refresh().catch(fail);};window.addEventListener('sift-permissions-changing',changing);window.addEventListener('sift-permissions-settled',settled);
    async function poll(){try{await refresh();}catch(cause){if(!stopped)fail(cause);}if(!stopped)timer=window.setTimeout(poll,1500);}void poll();
    if(first.current&&initialAttachment){first.current=false;void attach().catch(fail);}
    return()=>{stopped=true;alive.current=false;generation.current++;window.clearTimeout(timer);window.removeEventListener('sift-permissions-changing',changing);window.removeEventListener('sift-permissions-settled',settled);};
  },[refresh,fail]);
  const job=detail?.job,working=!!job&&['queued','running'].includes(job.state);
  const allTopics=detail?topicList(detail.outline):[];
  const choose=(id:string)=>{generation.current++;setDetail(null);clearPreview();setSelected(id);setTopic(null);setOffset(0);setEditing(false);setIntake(false);localStorage.setItem('sift.collection',id);};
  return <section className="collections-panel" aria-label="Syllabus organizer">
    <div className="collection-toolbar"><button className="button button-small" onClick={()=>void action(attach)}><Icon name="file" small/>Attach syllabus</button><button className="button button-small" onClick={()=>{setIntake(true);setAttachment(null);setText('');}}>Paste syllabus text</button><button className="text-button" onClick={()=>void action(async()=>{const output=await window.sift.collectionDestination();if(output)setDestination(output);})}>{destination?'Change output folder':'Choose output folder'}</button>{destination&&<button className="text-button" onClick={()=>void action(()=>window.sift.collectionShowOutput())}>Open collection folder</button>}</div>
    <div className="collection-permissions"><Icon name="shield" small/>Approved library + this attachment Â· Writes only to {destination?.path||'a folder you select'} Â· Originals stay read-only</div>
    {destination&&<button className="text-button disconnect-output" onClick={()=>void action(()=>window.sift.collectionDisconnectOutput())}>Disconnect output folder</button>}
    {notice&&<p className="discovery-notice" role="status">{notice}<button className="text-button" onClick={()=>setNotice('')}>Dismiss</button></p>}
    <div className="collection-layout"><aside className="collection-tree"><h3>Study collections</h3>{list.map(item=><button className={selected===item.id?'selected':''} key={item.id} onClick={()=>choose(item.id)}>{item.subject}<small>Revision {item.revision} Â· {item.state}</small></button>)}
      {detail&&<><h3>Units &amp; topics</h3><button onClick={()=>{clearPreview();setTopic(null);setOffset(0);}}>All matches</button>{detail.outline.units.map(unit=><section key={unit.id}><h4>{unit.name}</h4>{detail.coverage.filter(item=>item.unit===unit.name).map(item=><button key={item.id} className={topic===item.id?'selected':''} onClick={()=>{setTopic(item.id);setOffset(0);clearPreview();}}>{item.name}<small>{item.matches} matching Â· {item.review} review</small></button>)}</section>)}</>}
    </aside><main className="collection-content">
      {intake&&<form className="syllabus-intake" onSubmit={event=>{event.preventDefault();void action(async()=>{if(!destination){const output=await window.sift.collectionDestination();if(!output)return;setDestination(output);}const started=await window.sift.collectionCreate({... (attachment?{attachment_id:attachment.id}:{text}),... (updatingSource&&selected?{collection_id:selected}:{})});choose(started.id);});}}>
        <h2>{updatingSource?'Update this syllabus revision':'Organize my notes according to this syllabus.'}</h2><p>Attach a PDF or photograph, or paste the syllabus below. SIFT keeps the original order and shows uncertain parts for review.</p><label className="source-update-choice"><input type="checkbox" checked={updatingSource} disabled={!selected} onChange={event=>setUpdatingSource(event.target.checked)}/>Update the selected collection instead of creating a new one</label>
        {attachment?<p className="attachment-chip">{attachment.name}<button className="text-button" type="button" onClick={()=>void action(async()=>{await window.sift.collectionDetach(attachment.id);setAttachment(null);})}>Remove attachment permission</button></p>:<label>Syllabus text<textarea value={text} onChange={event=>setText(event.target.value)} maxLength={100000} rows={9} placeholder={'Subject: Computer Architecture\nUnit 1 - Fundamentals\nVon Neumann Architecture; Number Systems'}/></label>}
        <button className="button button-primary" disabled={busy||(!attachment&&!text.trim())}>Organize notes</button>{selected&&<button className="text-button" type="button" onClick={()=>setIntake(false)}>Back to collection</button>}
      </form>}
      {!intake&&!detail&&<div className="discovery-welcome"><h2>Your syllabus, with the notes beside it.</h2><p>Choose a collection or attach a syllabus to begin.</p></div>}
      {!intake&&detail&&<><header className="collection-heading"><div><p className="eyebrow">Study collection Â· revision {detail.revision}</p><h2>{detail.subject}</h2><p>{detail.topics_with_material} of {detail.coverage.length} topics with matching material Â· {detail.gaps} gaps</p><small>This measures matching material, not complete exam preparation.</small></div><div className="result-actions"><button className="button button-small" disabled={busy||working} onClick={()=>setEditing(value=>!value)}>Edit outline</button><button className="button button-small" disabled={busy||working} onClick={()=>void action(()=>window.sift.collectionRefresh(detail.id))}>Refresh collection</button></div></header>
        {job&&<div className="collection-progress" role="status"><span>{working?job.phase:job.state} Â· {job.processed} / {job.total||'â€¦'}</span>{working&&<button className="text-button" onClick={()=>void action(()=>window.sift.collectionCancel(job.id))}>Cancel organization</button>}{job.error&&<span>{job.error}</span>}</div>}
        <div className="collection-export" role="status"><span>Shortcut export: {detail.export?.state||'Choose an output folder'}{detail.export?.error&&` Â· ${detail.export.error}`}</span>{detail.export&&['pending','writing'].includes(detail.export.state)?<button className="text-button" onClick={()=>void action(()=>window.sift.collectionCancelExport(detail.export!.id))}>Cancel export</button>:<button className="text-button" disabled={busy||!destination} onClick={()=>void action(()=>window.sift.collectionRetry(detail.id))}>Retry / reconcile shortcuts</button>}</div>
        {detail.export?.state==='done'&&<p className="collection-complete" role="status">Organized {detail.outline.units.length} units with matching material for {detail.topics_with_material} topics. {detail.gaps} topics have no approved matching material; {detail.coverage.reduce((count,item)=>count+item.review,0)} candidates need review.</p>}
        {detail.issues.length>0&&<details className="collection-issues"><summary>{detail.issues.length} source issues need review</summary>{detail.issues.map((issue,index)=><p key={index}>{issue}</p>)}</details>}
        {editing?<OutlineEditor initial={detail.outline} onCancel={()=>setEditing(false)} onSave={async value=>{await window.sift.collectionOutline(detail.id,value);setEditing(false);await refresh();}}/>:<>
          <details className="collection-gaps"><summary>Topics without matching material ({detail.gaps})</summary>{detail.coverage.filter(item=>!item.matches).map(item=><button className="text-button" key={item.id} onClick={()=>{clearPreview();setTopic(item.id);setOffset(0);}}>{item.unit} Â· {item.name}{item.review?' Â· candidates need review':''}</button>)}</details>
          <h3>{topic?allTopics.find(t=>t.id===topic)?.name:'All topic evidence'} <span className="count-pill">{detail.total}</span></h3>
          {detail.items.map(item=><article className="discovery-result" key={item.topic_id+':'+item.file_id}><div className="result-heading"><div><h3>{item.filename}</h3><p className="result-path">{item.path}</p></div><span className={item.classification==='substantive'?'match-label':'likely-label'}>{item.decision==='auto'?item.classification:item.decision}</span></div><p>{allTopics.find(t=>t.id===item.topic_id)?.name}</p><p className="result-reason">{item.reason}</p>
            {item.evidence.map((evidence,index)=><blockquote key={evidence.chunk_id+':'+index}><div>{evidence.location||'Extracted text'} Â· {evidence.origin}{evidence.ocr_confidence!=null?` Â· OCR confidence ${evidence.ocr_confidence.toFixed(2)}`:''}</div><p>{evidence.text}</p>{evidence.uncertain&&<small>Extraction needs review. OCR confidence is separate from relevance.</small>}{evidence.page&&<button className="text-button" onClick={()=>void inspectEvidence(evidence)}>Inspect page &amp; evidence</button>}</blockquote>)}
            <div className="result-actions"><button className="text-button" onClick={()=>void action(()=>window.sift.collectionOpen('file:'+item.file_id))}>Open source</button><button className="text-button" onClick={()=>void action(()=>window.sift.collectionDecision(detail.id,item.topic_id,item.file_id,'approved'))}>Approve</button><button className="text-button" onClick={()=>void action(()=>window.sift.collectionDecision(detail.id,item.topic_id,item.file_id,'rejected'))}>Reject</button><label>Move to topic<select aria-label={`Move ${item.filename} to topic`} value="" onChange={event=>{if(event.target.value)void action(()=>window.sift.collectionDecision(detail.id,item.topic_id,item.file_id,'approved',event.target.value));}}><option value="">Choose topicâ€¦</option>{allTopics.filter(t=>t.id!==item.topic_id).map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label></div>
          </article>)}
          {!detail.items.length&&!working&&<p className="collection-empty">No matching material here yet. Review the outline or add notes to an approved folder.</p>}
          {detail.total>25&&<div className="discovery-pager"><button className="text-button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button><span>{offset+1}â€“{Math.min(offset+25,detail.total)} of {detail.total}</span><button className="text-button" disabled={!detail.has_more} onClick={()=>setOffset(offset+25)}>More matches</button></div>}
        </>}
        {detail.attachment_id&&<details><summary>Syllabus reference permission</summary><button className="text-button" onClick={()=>void action(async()=>{await window.sift.collectionOpen('attachment:'+detail.attachment_id);})}>Open original syllabus</button><button className="text-button" onClick={()=>void action(async()=>{setDetail(null);clearPreview();await window.sift.collectionDetach(detail.attachment_id!);setSelected(null);localStorage.removeItem('sift.collection');})}>Revoke attachment access</button></details>}
      </>}
      {preview&&<section className="collection-preview" aria-label="Source page preview"><div className="result-actions"><h3>{preview.evidence.location} Â· {preview.evidence.origin}</h3><button className="button button-small" onClick={clearPreview}>Close page preview</button></div><div className="collection-page-image"><img src={preview.image} alt={`Source page ${preview.evidence.page}; compare highlighted wording with the excerpt`}/>{preview.evidence.bbox&&preview.dimensions&&<span className="region-highlight" style={{left:100*preview.evidence.bbox[0]/preview.dimensions[0]+'%',top:100*preview.evidence.bbox[1]/preview.dimensions[1]+'%',width:100*(preview.evidence.bbox[2]-preview.evidence.bbox[0])/preview.dimensions[0]+'%',height:100*(preview.evidence.bbox[3]-preview.evidence.bbox[1])/preview.dimensions[1]+'%'}}/>}</div><p className="evidence-highlight"><mark>{preview.evidence.text}</mark></p></section>}
    </main></div>
    <details className="collection-setup"><summary>Local OCR &amp; visual models Â· {vision?.ocr_ready?'OCR pack installed':'Native text available; image pages may need setup'}</summary><div><p>Native PDF text is read first. The optional PP-OCRv5 mobile pack runs on CPU with a 1.5 GB page-worker memory limit. Extract the separate SIFT OCR pack, then select its folder. Processing makes no external requests.</p><p>Pack location: {vision?.ocr_pack||'Not configured'} Â· Up to {vision?.page_limit||200} pages per source.</p><button className="button button-small" disabled={busy} onClick={()=>void action(()=>window.sift.collectionPack())}>Select extracted OCR pack</button><p>Qwen3-VL 2B is optional for difficult visual regions: 1.9 GB download, estimated 4â€“6 GB RAM, Apache-2.0. It produces labeled descriptions, not quotations. Models stay in Ollamaâ€™s local model directory. No model is downloaded automatically.</p><button className="text-button" onClick={()=>void action(()=>window.sift.discoveryModels(!vision?.models.enabled))}>{vision?.models.enabled?'Disable local models':'Enable local models'}</button><button className="button button-small" disabled={!vision?.models.enabled||!vision?.models.available||busy||vision.models.ready.vision} onClick={()=>void action(()=>window.sift.discoveryDownload('vision'))}>{vision?.models.ready.vision?'Vision model installed':'Download vision model Â· 1.9 GB'}</button>{vision?.models.job&&<p role="status">Local model job: {vision.models.job.kind} Â· {vision.models.job.processed} / {vision.models.job.total||'â€¦'}</p>}<p>Handwriting, formulas, tables and blurry pages may need manual review. Supported quality is measured on the provided test set, not every handwriting style.</p></div></details>
  </section>;
}
