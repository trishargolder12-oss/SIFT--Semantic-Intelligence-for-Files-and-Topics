const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const backend = path.resolve(__dirname, '../../backend');
const venv = path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = fs.existsSync(venv) ? venv : (process.env.SIFT_PYTHON || 'python');
const args = [
  '-m', 'PyInstaller', '--onefile', '--name', 'sift-indexer',
  '--distpath', path.join(backend, 'dist'), '--workpath', path.join(backend, 'build'),
  '--specpath', path.join(backend, 'build'), path.join(backend, 'run_service.py'),
];
const result = spawnSync(python, args, { cwd: backend, stdio: 'inherit' });
process.exit(result.status ?? 1);
