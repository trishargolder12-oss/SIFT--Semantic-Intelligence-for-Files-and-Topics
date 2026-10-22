import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { readFile, writeFile } from 'node:fs/promises';
import { publicOrigin, seoHead, sitemapXml } from './seo.mjs';
const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
try {
  const { App } = await server.ssrLoadModule('/src/App.tsx');
  const html = await readFile('dist/index.html', 'utf8');
  const { pages } = await server.ssrLoadModule('/src/pages.ts');
  const site = JSON.parse(await readFile('public/site.json', 'utf8'));
  const origin = publicOrigin(process.env.SITE_URL || site.siteUrl || (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : null));
  for (const [page, info] of Object.entries(pages)) {
    const markup = renderToString(createElement(App, { page }));
    const pageHtml = html.replace('<div id="root"></div>', `<div id="root">${markup}</div>`)
      .replace(/<title>.*?<\/title>/, `<title>${info.title}</title>`)
      .replace(/(<meta name="description" content=")[^"]*("\s*\/?>)/, `$1${info.description}$2`)
      .replace(/(<meta property="og:title" content=")[^"]*("\s*\/?>)/, `$1${info.title}$2`)
      .replace(/(<meta property="og:description" content=")[^"]*("\s*\/?>)/, `$1${info.description}$2`)
      .replace('</head>', `${seoHead({ page, info, site, origin })}\n</head>`);
    await writeFile(page === 'home' ? 'dist/index.html' : `dist${info.href}`, pageHtml);
  }
  // All displayed installer facts are derived from the one maintained manifest.
  const release = JSON.parse(await readFile('public/release.json', 'utf8'));
  const escape = value => String(value ?? 'Not configured').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
  const candidate = release.candidate;
  const artifact = (item, local = false) => {
    const fields = [['Version', item.version], ['Platform', `${item.platform} ${item.architecture}`], ['Filename', item.installerFilename], [local ? 'Built locally' : 'Published', local ? item.builtAt : item.releaseDate], ['Size', `${Number(item.sizeBytes).toLocaleString('en-US')} bytes`], ['Signing', item.signingStatus], ['SHA-256', item.sha256]];
    return fields.map(([key, value]) => `<dt>${escape(key)}</dt><dd>${key === 'SHA-256' ? `<code>${escape(value)}</code>` : escape(value)}</dd>`).join('');
  };
  let notes = await readFile('public/release-notes.html', 'utf8');
  notes = notes.replace(/<dl id="public-artifact">.*?<\/dl>/s, `<dl id="public-artifact">${artifact(release)}</dl>`);
  notes = notes.replace(/<dl id="local-artifact">.*?<\/dl>/s, `<dl id="local-artifact">${artifact(candidate, true)}</dl>`);
  const releaseSummary = release.status === 'published' ? `Public Windows release: ${escape(release.version)}.` : 'Public Windows download: coming soon.';
  const releaseBody = release.status === 'published' ? `Version ${escape(release.version)} · ${escape(release.sizeBytes)} bytes · Released ${escape(release.releaseDate)} · ${escape(release.signingStatus)}. See the download section for the installer and checksum.` : `${escape(release.message)} No release date has been announced.`;
  notes = notes.replace(/<div class="status">.*?<\/div>/s, `<div class="status"><strong>${releaseSummary}</strong><p>${releaseBody}</p></div>`);
  await writeFile('dist/release-notes.html', notes);
  const indexedPaths = [...Object.values(pages).map(info => info.href), '/release-notes.html', '/privacy.html', '/terms.html'];
  await writeFile('dist/robots.txt', `User-agent: *\nAllow: /\n${origin ? `Sitemap: ${origin}/sitemap.xml\n` : '# Configure SITE_URL at build time to generate the public sitemap.\n'}`);
  if (origin) await writeFile('dist/sitemap.xml', sitemapXml(origin, indexedPaths));
  console.log('Pre-rendered Home, Features, How It Works, Preview and Download as separate static pages.');
  console.log(origin ? 'Public canonical URLs, structured data and sitemap generated.' : 'Local preview SEO generated. Set SITE_URL for production canonicals and sitemap.');
} finally { await server.close(); }
