import { memo, useEffect, useState, type CSSProperties } from 'react';

type ParticleStyle = CSSProperties & Record<`--${string}`, string>;
// Match the desktop app's leaves, rain and wind, including its slow timing.
const leaves = [[3, 13, 29, 7], [23, 10, 35, 19], [44, 11, 31, 12], [65, 14, 38, 29], [79, 10, 33, 4], [90, 12, 41, 23]];
const rain = [8, 17, 26, 34, 43, 51, 60, 69, 78, 86, 93, 6, 38, 57, 74, 99];
const wind = [[28, 26, 6], [63, 33, 19], [85, 29, 12]];

export function useAmbientPreference() {
  const [enabled, setEnabled] = useState(true);
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    try { setEnabled(localStorage.getItem('sift.website.effects') !== 'off'); } catch { /* Usable without storage. */ }
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const toggle = () => setEnabled(current => {
    try { localStorage.setItem('sift.website.effects', current ? 'off' : 'on'); } catch { /* Session-only preference. */ }
    return !current;
  });
  return { enabled, reduced, toggle };
}

export const AmbientEffects = memo(function AmbientEffects({ enabled }: { enabled: boolean }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    update(); document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  const active = enabled && visible;
  return <div className="weather-layer" aria-hidden="true" hidden={!active}>
    {active && <><div className="rain-field">{rain.map((x, i) => <i key={i} className="raindrop" style={{ '--x': `${x}%`, '--length': `${28 + i % 4 * 9}px`, '--duration': `${3.8 + i % 5 * .6}s`, '--delay': `-${i * .73}s` } as ParticleStyle} />)}</div>
      {leaves.map(([x, size, duration, delay], i) => <i key={i} className="leaf" style={{ '--x': `${x}%`, '--size': `${size}px`, '--duration': `${duration}s`, '--delay': `-${delay}s` } as ParticleStyle} />)}
      {wind.map(([y, duration, delay], i) => <i key={i} className="wind-trail" style={{ '--y': `${y}%`, '--duration': `${duration}s`, '--delay': `-${delay}s` } as ParticleStyle} />)}</>}
  </div>;
});
