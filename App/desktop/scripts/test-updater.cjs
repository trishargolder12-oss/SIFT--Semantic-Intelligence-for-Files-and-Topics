const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const python = path.join(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const result = spawnSync(python, ['-m', 'pytest', path.join(root, 'updater/tests'), '-q'], { cwd: root, stdio: 'inherit' });
process.exit(result.status ?? 1);
