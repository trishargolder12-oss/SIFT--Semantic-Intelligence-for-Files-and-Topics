import { useCallback, useEffect, useRef, useState } from 'react';
import type { DocumentDetail, FileItem, Folder, Job, SearchPage } from './types';
import { DocumentDrawer } from './components/DocumentDrawer';
import { Icon } from './components/Icon';
import { FolderPanel } from './components/FolderPanel';
import { WeatherEffects } from './components/WeatherEffects';
import { useMediaQuery, usePreferences } from './hooks/usePreferences';
import siftLogo from './assets/sift-book.svg';
import { DiscoveryPanel } from './components/DiscoveryPanel';

const FILE_PAGE_SIZE = 200;
const SEARCH_PAGE_SIZE = 50;
type Notice = { text: string; tone: 'info' | 'error' };
type FileStatus = '' | FileItem['status'];
function shortPath(value: string) {
  const parts = value.split(/[\\/]/).filter(Boolean);
  return parts.length > 3 ? `… / ${parts.slice(-3).join(' / ')}` : value;
}
function formatDate(value: string | null, compact = false) {
  if (!value) return 'Not yet';
  const date = new Date(value);
  return compact ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : date.toLocaleString();
}
function statusName(status: FileItem['status']) { return { indexed: 'Indexed', error: 'Needs attention', missing: 'Missing', excluded: 'Excluded' }[status]; }
function snippet(value: string) {
  return value.split(/(\[[^\]]+\])/g).map((part, index) => part.startsWith('[') && part.endsWith(']') ? <mark key={index}>{part.slice(1, -1)}</mark> : part);
}
function jobTitle(job: Job, cancelling: boolean) {
  if (cancelling) return 'Finishing the current file…';
  return { queued: 'Getting your library ready', running: 'A little order is on its way', done: 'Your scan is complete', cancelled: 'Scan cancelled', failed: 'This scan needs attention' }[job.state];
}

export default function App() {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [total, setTotal] = useState(0);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<FileStatus>('');
  const [job, setJob] = useState<Job | null>(null);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [query, setQuery] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [results, setResults] = useState<SearchPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [showTop, setShowTop] = useState(false);
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const workspace = useRef<HTMLElement>(null);
  const app = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const scrollAnimation = useRef(0);
  const [foldersOpen, setFoldersOpen] = useState(false);
  const compact = useMediaQuery('(max-width: 950px)');
  const { reduced, reduceMotion, setReduceMotion, effects, setEffects } = usePreferences();
  useEffect(() => { if (!compact) setFoldersOpen(false); }, [compact]);
  useEffect(() => {
    const element = workspace.current!;
    let frame = 0;
    const cancel = () => { cancelAnimationFrame(scrollAnimation.current); scrollAnimation.current = 0; };
    const update = () => {
      app.current?.style.setProperty('--room-presence', String(Math.min(1, element.scrollTop / 260)));
      const art = app.current?.querySelector<HTMLElement>('.hero-art');
      if (art) art.style.transform = reduced ? 'none' : `translateY(${Math.min(24, element.scrollTop * .055)}px)`;
      setShowTop(element.scrollTop >= 360); frame = 0;
    };
    const scroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    const key = (event: KeyboardEvent) => { if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) cancel(); };
    update(); cancel();
    element.addEventListener('scroll', scroll, { passive: true });
    for (const type of ['wheel', 'touchstart', 'pointerdown']) element.addEventListener(type, cancel, { passive: true });
    window.addEventListener('keydown', key);
    return () => {
      cancel(); cancelAnimationFrame(frame); element.removeEventListener('scroll', scroll);
      for (const type of ['wheel', 'touchstart', 'pointerdown']) element.removeEventListener(type, cancel);
      window.removeEventListener('keydown', key);
    };
  }, [reduced]);
  function backToTop(keyboard: boolean) {
    const element = workspace.current;
    if (!element) return;
    cancelAnimationFrame(scrollAnimation.current);
    const finish = () => { scrollAnimation.current = 0; if (keyboard) heading.current?.focus({ preventScroll: true }); };
    if (reduced) { element.scrollTop = 0; finish(); return; }
    const start = element.scrollTop, duration = Math.min(1000, 450 + start * .18), begin = performance.now();
    const tick = (time: number) => {
      const t = Math.min(1, (time - begin) / duration), eased = t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      element.scrollTop = Math.max(0, start * (1 - eased));
      if (t < 1) scrollAnimation.current = requestAnimationFrame(tick); else finish();
    };
    scrollAnimation.current = requestAnimationFrame(tick);
  }
  function browseLibrary() { document.getElementById('library')?.scrollIntoView({ block: 'start' }); }
  function browseFolders() { if (compact) setFoldersOpen(true); else document.getElementById('folders')?.scrollIntoView({ block: 'start' }); }
  const searchInput = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const libraryRequest = useRef(0);
  const searchRequest = useRef(0);
  const detailRequest = useRef(0);
  const selectedId = useRef<number | null>(null);
  const documentTrigger = useRef<HTMLElement | null>(null);
  const searchView = useRef({ query: '', offset: 0 });
  const libraryView = useRef({ offset, status });
  libraryView.current = { offset, status };

  const showError = useCallback((error: unknown) => {
    const text = error instanceof Error ? error.message : String(error);
    if (mounted.current) setNotice({ tone: 'error', text });
  }, []);

  const loadLibrary = useCallback(async (page = 0, filter: FileStatus = '', background = false) => {
    const request = ++libraryRequest.current;
    if (!background) setLoading(true);
    try {
      const [roots, response] = await Promise.all([window.sift.folders(), window.sift.documents(page, filter || undefined)]);
      let documents = response;
      let actualPage = page;
      if (request !== libraryRequest.current || !mounted.current) return;
      if (page > 0 && documents.items.length === 0) {
        actualPage = documents.total ? Math.floor((documents.total - 1) / FILE_PAGE_SIZE) * FILE_PAGE_SIZE : 0;
        documents = await window.sift.documents(actualPage, filter || undefined);
      }
      if (request !== libraryRequest.current || !mounted.current) return;
      libraryView.current = { offset: actualPage, status: filter };
      setFolders(roots); setFiles(documents.items); setTotal(documents.total); setLibraryTotal(documents.library_total); setOffset(actualPage);
    } catch (error) {
      if (request === libraryRequest.current && mounted.current) throw error;
    } finally {
      if (request === libraryRequest.current && mounted.current) setLoading(false);
    }
  }, []);

  const loadSearch = useCallback(async (term: string, page = 0) => {
    const request = ++searchRequest.current;
    setSearching(true);
    try {
      let response = await window.sift.search(term, page, SEARCH_PAGE_SIZE);
      if (request !== searchRequest.current || term !== searchView.current.query || !mounted.current) return;
      if (page > 0 && response.items.length === 0) response = await window.sift.search(term, 0, SEARCH_PAGE_SIZE);
      if (request !== searchRequest.current || term !== searchView.current.query || !mounted.current) return;
      searchView.current.offset = response.offset;
      setResults(response);
    } catch (error) {
      if (request === searchRequest.current && term === searchView.current.query && mounted.current) throw error;
    } finally {
      if (request === searchRequest.current && mounted.current) setSearching(false);
    }
  }, []);

  const loadDocument = useCallback(async (id: number) => {
    const request = ++detailRequest.current;
    const response = await window.sift.document(id);
    if (request === detailRequest.current && selectedId.current === id && mounted.current) setSelected(response);
  }, []);

  const refreshViews = useCallback(async () => {
    const currentLibrary = libraryView.current;
    const currentSearch = searchView.current;
    await Promise.all([
      loadLibrary(currentLibrary.offset, currentLibrary.status, true),
      currentSearch.query ? loadSearch(currentSearch.query, currentSearch.offset) : Promise.resolve(),
      selectedId.current ? loadDocument(selectedId.current) : Promise.resolve(),
    ]);
  }, [loadLibrary, loadSearch, loadDocument]);

  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    let timer: number | undefined;
    let previousJob = '';
    async function poll() {
      let active = false;
      try {
        const latest = await window.sift.latestJob();
        if (stopped) return;
        active = latest?.state === 'running' || latest?.state === 'queued';
        const signature = JSON.stringify(latest);
        if (signature !== previousJob) {
          previousJob = signature;
          setJob(latest);
          if (!active) setCancelling(false);
          await refreshViews();
        }
      } catch (error) { if (!stopped) showError(error); }
      finally { if (!stopped) timer = window.setTimeout(poll, active ? 1000 : 3500); }
    }
    void poll();
    return () => {
      stopped = true; mounted.current = false;
      window.clearTimeout(timer);
      libraryRequest.current++; searchRequest.current++; detailRequest.current++;
    };
  }, [loadLibrary, refreshViews, showError]);

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !selectedId.current) {
        event.preventDefault(); searchInput.current?.focus();
      }
    }
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, []);

  async function action(work: () => Promise<unknown>) {
    setBusy(true); setNotice(null);
    try { await work(); }
    catch (error) { showError(error); }
    finally { if (mounted.current) setBusy(false); }
  }
  function clearSearch() {
    searchRequest.current++;
    searchView.current = { query: '', offset: 0 };
    setActiveQuery(''); setQuery(''); setResults(null); setSearching(false);
  }
  function search() {
    const term = query.trim();
    if (!term) { clearSearch(); return; }
    searchView.current = { query: term, offset: 0 };
    setActiveQuery(term); setResults(null); setNotice(null);
    void loadSearch(term).catch(showError);
  }
  function addFolder() {
    void action(async () => {
      const chosen = await window.sift.chooseFolder();
      if (!chosen) return;
      setFoldersOpen(false);
      setJob(await window.sift.job(chosen.job.id));
      await refreshViews();
    });
  }
  function scan(rootId?: number) {
    void action(async () => {
      const started = await window.sift.scan(rootId);
      setJob(await window.sift.job(started.id));
    });
  }
  function folderState(id: number, state: 'active' | 'paused' | 'removed') {
    if (state === 'removed') {
      closeDocument(); clearSearch();
      window.dispatchEvent(new Event('sift-permissions-changing'));
    }
    void action(async () => {
      searchRequest.current++; libraryRequest.current++; detailRequest.current++;
      try {
        await window.sift.setFolderState(id, state);
        await refreshViews();
        if (state === 'removed') setNotice({ tone: 'info', text: 'Folder removed from SIFT. Your original files are safe; saved records remain marked as excluded.' });
      } finally { if (state === 'removed') window.dispatchEvent(new Event('sift-permissions-settled')); }
    });
  }
  function showDocument(id: number) {
    documentTrigger.current = window.document.activeElement as HTMLElement | null;
    selectedId.current = id;
    void action(() => loadDocument(id));
  }
  function closeDocument() { selectedId.current = null; detailRequest.current++; setSelected(null); }
  function previewDiscovery(turn: string, id: number) {
    documentTrigger.current = document.activeElement as HTMLElement | null;
    selectedId.current = id;
    const request = ++detailRequest.current;
    void action(async () => {
      const response = await window.sift.discoveryPreview(turn, id);
      if (mounted.current && selectedId.current === id && request === detailRequest.current) setSelected(response);
    });
  }
  function changePage(page: number) {
    if (activeQuery) {
      searchView.current.offset = page;
      void loadSearch(activeQuery, page).catch(showError);
    } else {
      libraryView.current = { offset: page, status };
      setOffset(page);
      void loadLibrary(page, status).catch(showError);
    }
  }
  function changeFilter(filter: FileStatus) {
    libraryView.current = { offset: 0, status: filter };
    setStatus(filter); setOffset(0);
    void loadLibrary(0, filter).catch(showError);
  }
  function cancelScan() {
    if (!job) return;
    setCancelling(true);
    void action(async () => {
      try { await window.sift.cancelJob(job.id); }
      catch (error) { setCancelling(false); throw error; }
    });
  }

  const scanning = job?.state === 'queued' || job?.state === 'running';
  const activeCount = folders.filter(folder => folder.state === 'active').length;
  const visibleTotal = activeQuery ? results?.total || 0 : total;
  const pageOffset = activeQuery ? results?.offset || 0 : offset;
  const pageLength = activeQuery ? results?.items.length || 0 : files.length;
  const pageSize = activeQuery ? SEARCH_PAGE_SIZE : FILE_PAGE_SIZE;
  const pageBusy = activeQuery ? searching : loading;

  return <div ref={app} className={`app-shell ${reduced ? 'motion-off' : ''}`}>
    <div className="study-backdrop" aria-hidden="true" />
    <main ref={workspace} className="workspace" aria-label="SIFT library workspace">
      <WeatherEffects enabled={effects && !reduced} />
      <header className="app-header">
        <div className="brand" aria-label="SIFT, Semantic Intelligence for Files and Topics"><img src={siftLogo} alt="" width="48" height="48" /><div><div className="wordmark">SIFT</div><small>Semantic Intelligence<br />for Files &amp; Topics</small></div></div>
        <nav className="nav" aria-label="Main navigation"><button aria-current="page" className="active" onClick={() => { clearSearch(); changeFilter(''); browseLibrary(); }}>Library <span className="nav-count">{libraryTotal}</span></button><button onClick={browseFolders}>Your folders</button><button onClick={() => setDiscoveryOpen(true)}>Find with SIFT</button></nav>
        <div className="header-right"><span className="local"><span className="status-dot active" />On this device</span><button className="motion-button" aria-pressed={reduceMotion} onClick={() => setReduceMotion(value => !value)} title={reduced && !reduceMotion ? 'Your system has reduced motion enabled' : undefined}><span className="switch" aria-hidden="true" />Reduce motion</button></div>
      </header>
      <section className="hero" aria-labelledby="library-heading"><div className="hero-art" aria-hidden="true" /><div className="hero-copy reveal"><p className="eyebrow"><Icon name="sparkles" small />A quieter place for your documents</p><h1 ref={heading} id="library-heading" tabIndex={-1}><span>Stop Searching.</span><span className="gradient-text">Start Studying.</span></h1><p className="hero-description">Your PDFs, notes and documents,<br />together on this device.</p><div className="hero-actions"><button className="button button-primary" onClick={addFolder} disabled={busy}><Icon name="folderPlus" small />Add a folder<Icon name="arrowRight" small /></button><button className="button" onClick={browseLibrary}>Browse your library<Icon name="arrowDown" small /></button></div><p className="hero-note"><Icon name="shield" small />Local files. Your folders. Always within reach.</p></div><p className="scene-note" aria-hidden="true">A little clarity, after dark.</p></section>
      <div className="content">
        <div className="search-wrap"><span className="search-hint">A word, a filename, a place to begin.</span><form className="search-form" role="search" onSubmit={event => { event.preventDefault(); search(); }}>
          <Icon name="search" /><input ref={searchInput} type="search" aria-label="Search words or filenames in your library" placeholder="Search words or filenames" value={query} onChange={event => setQuery(event.target.value)} maxLength={200} />
          {!activeQuery && <span className="key-hint">Ctrl K</span>}<button className="button button-small search-action" type="submit" disabled={!query.trim()}>Search</button>{activeQuery && <button type="button" className="icon-button" onClick={clearSearch} aria-label="Clear search"><Icon name="close" small /></button>}
          <button type="button" className="icon-button discovery-entry" aria-label="Find files with SIFT" title="Conversational file discovery" onClick={() => setDiscoveryOpen(true)}><Icon name="chat" small /></button>
          <button type="button" className="effects-toggle" role="switch" aria-checked={effects && !reduced} aria-label="Leaves, rain and wind effects" disabled={reduced} title={reduced ? 'Effects are off while reduced motion is enabled' : `Turn leaves, rain and wind ${effects ? 'off' : 'on'}`} onClick={() => setEffects(value => !value)}><Icon name="leaf" small /><span>Effects {effects && !reduced ? 'on' : 'off'}</span><span className="switch" aria-hidden="true" /></button>
          <button type="button" className="icon-button compact-folders" aria-label="Show approved folders" onClick={() => setFoldersOpen(true)}><Icon name="folder" small /></button>
        </form></div>
        {notice && <div className={`notice ${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'}><Icon name={notice.tone === 'error' ? 'alert' : 'info'} small /><span>{notice.text}</span><button className="icon-button" onClick={() => setNotice(null)} aria-label="Dismiss message"><Icon name="close" small /></button></div>}
        <div className="grid-layout">
          <FolderPanel folders={folders} busy={busy} scanning={scanning} compact={compact} open={foldersOpen} onClose={() => setFoldersOpen(false)} onAdd={addFolder} onScan={scan} onState={folderState} />
          <div className="library-main">
      {job && <section className="scan-card glass" aria-label="Latest scan"><div className="scan-heading"><span className={`scan-symbol ${scanning ? 'running' : job.state === 'failed' ? 'failed' : ''}`}><Icon name={scanning ? 'refresh' : job.state === 'failed' ? 'alert' : job.state === 'cancelled' ? 'close' : 'check'} small className={scanning ? 'spin' : ''} /></span><div className="scan-heading-copy" aria-live="polite"><h2>{jobTitle(job, cancelling)}</h2><p>{scanning ? `${job.processed} of ${job.total || '…'} files processed` : `${job.processed} files processed · ${formatDate(job.finished_at)}`}</p></div>{scanning ? <button className="button button-ghost" disabled={busy || cancelling} onClick={cancelScan}>{cancelling ? 'Cancelling…' : 'Cancel scan'}</button> : <button className="button button-ghost button-small" disabled={busy || !activeCount} onClick={() => scan()}><Icon name="refresh" small />Rescan</button>}</div>
        {scanning && <><progress aria-label="Scan progress" max={Math.max(job.total, 1)} value={job.total ? job.processed : undefined} />{job.current_path && <div className="current-path" title={job.current_path}>{shortPath(job.current_path)}</div>}</>}
        <details className="scan-notices"><summary>{scanning ? 'Scan details' : 'View scan summary'}{job.errors.length > 0 ? ` · ${job.errors.length}${job.errors.length === 500 ? '+' : ''} notices` : ''}</summary><div className="scan-metrics">{(['created', 'changed', 'moved', 'unchanged', 'missing', 'failed', 'skipped'] as const).map(key => <span key={key}><strong>{job[key]}</strong>{key === 'created' ? 'new' : key}</span>)}</div>{job.errors.length > 0 && <div className="job-errors">{job.errors.map((error, index) => <div key={`${error.path}-${index}`}><strong title={error.path}>{shortPath(error.path)}</strong><span>{error.message}</span></div>)}</div>}{job.errors.length === 500 && <p className="library-description">The first 500 notices are shown.</p>}</details>{job.error && <p className="error-text">{job.error}</p>}
      </section>}
      <section id="library" className="library-panel glass" aria-busy={pageBusy}><div className="library-toolbar"><div><div className="library-title"><h2 id="library-title">{activeQuery ? 'Search results' : 'Your documents'}</h2><span className="count-pill">{visibleTotal}</span></div><p className="library-description" aria-live="polite">{activeQuery ? searching ? 'Refreshing matches…' : `Matches for “${activeQuery}” in filenames and document text.` : 'A place for every note. Without moving a file.'}</p></div><div className="library-toolbar-actions">{!job && <button className="button button-ghost button-small" onClick={() => scan()} disabled={busy || scanning || !activeCount}><Icon name="refresh" small />Rescan</button>}<button className="button button-primary button-small" onClick={addFolder} disabled={busy}><Icon name="plus" small /><span className="action-label">Add folder</span></button></div></div>
        {!activeQuery && <div className="filter-row"><label htmlFor="file-filter">Show</label><select id="file-filter" className="filter-select" value={status} onChange={event => changeFilter(event.target.value as FileStatus)}><option value="">All files</option><option value="indexed">Indexed</option><option value="error">Needs attention</option><option value="missing">Missing</option><option value="excluded">Excluded</option></select><span className="formats">PDF · DOCX · TXT</span></div>}
        <div className="table-head"><span>DOCUMENT</span><span className="status-heading">STATUS</span><span className="date-heading">{activeQuery ? 'MATCH' : 'INDEXED'}</span><span /></div>
        {(loading && !activeQuery) || (searching && !results && activeQuery) ? <div className="loading-state" role="status"><Icon name="refresh" className="spin" small />{activeQuery ? 'Looking through your library…' : 'Opening your library…'}</div> : activeQuery ? <>
          {results?.items.map(result => <button key={result.id} className="file-row" onClick={() => showDocument(result.id)} disabled={busy}><span className="file-main"><span className={`file-icon ${result.filename.split('.').pop()?.toLowerCase()}`}><Icon name="file" small />{result.filename.split('.').pop()?.toUpperCase()}</span><span className="file-copy"><span className="file-name">{result.filename}</span><span className="file-subtitle">{snippet(result.snippet || shortPath(result.path))}</span></span></span><span className="status-badge indexed"><span className="status-dot indexed" />Indexed</span><span className="file-date">{result.match_kind === 'filename' ? 'Filename' : 'Content'}</span><Icon name="chevronRight" small className="file-chevron" /></button>)}
          {results?.items.length === 0 && <div className="empty-state"><div className="empty-symbol"><Icon name="search" /></div><h3>No matches this time.</h3><p>Try a different word or filename. Search currently matches words in extracted text; scanned pages may have no searchable text.</p><button className="button button-secondary" onClick={() => searchInput.current?.focus()}>Try another search</button></div>}
        </> : <>
          {files.map(file => <button className="file-row" key={file.id} onClick={() => showDocument(file.id)} disabled={busy}><span className="file-main"><span className={`file-icon ${file.extension.slice(1).toLowerCase()}`}><Icon name="file" small />{file.extension.slice(1).toUpperCase()}</span><span className="file-copy"><span className="file-name">{file.filename}</span><span className="file-subtitle" title={file.path}>{shortPath(file.path)}{file.duplicate_of ? ' · Duplicate content' : ''}{file.warning_count ? ` · ${file.warning_count} extraction ${file.warning_count === 1 ? 'note' : 'notes'}` : ''}</span></span></span><span className={`status-badge ${file.status}`}><span className={`status-dot ${file.status}`} />{statusName(file.status)}</span><span className="file-date" title={formatDate(file.indexed_at)}>{formatDate(file.indexed_at, true)}</span><Icon name="chevronRight" small className="file-chevron" /></button>)}
          {files.length === 0 && <div className="empty-state"><div className="empty-symbol"><Icon name="folderOpen" /></div><h3>{status ? 'No files with this status.' : folders.length ? 'Your collection is taking shape.' : 'Your library starts with a folder.'}</h3><p>{status ? 'Choose another filter to see more of your library.' : folders.length ? 'Rescan an active folder to bring PDF, Word, and text documents into your library.' : 'Choose a folder of PDFs, DOCX files or text notes. We will bring them together, right here on your device.'}</p>{!status && <button className="button button-primary" onClick={folders.length && activeCount ? () => scan() : addFolder} disabled={busy || scanning}><Icon name={folders.length && activeCount ? 'refresh' : 'folderPlus'} small />{folders.length && activeCount ? 'Scan your folders' : folders.length ? 'Add a folder' : 'Add your first folder'}</button>}</div>}
        </>}
        <div className="pager"><span>{visibleTotal ? `${pageOffset + 1}–${Math.min(pageOffset + pageLength, visibleTotal)} of ${visibleTotal}` : '0'} {activeQuery ? 'matches' : 'documents'}</span><div className="pager-actions"><button className="button button-ghost" disabled={pageBusy || pageOffset === 0} onClick={() => changePage(Math.max(0, pageOffset - pageSize))}><Icon name="chevronLeft" small />Previous</button><button className="button button-ghost" disabled={pageBusy || pageOffset + pageLength >= visibleTotal} onClick={() => changePage(pageOffset + pageSize)}>Next<Icon name="chevronRight" small /></button></div></div>
      </section>
          </div>
        </div>
        <footer className="workspace-footer"><Icon name="lock" small />Stored locally. Ready when you are.</footer>
      </div>
      {showTop && <button className="back-to-top" aria-label="Back to top" onClick={event => backToTop(event.detail === 0)}><Icon name="arrowUp" small /></button>}
    </main>
    {discoveryOpen && <DiscoveryPanel folders={folders} revision={JSON.stringify([job?.id, job?.state, job?.finished_at])} onClose={() => setDiscoveryOpen(false)} onPreview={previewDiscovery} />}
    {selected && <DocumentDrawer document={selected} busy={busy} returnFocus={documentTrigger.current} onClose={closeDocument} onOpen={() => void action(() => window.sift.openDocument(selected.id))} onReveal={() => void action(() => window.sift.revealDocument(selected.id))} />}
  </div>;
}
