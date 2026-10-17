import { useEffect, useRef, useState } from 'react';
import type { Folder } from '../types';
import { Icon } from './Icon';

function FolderDetails({ folder, busy, scanning, onClose, onScan, onState }: {
  folder: Folder; busy: boolean; scanning: boolean; onClose: () => void;
  onScan: (id: number) => void; onState: (id: number, state: 'active' | 'paused' | 'removed') => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element=dialog.current!, previous=document.activeElement as HTMLElement|null;
    element.showModal();
    return()=>{element.close();if(previous?.isConnected)previous.focus({preventScroll:true});};
  },[]);
  const name=folder.path.split(/[\\/]/).filter(Boolean).pop()||folder.path;
  return <dialog ref={dialog} className="folder-details-dialog" aria-labelledby="folder-details-title" onKeyDown={event=>{
    if(event.key!=='Tab')return;
    const controls=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
    const first=controls[0],last=controls[controls.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }} onCancel={event=>{event.preventDefault();event.stopPropagation();onClose();}} onClick={event=>{
    if(event.target!==event.currentTarget)return;
    const bounds=event.currentTarget.getBoundingClientRect();
    if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)onClose();
  }}>
    <header><h2 id="folder-details-title">{name}</h2><button className="icon-button" onClick={onClose} aria-label="Close folder details"><Icon name="close" small/></button></header>
    <dl><dt>Folder path</dt><dd>{folder.path}</dd><dt>Status</dt><dd>{folder.state==='active'?'Watching for changes':'Watching paused'}</dd><dt>Last scan</dt><dd>{folder.last_scan_at?new Date(folder.last_scan_at).toLocaleString():'Not yet'}</dd></dl>
    {folder.last_error&&<p className="error-text">{folder.last_error}</p>}
    <div className="folder-actions"><button className="text-button" disabled={busy||scanning||folder.state!=='active'} onClick={()=>{onScan(folder.id);onClose();}}>Rescan</button><button className="text-button" disabled={busy} onClick={()=>{onState(folder.id,folder.state==='active'?'paused':'active');onClose();}}>{folder.state==='active'?'Pause':'Resume'}</button><button className="text-button remove" disabled={busy} onClick={()=>{onState(folder.id,'removed');onClose();}}>Remove</button></div>
  </dialog>;
}

export function FolderPanel({ folders, busy, scanning, compact, open, onClose, onAdd, onScan, onState }: {
  folders: Folder[]; busy: boolean; scanning: boolean; compact: boolean; open: boolean;
  onClose: () => void; onAdd: () => void; onScan: (id: number) => void;
  onState: (id: number, state: 'active' | 'paused' | 'removed') => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const [detailsId,setDetailsId]=useState<number|null>(null);
  const details=folders.find(folder=>folder.id===detailsId);
  useEffect(() => {
    if (!compact || !open) return;
    const element = dialog.current!;
    const previous = document.activeElement as HTMLElement | null;
    element.showModal(); close.current?.focus();
    return () => { element.close(); if (previous?.isConnected) previous.focus({ preventScroll: true }); };
  }, [compact, open]);
  const content = <>
    <div className="panel-title"><h2 id="folders-title">Your study folders</h2><span className="count-pill">{folders.length}</span>{compact && <button ref={close} className="icon-button" onClick={onClose} aria-label="Close folders"><Icon name="close" small /></button>}</div>
    <div className="folder-list">
      {!folders.length && <p className="side-empty">A folder is all it takes.<br />Bring your study material together.</p>}
      {folders.map(folder => <article className="folder-card" key={folder.id} onContextMenu={event=>{event.preventDefault();setDetailsId(folder.id);}}>
        <h3><button className="folder-name" aria-haspopup="dialog" onClick={()=>setDetailsId(folder.id)} onKeyDown={event=>{
          if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){event.preventDefault();setDetailsId(folder.id);}
        }}><Icon name="folderOpen" /><span>{folder.path.split(/[\\/]/).filter(Boolean).pop() || folder.path}</span></button></h3>
      </article>)}
    </div>
    <button className="button folder-add" disabled={busy} onClick={onAdd}><Icon name="plus" small />Add a folder</button>
    <p className="folder-note"><Icon name="shield" small />SIFT only reads folders you choose.<br />Your originals stay where they are.</p>
    {details&&<FolderDetails key={details.id} folder={details} busy={busy} scanning={scanning} onClose={()=>setDetailsId(null)} onScan={onScan} onState={onState}/>}
  </>;
  if (!compact) return <aside id="folders" className="folders glass" aria-labelledby="folders-title">{content}</aside>;
  return <dialog ref={dialog} className="folder-dialog" aria-labelledby="folders-title" onKeyDown={event => {
    if (details || event.key !== 'Tab') return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')).filter(element => element.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }} onCancel={event => { if(event.target!==event.currentTarget)return; event.preventDefault(); onClose(); }} onClick={event => {
    if (event.target === event.currentTarget && event.clientX > event.currentTarget.getBoundingClientRect().right) onClose();
  }}>{content}</dialog>;
}
