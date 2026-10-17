import type { ReactNode } from 'react';
const paths: Record<string, ReactNode> = {
  coffee: <><path d="M4 8h12v8a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V8Zm12 1h2a3 3 0 0 1 0 6h-2M3 22h16M7 3v2m4-3v3m4-2v2" /></>,
  instagram: <><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4" /><circle cx="17.5" cy="6.5" r=".8" fill="currentColor" stroke="none" /></>,
  leaf: <><path d="M20 3C10 2 3 7 4 14s12 8 15-2c1-3 1-6 1-9Z" /><path d="M3 22 16 8M8 16v-5m4 1h5" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  down: <path d="M12 3v13m-5-5 5 5 5-5M4 18v3h16v-3" />,
  up: <path d="M12 20V4m-6 6 6-6 6 6" />,
  play: <path d="m8 4 13 8-13 8V4Z" fill="currentColor" strokeWidth="0" />,
  folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm0 4h18" />,
  search: <><circle cx="10" cy="10" r="6.5" /><path d="m15 15 6 6" /></>,
  shield: <><path d="m12 3 9 4v5c0 5-9 10-9 10S3 17 3 12V7l9-4Z" /><path d="m8 12 3 3 5-6" /></>,
  file: <><path d="M5 3h9l5 5v13H5V3Zm9 0v6h5M9 13h6m-6 4h6" /></>,
  refresh: <><path d="M20 5v6h-6M4 19v-6h6" /><path d="M19 10a7 7 0 0 0-12-5L4 8m16 8-3 3A7 7 0 0 1 5 14" /></>,
  spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM21 2v4M19 4h4" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  moon: <path d="M20.5 13A8.5 8.5 0 0 1 11 3.5 8.5 8.5 0 1 0 20.5 13Z" />,
  windows: <path d="m3 5 8-1v8H3V5Zm10-1 8-1v9h-8V4ZM3 14h8v8l-8-1v-7Zm10 0h8v9l-8-1v-8Z" fill="currentColor" stroke="none" />,
  chevron: <path d="m8 4 8 8-8 8" />,
  expand: <path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" />,
};
export function Icon({ name, className = '' }: { name: string; className?: string }) {
  return <svg className={`icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.spark}</svg>;
}
