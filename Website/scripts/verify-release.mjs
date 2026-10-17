import { readFile } from 'node:fs/promises';
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
