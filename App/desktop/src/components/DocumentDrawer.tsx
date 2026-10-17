import { useEffect, useRef } from 'react';
import type { DocumentDetail } from '../types';
import { Icon } from './Icon';

function date(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not indexed';
}

function fileSize(size: number | null) {
  if (size === null) return 'Unavailable';
  if (size < 1024) return `${size} bytes`;
  return size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentDrawer({ document: item, busy, returnFocus, onClose, onOpen, onReveal }: {
  document: DocumentDetail; busy: boolean; returnFocus: HTMLElement | null; onClose: () => void; onOpen: () => void; onReveal: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = returnFocus || window.document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal();
    closeButton.current?.focus();
    return () => { element.close(); previous?.focus(); };
  }, [returnFocus]);
  const kind = item.extension.slice(1).toLowerCase();

  return <dialog ref={dialog} className="detail-dialog" aria-labelledby="document-title" onKeyDown={event => {
    if (event.key !== 'Tab') return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), summary, [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')).filter(element => element.getClientRects().length);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && window.document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && window.document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }} onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => {
    if (event.target === event.currentTarget) {
      const box = event.currentTarget.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) onClose();
    }
  }}>
    <header className="detail-header"><span>Document details</span><button ref={closeButton} className="icon-button" onClick={onClose} aria-label="Close document details"><Icon name="close" /></button></header>
    <div className="detail-content">
      <div className="detail-file-heading"><div className={`file-icon ${kind}`}><Icon name="file" />{kind.toUpperCase()}</div><div><h2 id="document-title">{item.filename}</h2><span className={`status-badge ${item.status}`}><span className={`status-dot ${item.status}`} />{item.status === 'indexed' ? 'Indexed' : item.status === 'error' ? 'Needs attention' : item.status === 'missing' ? 'Missing' : 'Excluded'}</span></div></div>
      <p className="detail-path">{item.path}</p>
      <div className="detail-actions"><button className="button button-primary" disabled={busy || item.status !== 'indexed'} onClick={onOpen}><Icon name="external" small />Open original</button><button className="button button-secondary" disabled={busy || item.status !== 'indexed'} onClick={onReveal}><Icon name="folderOpen" small />Show in folder</button></div>
      {item.error && <div className="detail-callout">{item.error}</div>}
      {item.status !== 'indexed' && item.blocks.length > 0 && <div className="detail-callout info">This is the text from the last successful scan. It may be out of date.</div>}
      {item.duplicate_of && <div className="detail-callout info">This file has the same content as another document in your library (file #{item.duplicate_of}).</div>}
      {item.warnings.length > 0 && <div className="detail-callout"><strong>Extraction notes</strong>{item.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</div>}
      <dl className="detail-metadata"><div><dt>Last indexed</dt><dd>{date(item.indexed_at)}</dd></div><div><dt>File size</dt><dd>{fileSize(item.size)}</dd></div></dl>
      <details className="technical-details"><summary>File identity and history</summary><p>SHA-256: {item.content_hash || 'Unavailable'}</p>{item.path_history.map((move, index) => <p key={`${move.moved_at}-${index}`}>Moved from {move.old_path}<br />{date(move.moved_at)}</p>)}</details>
      <h3>{item.status === 'indexed' ? 'Inside this document' : 'Last extracted text'}</h3>
      {item.blocks.length ? item.blocks.map(block => <section className="text-block" key={block.position}><div className="block-location"><Icon name="file" small />{block.location || 'Text'}</div><p>{block.text}</p></section>) : <p className="library-description">No text was extracted from this file.</p>}
    </div>
  </dialog>;
}
