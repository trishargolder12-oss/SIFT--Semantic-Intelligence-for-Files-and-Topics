import type { ReactNode } from 'react';

const paths = {
  chat: <><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-3 3V11.5A8.5 8.5 0 0 1 9.5 3h3a8.5 8.5 0 0 1 8.5 8.5Z" /><path d="M7 10h9M7 14h6" /></>,
  edit: <><path d="m15 4 5 5M4 20l4-1L21 6l-5-5L3 14l1 6Z" /></>,
  send: <><path d="m3 3 19 9-19 9 4-9-4-9ZM7 12h15" /></>,
  book: <><path d="M12 7c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V6c-3-1-6-1-9 1Z" /><path d="M12 7v14M6 10h3M15 10h3M6 14h3M15 14h3M8 2v2M16 2v2" /></>,
  library: <><path d="M4 5v15M8 5v15M12 5v15M16 4l5 15-4 1-5-15 4-1Z" /></>,
  folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
  folderOpen: <><path d="M3 11V6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v3" /><path d="M3 11h19l-3 10H5L3 11Z" /></>,
  folderPlus: <><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /><path d="M12 11v6M9 14h6" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  shield: <><path d="M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7l-9-4Z" /><path d="m8 12 3 3 5-6" /></>,
  moon: <path d="M20.5 13A8.5 8.5 0 0 1 11 3.5 8.5 8.5 0 1 0 20.5 13Z" />,
  sparkles: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4M18 4h4" /></>,
  files: <><path d="M8 3h8l4 4v13a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M16 3v5h4M4 6v12M10 12h7M10 16h5" /></>,
  file: <><path d="M6 3h9l5 5v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M15 3v6h5M8 13h8M8 17h6" /></>,
  fileCheck: <><path d="M6 3h9l5 5v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M15 3v6h5m-12 6 3 3 5-6" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  arrowRight: <path d="M4 12h16m-6-6 6 6-6 6" />,
  arrowDown: <path d="M12 4v16m-6-6 6 6 6-6" />,
  leaf: <><path d="M20 4c-7-1-15 2-15 9a6 6 0 0 0 6 6c7 0 10-8 9-15Z" /><path d="M4 21 15 10" /></>,
  arrowUp: <path d="M12 20V4m-6 6 6-6 6 6" />,
  chevronRight: <path d="m9 5 7 7-7 7" />,
  chevronLeft: <path d="m15 5-7 7 7 7" />,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M19 12a7 7 0 0 0-12-5L4 10m16 4-3 3a7 7 0 0 1-12-5" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  alert: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3v.1" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v.1" /></>,
  external: <><path d="M14 3h7v7M21 3l-9 9M10 3H4a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-6" /></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof paths;

export function Icon({ name, small = false, className = '' }: { name: IconName; small?: boolean; className?: string }) {
  return <svg className={`icon ${small ? 'sm' : ''} ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
