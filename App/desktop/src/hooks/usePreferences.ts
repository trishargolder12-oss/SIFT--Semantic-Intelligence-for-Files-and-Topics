import { useEffect, useState } from 'react';

function readPreference(key: string, fallback: boolean) {
  try { const value = localStorage.getItem(key); return value === null ? fallback : value === 'on'; }
  catch { return fallback; }
}

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const media = matchMedia(query);
    const update = () => setMatches(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [query]);
  return matches;
}

function usePreference(key: string, fallback: boolean) {
  const [value, setValue] = useState(() => readPreference(key, fallback));
  useEffect(() => { try { localStorage.setItem(key, value ? 'on' : 'off'); } catch { /* Settings remain usable without storage. */ } }, [key, value]);
  return [value, setValue] as const;
}

export function usePreferences() {
  const systemReduced = useMediaQuery('(prefers-reduced-motion: reduce)');
  const [reduceMotion, setReduceMotion] = usePreference('sift.reduceMotion', false);
  const [effects, setEffects] = usePreference('sift.weatherEffects', true);
  return { reduceMotion, setReduceMotion, reduced: systemReduced || reduceMotion, effects, setEffects };
}
