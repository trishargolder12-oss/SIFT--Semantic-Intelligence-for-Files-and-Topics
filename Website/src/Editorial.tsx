import type { Page } from './pages';
import { Icon } from './icons';

const writing = {
  features: {
    eyebrow: 'A LITTLE THEORY, MADE PRACTICAL',
    heading: 'Less time finding.', emphasis: 'More time understanding.',
    lead: 'Study materials tend to grow in every direction: a lecture PDF here, a Word document there, a text note saved in a hurry. SIFT gives those scattered materials a shared place to be found, while your folders remain your own.',
    sections: [
      ['A library is a map', 'SIFT builds a separate local index of supported documents. Think of it as a map of the words in your files, rather than a new set of folders you have to maintain. You can search across the library without first remembering which subject folder holds a passage.'],
      ['Useful search starts with a clue', 'A distinctive word, a phrase from a lecture, or part of a filename gives exact-term search somewhere to begin. The current core library searches extracted text; image-only scans may have no searchable words. Find with SIFT adds conversational discovery and editable virtual sections. Optional local models add meaning retrieval; a separate OCR pack can make scanned pages searchable.'],
      ['Control belongs with you', 'Only approved folders belong in the library. Monitoring helps keep the index current, and scan controls let you pause or rescan when needed. Your original documents stay in place. The aim is a quieter workflow, with fewer decisions between a question and your notes.'],
    ], quote: 'A place to find your work. Space to think about it.', link: '/how-it-works.html', linkText: 'See how the library works',
  },
  'how-it-works': {
    eyebrow: 'WHAT HAPPENS BEHIND THE SCENES',
    heading: 'A small index.', emphasis: 'A clearer starting point.',
    lead: 'You do not need to reorganize an entire semester before you can use SIFT. Start with one folder you trust, let the library read its supported documents, and search for a word you already remember.',
    sections: [
      ['1. A boundary you choose', 'The folder picker defines the scope of your library. SIFT works within approved folders, so the starting point is deliberate. A course folder or a collection of revision notes is a useful first step.'],
      ['2. A separate local index', 'SIFT extracts readable text and file metadata into its own local library. PDF, DOCX, and TXT are supported by the core indexer. The index is separate from the originals; SIFT does not rename, move, or rewrite your study documents.'],
      ['3. Search, then return to the source', 'Search a filename or a phrase, or ask Find with SIFT for a document. Source excerpts explain matches. Syllabus collections and virtual sections help organize the library while leaving originals in place. Monitoring and rescans keep approved folders current.'],
    ], quote: 'Start with one folder. Follow one useful clue.', link: '/preview.html', linkText: 'Look inside the app',
  },
  preview: {
    eyebrow: 'A WORKSPACE WITH A PURPOSE',
    heading: 'Familiar files.', emphasis: 'A calmer way through.',
    lead: 'The gallery shows captures from the SIFT desktop renderer with synthetic documents. It is a view of the interface you are exploring, rather than a connection to files on your computer.',
    sections: [
      ['Your folders, in context', 'The library view keeps approved folders beside the document list. Scan status, supported file types, and document states help explain what is in the index and what may need attention.'],
      ['A visible path back to your notes', 'Search sits close to the library, so looking for a word and reviewing a document feel like parts of the same task. The room artwork provides atmosphere; stable navy reading surfaces keep the practical information clear.'],
      ['Know which build you are viewing', 'These captures show the local 0.4.3 renderer with synthetic documents. Public beta 0.3.3 already includes discovery and syllabus collections. The newer 0.4.3 explanation opt-in, progress, and model-loading changes belong to the local build; the download page labels each version separately.'],
    ], quote: 'Atmosphere around the work. Clarity where you read.', link: '/features.html', linkText: 'Explore the core features',
  },
  download: {
    eyebrow: 'A THOUGHTFUL FIRST INSTALL',
    heading: 'Know the build.', emphasis: 'Keep your bearings.',
    lead: 'A download should tell you what you are getting. SIFT keeps release details together so the installer, version, and published information can be checked as one coherent release.',
    sections: [
      ['A complete Windows package', 'The public Windows x64 beta installer includes the desktop application and its local service. The packaged app is designed to run without separately installing Python or Node.js. The current public installer is 0.3.3. The complete local 0.4.3 build is listed separately and has not been uploaded.'],
      ['Details you can verify', 'The public download information includes its version, installer size, release date, signing status, and SHA-256 checksum. A checksum helps confirm that a downloaded file matches the published artifact.'],
      ['Your library comes next', 'After installation, choose the folders you want to include. SIFT builds a local index while keeping the originals in place. Start small, try a familiar filename or phrase, and expand your library when the workflow feels comfortable.'],
    ], quote: 'A clear release. A considered beginning.', link: '/how-it-works.html', linkText: 'Read the setup guide',
  },
};

export function PageBackdrop({ page }: { page: Page }) {
  if (page === 'home') return <div className="home-scroll-backdrop" aria-hidden="true" />;
  const images = { features: 'features-library.png', 'how-it-works': 'how-it-works-desk.png', preview: 'preview-window.png', download: 'download-nightstand.png' };
  return <div className={`page-backdrop backdrop-${page}`} aria-hidden="true"><img src={`/assets/${images[page]}`} width="1200" height="800" alt="" decoding="async" fetchPriority="low" /></div>;
}

export function Editorial({ page }: { page: Exclude<Page, 'home'> }) {
  const content = writing[page];
  return <section className="section editorial" aria-labelledby={`${page}-story-title`}><div className="editorial-heading reveal"><p className="eyebrow"><span>✦</span> {content.eyebrow}</p><h2 id={`${page}-story-title`}>{content.heading}<br /><span className="gradient-text">{content.emphasis}</span></h2><p>{content.lead}</p></div><div className="editorial-layout"><div className="editorial-body">{content.sections.map(([title, text], i) => <article className="editorial-chapter reveal" key={title} style={{ '--delay': `${i * 70}ms` } as React.CSSProperties}><span className="chapter-dot" aria-hidden="true" /><h3>{title}</h3><p>{text}</p></article>)}</div><aside className="editorial-aside reveal"><Icon name="moon" /><p>{content.quote}</p><span>SIFT / A LITTLE CLARITY, AFTER DARK</span><a className="text-link" href={content.link}>{content.linkText}<Icon name="arrow" /></a></aside></div></section>;
}
