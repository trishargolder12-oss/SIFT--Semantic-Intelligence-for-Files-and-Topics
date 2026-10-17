import release from '../public/release.json';
export { release };
export const canDownload = release.status === 'published' && release.approved &&
  typeof release.downloadUrl === 'string' && /^https:\/\//.test(release.downloadUrl) &&
  typeof release.sha256 === 'string' && /^[a-f0-9]{64}$/i.test(release.sha256) &&
  typeof release.sizeBytes === 'number' && release.sizeBytes > 0;
export const downloadHref = canDownload ? String(release.downloadUrl) : '/download.html';
