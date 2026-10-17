import { useEffect, useRef, useState } from 'react';
import { Icon } from './icons';
import site from '../public/site.json';
import type { Page } from './pages';

const sessionKey = 'sift.coffee.seen';
function rememberVisit() { try { sessionStorage.setItem(sessionKey, 'yes'); } catch { /* Still bounded during this page visit. */ } }

export function CoffeePopup({ page, request, onClose }: { page: Page; request: number; onClose: () => void }) {
  const [open, setOpen] = useState(false);
  const [manual, setManual] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);
  const previous = useRef<HTMLElement | null>(null);
  const shown = useRef(false);
  useEffect(() => {
    if (!request) return;
    previous.current = document.activeElement as HTMLElement;
    shown.current = true; rememberVisit(); setManual(true); setOpen(true);
  }, [request]);
  useEffect(() => {
    if (page !== 'home') return;
    try { if (sessionStorage.getItem(sessionKey)) return; } catch { /* Session storage is optional. */ }
    let timer = 0;
    const show = () => {
      if (document.hidden || shown.current || document.querySelector('dialog[open]')) return;
      shown.current = true; rememberVisit(); setManual(false); setOpen(true);
    };
    const schedule = () => {
      clearTimeout(timer);
      if (!document.hidden && !shown.current) timer = window.setTimeout(show, site.coffeeAutoDelayMs);
    };
    schedule(); document.addEventListener('visibilitychange', schedule);
    return () => { clearTimeout(timer); document.removeEventListener('visibilitychange', schedule); };
  }, [page]);
  useEffect(() => { if (open && manual) closeButton.current?.focus(); }, [open, manual]);
  useEffect(() => {
    if (!open) return;
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !document.querySelector('dialog[open]')) { setOpen(false); if (manual) previous.current?.focus({ preventScroll: true }); onClose(); } };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [open, manual, onClose]);
  if (!open) return null;
  const support = typeof site.supportUrl === 'string' && /^https:\/\//.test(site.supportUrl) ? site.supportUrl : null;
  const close = () => { setOpen(false); if (manual) previous.current?.focus({ preventScroll: true }); onClose(); };
  return <aside className="coffee-popup" role="dialog" aria-modal="false" aria-labelledby="coffee-title"><button ref={closeButton} className="coffee-close" aria-label="Close coffee popup" type="button" onClick={close}><Icon name="close" /></button><div className="coffee-cup" aria-hidden="true"><Icon name="coffee" /><i /><i /><i /></div><p className="eyebrow">A SMALL THANK YOU</p><h2 id="coffee-title">Grab us a <span className="gradient-text">coffee?</span></h2><p>Made with care, for the moments when your notes need a little order. If SIFT feels like your kind of space, come say hello.</p><a className="button primary" href={support || site.creatorUrl} target="_blank" rel="noopener noreferrer">{support ? 'Support SIFT' : 'Say hello on Instagram'}<Icon name="arrow" /></a><button className="coffee-later" type="button" onClick={close}>Maybe later</button></aside>;
}
