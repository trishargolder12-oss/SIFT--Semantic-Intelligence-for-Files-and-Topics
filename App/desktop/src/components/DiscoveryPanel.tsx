import { useCallback, useEffect, useRef, useState } from 'react';
import type { DiscoveryFile, DiscoveryFilters, DiscoveryJob, DiscoveryStatus, DiscoveryTurn, Folder, LibraryGroup } from '../types';
import { Icon } from './Icon';
import siftLogo from '../assets/sift-book.svg';
import { CollectionsPanel } from './CollectionsPanel';

const labels = { subject: 'Subjects', topic: 'Topics', type: 'Document types' };
const groupKinds = ['subject', 'topic', 'type'] as const;
function folderName(path: string) { return path.split(/[\\/]/).filter(Boolean).pop() || path; }
function lastConversation() { try { return localStorage.getItem('sift.discoveryConversation'); } catch { return null; } }

function SectionEditor({ file, onSave, onCancel }: { file: DiscoveryFile; onSave: (groups: Record<string, string[]>) => Promise<void>; onCancel: () => void }) {
  const [values, setValues] = useState(() => Object.fromEntries(groupKinds.map(kind => [kind, file.groups.filter(group => group.kind === kind).map(group => group.name).join(', ')])));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  return <form className="section-editor" onSubmit={event => { event.preventDefault(); setSaving(true); setError(''); void onSave(Object.fromEntries(groupKinds.map(kind => [kind, values[kind].split(',').map(name => name.trim()).filter(Boolean)]))).catch(error => setError(String(error))).finally(() => setSaving(false)); }}>
    <p>Your choices stay in place during later scans. Separate names with commas.</p>
    {groupKinds.map(kind => <label key={kind}>{labels[kind]}<input value={values[kind]} maxLength={600} onChange={event => setValues({ ...values, [kind]: event.target.value })} autoFocus={kind === 'subject'} /></label>)}
    {error && <p role="alert" className="error-text">{error}</p>}
    <div className="result-actions"><button type="submit" className="button button-primary button-small" disabled={saving}>Save sections</button><button type="button" className="button button-small" onClick={onCancel} disabled={saving}>Cancel editing</button></div>
  </form>;
}

function ResultCard({ file, turn, onPreview, onRefresh, onError }: { file: DiscoveryFile; turn: DiscoveryTurn; onPreview: (turn: string, id: number) => void; onRefresh: () => Promise<void>; onError: (error: unknown) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  async function open(reveal = false) {
    setBusy(true);
    try { await window.sift.discoveryOpen(turn.id, file.id, reveal); }
    catch (error) { onError(error); await onRefresh(); }
    finally { setBusy(false); }
  }
  return <article className="discovery-result" aria-label={file.filename}>
    <div className="result-heading"><span className={`file-icon ${file.extension.slice(1)}`}><Icon name="file" small />{file.extension.slice(1).toUpperCase()}</span><div><h3>{file.ordinal && <small>{file.ordinal}. </small>}{file.filename}</h3>{file.title !== file.filename && <p className="result-title">{file.title}</p>}<p className="result-path" title={file.path}>{file.path}</p></div>{file.likely && <span className="likely-label">Likely match</span>}</div>
    <p className="result-reason"><Icon name="check" small />{file.reason}</p>
    <blockquote><div>{file.location || (file.excerpt ? 'Extracted text' : 'No extracted text')}</div><p tabIndex={0} aria-label="Source excerpt">{file.excerpt || 'Matched the filename or library section. This file has no searchable extracted text.'}</p></blockquote>
    <div className="result-sections">{file.groups.map(group => <span key={`${group.id}-${group.source}`} title={`${labels[group.kind]} · ${group.reason}`}>{group.name}{group.source === 'user' ? ' · yours' : ''}</span>)}</div>
    <div className="result-actions"><button className="text-button" disabled={busy} onClick={() => void open()}><Icon name="external" small />Open file</button><button className="text-button" disabled={busy} onClick={() => void open(true)}><Icon name="folderOpen" small />Show in folder</button><button className="text-button" disabled={busy} onClick={() => onPreview(turn.id, file.id)}><Icon name="search" small />Preview</button><button className="text-button" onClick={() => setEditing(value => !value)} aria-expanded={editing}>Edit sections</button></div>
    <details className="result-dates"><summary>File dates</summary><p>Added to SIFT: {new Date(file.added_at).toLocaleString()}<br />File modified: {new Date(file.modified_ns / 1e6).toLocaleString()}</p></details>
    {editing && <SectionEditor file={file} onCancel={() => setEditing(false)} onSave={async groups => { await window.sift.discoveryCorrect(file.id, groups); await onRefresh(); setEditing(false); }} />}
  </article>;
}

export function DiscoveryPanel({ folders, revision, onClose, onPreview }: { folders: Folder[]; revision: string; onClose: () => void; onPreview: (turn: string, id: number) => void }) {
  const [organizer,setOrganizer]=useState(false);
  const [syllabusText,setSyllabusText]=useState('');
  const [attachSyllabus,setAttachSyllabus]=useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  const generation = useRef(0);
  const active = useRef<number | null>(null);
  const scopeChanging = useRef(false);
  const pageOffsets = useRef<Record<string, number>>({});
  const [conversation, setConversation] = useState<string | null>(lastConversation);
  const conversationRef = useRef(conversation);
  const [turns, setTurns] = useState<DiscoveryTurn[]>([]);
  const [groups, setGroups] = useState<LibraryGroup[]>([]);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [job, setJob] = useState<DiscoveryJob | null>(null);
  const [message, setMessage] = useState('');
  const [pendingMessage, setPendingMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [root, setRoot] = useState('');
  const [extension, setExtension] = useState('');
  const [rename, setRename] = useState<{ id: number; name: string } | null>(null);
  const [showSections, setShowSections] = useState(false);
  const [sending, setSending] = useState(false);
  const [setupBusy, setSetupBusy] = useState(false);
  const scope = JSON.stringify(folders.map(folder => [folder.id, folder.state]));
  const error = useCallback((cause: unknown) => { if (alive.current) setNotice(cause instanceof Error ? cause.message : String(cause)); }, []);

  useEffect(() => {
    alive.current = true;
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal(); input.current?.focus();
    return () => { alive.current = false; generation.current++; element.close(); previous?.focus({ preventScroll: true }); };
  }, []);
  useEffect(() => {
    conversationRef.current = conversation;
    try { if (conversation) localStorage.setItem('sift.discoveryConversation', conversation); else localStorage.removeItem('sift.discoveryConversation'); } catch { /* Conversations still work without preference storage. */ }
  }, [conversation]);

  const refresh = useCallback(async () => {
    if (scopeChanging.current) return;
    const request = generation.current;
    const current = conversationRef.current;
    const [sections, history] = await Promise.all([window.sift.discoveryGroups(), current ? window.sift.discoveryHistory(current) : Promise.resolve([])]);
    const pages = await Promise.all(history.map(turn => pageOffsets.current[turn.id] ? window.sift.discoveryTurn(turn.id, pageOffsets.current[turn.id]) : turn));
    if (!alive.current || scopeChanging.current || request !== generation.current || current !== conversationRef.current) return;
    setGroups(sections); setTurns(pages);
  }, []);

  useEffect(() => {
    const changing = () => { scopeChanging.current = true; generation.current++; setTurns([]); setGroups([]); };
    const settled = () => { scopeChanging.current = false; void refresh().catch(error); };
    window.addEventListener('sift-permissions-changing', changing);
    window.addEventListener('sift-permissions-settled', settled);
    return () => { window.removeEventListener('sift-permissions-changing', changing); window.removeEventListener('sift-permissions-settled', settled); };
  }, [refresh, error]);

  useEffect(() => {
    generation.current++;
    scopeChanging.current = false;
    // Clear visible evidence before awaiting any request after a scope/content change.
    setTurns([]); setGroups([]);
    if (root && !folders.some(folder => folder.id === Number(root))) setRoot('');
    void refresh().catch(error);
  }, [scope, revision, refresh, error]); // Root data is represented by scope, not array identity.

  useEffect(() => {
    let stopped = false, timer: number | undefined;
    async function poll() {
      try {
        const latest = await window.sift.discoveryStatus();
        if (stopped) return;
        setStatus(latest);
        const current = active.current;
        if (current) {
          const response = await window.sift.discoveryJob(current);
          if (stopped || active.current !== current) return;
          setJob(response);
          if (['done', 'failed', 'cancelled'].includes(response.state)) {
            active.current = null; setPendingMessage(''); setSending(false);
            if (response.error) setNotice(response.error);
            else if (response.state === 'cancelled') setNotice('Cancelled. Your library and completed work are safe.');
            await refresh();
          }
        } else await refresh();
      } catch (cause) { if (!stopped) error(cause); }
      finally { if (!stopped) timer = window.setTimeout(poll, active.current ? 500 : 3000); }
    }
    void poll();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [refresh, error, job?.id]);
  useEffect(() => {
    const container = dialog.current?.querySelector<HTMLElement>('.conversation');
    if (!container) return;
    if (pendingMessage) { container.scrollTop = container.scrollHeight; return; }
    const latest = Array.from(container.querySelectorAll<HTMLElement>('.conversation-turn')).at(-1);
    if (latest) container.scrollTop += latest.getBoundingClientRect().top - container.getBoundingClientRect().top - 16;
  }, [turns.length, pendingMessage]);

  async function send(value = message, extra: DiscoveryFilters = {}) {
    if (/organiz[es].*(?:notes|syllabus)|(?:unit|module)\s+[1i]\b[^]*\n/i.test(value)) {setSyllabusText(/(?:unit|module)\s+[1i]\b/i.test(value)?value:'');setOrganizer(true);setMessage('');return;}
    if (!value.trim() || active.current || sending) return;
    setSending(true); setNotice(''); setPendingMessage(value.trim()); setMessage('');
    try {
      const filters: DiscoveryFilters = { ...(root ? { root_id: Number(root) } : {}), ...(extension ? { extension: extension as DiscoveryFilters['extension'] } : {}), ...extra };
      const latest = turns.at(-1);
      const started = await window.sift.discoveryChat(value.trim(), conversationRef.current, filters, new Date().getTimezoneOffset(), latest ? {turn_id:latest.id,offset:latest.offset} : undefined);
      if (!alive.current) return;
      conversationRef.current = started.conversation_id; setConversation(started.conversation_id);
      active.current = started.id; setJob({ id: started.id, kind: 'chat', state: 'queued', processed: 0, total: 0, error: null });
    } catch (cause) { error(cause); setSending(false); setPendingMessage(''); }
  }
  async function cancel(id: number) {
    try { const response = await window.sift.discoveryCancel(id); if (active.current === id) { active.current = null; setJob(null); setSending(false); setPendingMessage(''); } setNotice(response.cancelled ? 'Cancelled. Completed work is retained.' : 'That request has already finished.'); await refresh(); }
    catch (cause) { error(cause); }
  }
  async function loadPage(turnId: string, offset: number) {
    const request = generation.current;
    try {
      const page = await window.sift.discoveryTurn(turnId, offset);
      if (!alive.current || scopeChanging.current || request !== generation.current) return;
      pageOffsets.current[turnId] = offset;
      setTurns(items => items.map(item => item.id === page.id ? page : item));
    } catch (cause) { error(cause); }
  }
  async function setup(work: () => Promise<{ id: number } | DiscoveryStatus>) {
    setSetupBusy(true); setNotice('');
    try { const response = await work(); if ('id' in response) { active.current = response.id; setJob({ id: response.id, kind: 'rebuild', state: 'queued', processed: 0, total: 0, error: null }); } setStatus(await window.sift.discoveryStatus()); }
    catch (cause) { error(cause); }
    finally { setSetupBusy(false); }
  }
  const busy = sending || !!active.current;
  const processing = job && ['queued', 'running'].includes(job.state) ? job : status?.job;
  return <dialog ref={dialog} className="discovery-dialog" aria-labelledby="discovery-title" onCancel={event => { event.preventDefault(); onClose(); }} onKeyDown={event => {
    if (event.key !== 'Tab') return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[href]')).filter(element => element.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }}>
    <header className="discovery-header"><div className="discovery-brand"><img src={siftLogo} alt="" /><span>SIFT</span></div><h2 id="discovery-title">Find it with SIFT</h2><button className="icon-button" onClick={onClose} aria-label="Close file discovery"><Icon name="close" /></button></header>
    <nav className="discovery-tabs" aria-label="Discovery tools"><button aria-selected={!organizer} onClick={()=>setOrganizer(false)}>Find files</button><button aria-selected={organizer} onClick={()=>{setAttachSyllabus(false);setOrganizer(true);}}>Organize syllabus</button><button onClick={()=>{setAttachSyllabus(true);setOrganizer(true);}}>Attach syllabus</button></nav>
    {organizer?<CollectionsPanel initialText={syllabusText} initialAttachment={attachSyllabus}/>:<>
    <div className="discovery-scope"><span><Icon name="shield" small />Approved folders only</span><label>Folder<select value={root} onChange={event => setRoot(event.target.value)}><option value="">All approved folders ({folders.length})</option>{folders.map(folder => <option key={folder.id} value={folder.id}>{folderName(folder.path)}{folder.state === 'paused' ? ' · indexing paused' : ''}</option>)}</select></label><label>Type<select value={extension} onChange={event => setExtension(event.target.value)}><option value="">All file types</option><option value=".pdf">PDF</option><option value=".docx">DOCX</option><option value=".txt">TXT</option></select></label><button className="text-button sections-toggle" aria-expanded={showSections} onClick={() => setShowSections(value => !value)}>Library sections</button><button className="text-button" disabled={busy} onClick={() => { generation.current++; conversationRef.current = null; setConversation(null); setTurns([]); setNotice(''); input.current?.focus(); }}>New conversation</button></div>
    <div className="discovery-layout">
      <aside className={`discovery-sections ${showSections ? 'expanded' : ''}`} aria-label="Virtual library sections"><p className="section-intro">Virtual library<br /><span>Your folders stay untouched.</span></p>{groupKinds.map(kind => <section key={kind}><h3>{labels[kind]}</h3>{groups.filter(group => group.kind === kind).map(group => <div className="section-row" key={group.id}><button className="section-link" disabled={busy} onClick={() => { setShowSections(false); void send(`Show files in ${group.name}`, { group_id: group.id }); }}><span>{group.name}</span><small>{group.count}</small></button><button className="icon-button" aria-label={`Rename ${group.name}`} onClick={() => setRename({ id: group.id, name: group.name })}><Icon name="edit" small /></button></div>)}{!groups.some(group => group.kind === kind) && <p className="section-empty">{status?.documents.pending ? 'Preparing sections…' : 'No sections yet.'}</p>}</section>)}
        {rename && <form className="rename-section" onSubmit={event => { event.preventDefault(); void window.sift.discoveryRename(rename.id, rename.name).then(async () => { setRename(null); await refresh(); }).catch(error); }}><label>Section name<input value={rename.name} maxLength={100} autoFocus onChange={event => setRename({ ...rename, name: event.target.value })} /></label><button className="text-button" type="submit">Save name</button><button className="text-button" type="button" onClick={() => setRename(null)}>Cancel</button></form>}
      </aside>
      <div className="discovery-main">
        <div className="conversation" role="region" aria-label="File discovery conversation">
          {!turns.length && !pendingMessage && <div className="discovery-welcome"><Icon name="sparkles" /><h3>A word, a topic, a half-remembered file.</h3><p>Tell me what you’re looking for. I’ll search only your approved folders and show the evidence.</p><p className="discovery-mode">{status?.mode === 'hybrid' ? 'Local meaning + keyword retrieval available' : 'Offline keyword discovery · no language model required'}</p>{!folders.length && <p>Add an approved folder from your library to begin.</p>}</div>}
          {turns.map(turn => <section key={turn.id} className="conversation-turn"><p className="user-message">{turn.message}</p><div className="assistant-message"><p className="discovery-mode">{turn.mode === 'hybrid' ? 'Local meaning + keyword retrieval' : 'Keyword discovery'}{status?.ready.intent ? ' · local query interpretation available' : ''}</p><p className="assistant-reply">{turn.reply}</p>{turn.expansion && <p className="query-adjustment">{turn.expansion}</p>}{turn.corrections.length > 0 && <p className="query-adjustment">Spelling suggestions: {turn.corrections.join(', ')}</p>}{turn.options.length > 0 && <div className="discovery-suggestions">{turn.options.map(option => <button key={option} disabled={busy} onClick={() => void send(option)}>{option}</button>)}</div>}<div className="discovery-results">{turn.items.map(file => <ResultCard key={file.id} file={file} turn={turn} onPreview={onPreview} onRefresh={refresh} onError={error} />)}</div>{turn.total > 10 && <div className="discovery-pager"><span>{turn.offset+1}–{Math.min(turn.offset+turn.items.length, turn.total)} of {turn.total}</span><button className="text-button" disabled={!turn.offset} onClick={() => void loadPage(turn.id, Math.max(0, turn.offset-10))}>Previous matches</button><button className="text-button" disabled={!turn.has_more} onClick={() => void loadPage(turn.id, turn.offset+10)}>More matches</button></div>}</div></section>)}
          {pendingMessage && <section><p className="user-message">{pendingMessage}</p><p className="discovery-pending" role="status"><Icon name="refresh" small className="spin" />{job?.state === 'queued' ? 'Waiting for the local worker…' : 'Searching your approved library…'}</p></section>}
          <div ref={bottom} />
        </div>
        {notice && <div className="discovery-notice" role="status"><span>{notice}</span><button className="icon-button" onClick={() => setNotice('')} aria-label="Dismiss discovery message"><Icon name="close" small /></button></div>}
        <div className="discovery-compose"><div className="discovery-suggestions">{[groups.find(group => group.kind === 'subject') ? `Find notes for ${groups.find(group => group.kind === 'subject')!.name}` : 'Find my notes', 'Do I have a syllabus?', ...(turns.length ? ['No, the other one.'] : [])].map(question => <button key={question} disabled={busy || !folders.length} onClick={() => void send(question)}>{question}</button>)}</div><form onSubmit={event => { event.preventDefault(); void send(); }}><textarea ref={input} aria-label="Ask SIFT to find a file" placeholder="Ask a natural question…" value={message} maxLength={1000} rows={1} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send(); } }} />{active.current && <button type="button" className="text-button" onClick={() => void cancel(active.current!)}>Cancel request</button>}<button type="submit" className="button button-primary" disabled={busy || !message.trim() || !folders.length}>Send<Icon name="send" small /></button></form><p className="compose-note">Only approved folders · Original files stay read-only · Pausing indexing keeps search available.</p></div>
      </div>
    </div>
    <details className="model-setup"><summary>Local models &amp; processing · {status?.mode === 'hybrid' ? 'Meaning retrieval available' : 'Keyword fallback active'}</summary><div className="model-setup-body"><p>Keyword discovery and virtual sections work offline now. Optional local models use Ollama on this device. Install Ollama separately in local-only mode; downloads happen only when you press Download below. Model memory figures are estimates.</p><p>{status?.storage}</p><p>For local-only Ollama operation, set OLLAMA_NO_CLOUD=1 and restart Ollama. No library data is sent during model downloads.</p><button className="text-button" onClick={() => void window.sift.discoverySetup().catch(error)}>Get Ollama for Windows (opens browser)</button><button className="button button-small" disabled={setupBusy} onClick={() => void setup(() => window.sift.discoveryModels(!status?.enabled))}>{status?.enabled ? 'Disable local models' : 'Enable local models'}</button>{status?.enabled && !status.available && <p className="model-warning">Ollama is unavailable. Start it locally at 127.0.0.1:11434; keyword discovery remains available.</p>}<div className="model-catalog">{status && (['embedding', 'intent'] as const).map(role => <article key={role}><h3>{status.catalog[role].name}</h3><p>{status.catalog[role].purpose}<br />{Math.round(status.catalog[role].size_bytes / 1e6)} MB download · {status.catalog[role].memory_estimate} estimated RAM · {status.catalog[role].license}</p><button className="button button-small" disabled={!status.enabled || !status.available || setupBusy || busy || status.ready[role]} onClick={() => void setup(() => window.sift.discoveryDownload(role))}>{status.ready[role] ? 'Installed locally' : `Download ${Math.round(status.catalog[role].size_bytes / 1e6)} MB`}</button></article>)}</div><div className="processing-controls"><button className="button button-small" disabled={busy || setupBusy || !folders.length} onClick={() => void setup(() => window.sift.discoveryRebuild())}>Rebuild discovery index</button><span>{status?.documents.ready || 0} ready · {status?.documents.pending || 0} pending · {status?.documents.deferred || 0} deferred</span>{processing && <span role="status">{processing!.kind} · {processing!.processed} / {processing!.total || '…'}<button className="text-button" onClick={() => void cancel(processing!.id)}>Cancel processing</button></span>}</div></div></details>
    </>}
  </dialog>;
}
