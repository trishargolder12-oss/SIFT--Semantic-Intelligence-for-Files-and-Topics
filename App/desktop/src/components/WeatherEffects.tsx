import { memo, useEffect, useState, type CSSProperties } from 'react';

type ParticleStyle = CSSProperties & Record<`--${string}`, string>;
const leaves = [[3, 13, 29, 7], [23, 10, 35, 19], [44, 11, 31, 12], [65, 14, 38, 29], [79, 10, 33, 4], [90, 12, 41, 23]];
const rain = [8, 17, 26, 34, 43, 51, 60, 69, 78, 86, 93, 6, 38, 57, 74, 99];
const wind = [[28, 26, 6], [63, 33, 19], [85, 29, 12]];

export const WeatherEffects = memo(function WeatherEffects({ enabled }: { enabled: boolean }) {
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  // Unmount the particles when disabled so no animation work remains in the background.
  return <div className="weather-layer" aria-hidden="true" hidden={!enabled || !visible}>
    {enabled && visible && <>
      <div className="rain-field">{rain.map((x, i) => <i key={i} className="raindrop" style={{ '--x': `${x}%`, '--length': `${28 + i % 4 * 9}px`, '--duration': `${3.8 + i % 5 * .6}s`, '--delay': `-${i * .73}s` } as ParticleStyle} />)}</div>
      {leaves.map(([x, size, duration, delay], i) => <i key={i} className="leaf" style={{ '--x': `${x}%`, '--size': `${size}px`, '--duration': `${duration}s`, '--delay': `-${delay}s` } as ParticleStyle} />)}
      {wind.map(([y, duration, delay], i) => <i key={i} className="wind-trail" style={{ '--y': `${y}%`, '--duration': `${duration}s`, '--delay': `-${delay}s` } as ParticleStyle} />)}
    </>}
  </div>;
});
