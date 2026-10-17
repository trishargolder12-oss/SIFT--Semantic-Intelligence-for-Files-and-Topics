// Pure build-time SEO helpers: no browser scripts or invented production domain.
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
export function publicOrigin(value) {
  if (!value) return null;
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.pathname !== '/' || url.search || url.hash || url.username || url.password || ['localhost', '127.0.0.1'].includes(url.hostname)) {
    throw new Error('SITE_URL must be the real public HTTPS origin, without a path, credentials, query or hash.');
  }
  return url.origin;
}
export function seoHead({ page, info, site, origin }) {
  const url = origin ? new URL(info.href, origin).href : null;
  const creator = { '@type': 'Person', name: site.creatorName, sameAs: [site.creatorUrl] };
  const graph = [
    { '@type': 'WebSite', name: 'SIFT', description: 'A local Windows document library for study materials.', inLanguage: 'en', creator, ...(origin ? { '@id': `${origin}/#website`, url: `${origin}/` } : {}) },
    { '@type': 'WebPage', name: info.title, description: info.description, inLanguage: 'en', ...(url ? { '@id': `${url}#page`, url, isPartOf: { '@id': `${origin}/#website` } } : {}) },
  ];
  if (page === 'home') graph.push({ '@type': 'SoftwareApplication', name: 'SIFT', applicationCategory: 'EducationalApplication', operatingSystem: 'Windows', description: 'A local library that indexes PDF, DOCX and TXT files from user-approved folders and offers exact-term search.', creator, ...(origin ? { url: `${origin}/` } : {}) });
  if (page !== 'home' && origin) graph.push({ '@type': 'BreadcrumbList', itemListElement: [{ '@type': 'ListItem', position: 1, name: 'Home', item: `${origin}/` }, { '@type': 'ListItem', position: 2, name: info.label, item: url }] });
  const tags = [
    '<meta name="robots" content="index, follow, max-image-preview:large">',
    '<meta property="og:site_name" content="SIFT">',
    '<meta name="twitter:card" content="summary_large_image">',
    `<meta name="twitter:title" content="${escape(info.title)}">`,
    `<meta name="twitter:description" content="${escape(info.description)}">`,
  ];
  if (url) tags.push(`<link rel="canonical" href="${escape(url)}">`, `<meta property="og:url" content="${escape(url)}">`, `<meta property="og:image" content="${escape(origin)}/assets/study-room.webp">`, '<meta property="og:image:alt" content="SIFT midnight study room artwork">', `<meta name="twitter:image" content="${escape(origin)}/assets/study-room.webp">`);
  tags.push(`<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@graph': graph }).replaceAll('<', '\\u003c')}</script>`);
  return tags.join('\n');
}
export function sitemapXml(origin, paths) {
  const items = paths.map(path => `  <url><loc>${escape(new URL(path, origin).href)}</loc></url>`).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${items}\n</urlset>\n`;
}
