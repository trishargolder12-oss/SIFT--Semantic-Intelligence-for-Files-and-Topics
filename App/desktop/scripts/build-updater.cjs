const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const desktop = path.resolve(__dirname, '..');
const root = path.resolve(desktop, '..');
const pkg = require('../package.json');
const release = path.join(desktop, 'release');
const installer = path.join(release, pkg.version, `SIFT Setup ${pkg.version}.exe`);
if (!fs.existsSync(installer)) throw new Error('Build the current installer before refreshing the updater');
const previous = path.join(release, 'latest.json');
if (fs.existsSync(previous)) {
  const old = JSON.parse(fs.readFileSync(previous, 'utf8')).version.split('.').map(Number);
  const now = pkg.version.split('.').map(Number);
  const diff = now.map((n, i) => n - old[i]).find(n => n !== 0) || 0;
  if (diff < 0) throw new Error('Refusing to replace a newer update manifest');
}
const manifest = { appId: pkg.build.appId, version: pkg.version,
  installer: `${pkg.version}/SIFT Setup ${pkg.version}.exe`,
  sizeBytes: fs.statSync(installer).size,
  sha256: crypto.createHash('sha256').update(fs.readFileSync(installer)).digest('hex') };
const python = path.join(root, 'backend/.venv/Scripts/python.exe');
const result = spawnSync(python, ['-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
  '--name', 'SIFT Updater', '--icon', path.join(desktop, 'build/sift.ico'),
  '--distpath', release, '--workpath', path.join(root, 'updater/build'),
  '--specpath', path.join(root, 'updater/build'), path.join(root, 'updater/sift_updater.py')], { stdio: 'inherit' });
if (result.status !== 0) process.exit(result.status || 1);
fs.writeFileSync(previous + '.tmp', JSON.stringify(manifest, null, 2) + '\n');
const verified = spawnSync(path.join(release, 'SIFT Updater.exe'), ['--verify-only', '--manifest', previous + '.tmp'], { stdio: 'inherit' });
if (verified.status !== 0) throw new Error('Frozen updater validation failed; latest.json was not updated');
fs.renameSync(previous + '.tmp', previous);
const updater = path.join(release, 'SIFT Updater.exe');
fs.writeFileSync(updater + '.sha256', crypto.createHash('sha256').update(fs.readFileSync(updater)).digest('hex') + '  SIFT Updater.exe\n');
const bundle = spawnSync(python, [path.join(root, 'updater/package_bundle.py'), release], { stdio: 'inherit' });
if (bundle.status !== 0) throw new Error('Offline update bundle creation failed');
console.log(`Offline updater refreshed for SIFT ${pkg.version}`);
