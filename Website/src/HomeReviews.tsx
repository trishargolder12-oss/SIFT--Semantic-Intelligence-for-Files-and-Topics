import { Icon } from './icons';
import site from '../public/site.json';

// Explicitly fictional promotional scenarios, not submitted customer reviews.
const examples = [
  { name: 'Amanda', context: 'During revision week', quote: 'I want to spend my evening understanding the chapter, not hunting for the right PDF.', detail: 'A useful place to begin: one phrase you remember, across the folders you approve.', icon: 'search' },
  { name: 'Sonia', context: 'With a growing course folder', quote: 'Keeping my folders as they are makes getting started feel less like another project.', detail: 'Your originals stay in place while SIFT builds a separate local library.', icon: 'folder' },
  { name: 'Alex', context: 'At the end of a long day', quote: 'A calm library for the notes I already have—that’s the space I want to study in.', detail: 'A midnight study-room interface, local processing, and room to focus.', icon: 'moon' },
];
export function HomeReviews() {
  return <section className="section home-reviews" aria-labelledby="reviews-title"><div className="reviews-heading reveal"><p className="eyebrow"><span>✦</span> STUDY STORIES</p><h2 id="reviews-title">Less searching.<br /><span className="gradient-text">More moments like these.</span></h2><p>Imagined study moments that capture the experience we’re building.</p></div><div className="review-grid">{examples.map((example, i) => <article className="review-card reveal" key={example.context} style={{ '--delay': `${i * 75}ms` } as React.CSSProperties}><span className="review-context"><Icon name={example.icon} />{example.context}</span><blockquote>“{example.quote}”</blockquote><p>{example.detail}</p><span className="review-label">{example.name}</span></article>)}</div><div className="reviews-note"><p>Amanda, Sonia, and Alex are fictional names. These are sample quotes, not submitted customer reviews.</p><a className="text-link" href={site.creatorUrl} target="_blank" rel="noopener noreferrer">Share your own experience<Icon name="arrow" /></a></div></section>;
}
