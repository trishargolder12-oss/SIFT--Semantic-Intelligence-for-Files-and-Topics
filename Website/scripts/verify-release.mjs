import { readFile } from 'node:fs/promises';
import { existsSync, createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
const release = JSON.parse(await readFile('public/release.json', 'utf8'));
const assert = (condition, message) => { if (!condition) throw new Error(message); };
assert(['coming-soon', 'published'].includes(release.status), 'Unknown release state');
assert(release.platform === 'Windows' && release.architecture === 'x64', 'Only verified Windows x64 is configured');
assert(release.releaseNotesUrl === '/release-notes.html', 'Keep the implemented release notes destination');
if (release.status === 'published') {
  assert(release.approved === true, 'A public release must be explicitly approved');
  assert(/^\d+\.\d+\.\d+/.test(release.version || ''), 'Version is required');
  assert(/^https:\/\/[^\s]+$/.test(release.downloadUrl || ''), 'A real HTTPS artifact URL is required');
  assert(release.installerFilename?.endsWith('.exe'), 'Windows installer filename required');
  assert(Number.isSafeInteger(release.sizeBytes) && release.sizeBytes > 0, 'Exact installer byte size required');
  assert(/^[a-f0-9]{64}$/i.test(release.sha256 || ''), 'Verified SHA-256 required');
  assert(/^\d{4}-\d{2}-\d{2}$/.test(release.releaseDate || ''), 'Approved release date required');
  assert(['signed', 'unsigned'].includes(release.signingStatus), 'Signing status required');
  const url = new URL(release.downloadUrl);
  assert(url.origin === 'https://github.com' && url.pathname === `/trishargolder12-oss/SIFT--Semantic-Intelligence-for-Files-and-Topics/releases/download/v${release.version}/SIFT-Setup.exe`, 'Download must target the exact versioned SIFT GitHub release asset');
  console.log(`Release metadata complete: ${release.version}. Verify remote artifact and acceptance before deployment.`);
} else {
  assert(!release.approved && !release.downloadUrl, 'Coming-soon releases must not expose a download');
  console.log('Release state verified: coming soon; internal candidate is not distributed.');
}
const candidate = release.candidate;
assert(/^\d+\.\d+\.\d+$/.test(candidate.version), 'Local build version required');
assert(candidate.approved === false, 'Local-only build must not be presented as an approved public download');
assert(Number.isSafeInteger(candidate.sizeBytes) && candidate.sizeBytes > 0 && /^[a-f0-9]{64}$/i.test(candidate.sha256), 'Local installer size and SHA-256 required');
const manifestUrl = new URL('../../desktop/release/latest.json', import.meta.url);
if (existsSync(manifestUrl)) {
  const manifest = JSON.parse(await readFile(manifestUrl, 'utf8'));
  assert(candidate.version === manifest.version && candidate.sha256 === manifest.sha256 && candidate.sizeBytes === manifest.sizeBytes, 'Website local build must match the current updater manifest');
  const installerUrl = new URL(manifest.installer, manifestUrl);
  const hash = createHash('sha256');
  let bytes = 0;
  for await (const chunk of createReadStream(installerUrl)) { hash.update(chunk); bytes += chunk.length; }
  assert(bytes === candidate.sizeBytes && hash.digest('hex') === candidate.sha256, 'Local installer bytes must match website metadata');
  console.log(`Local installer ${candidate.version} independently verified against the manifest and file bytes.`);
}
