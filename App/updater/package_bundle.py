"""Assemble a self-contained offline update ZIP after executable validation."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def main(directory):
    directory = Path(directory).resolve(strict=True)
    manifest = json.loads((directory / 'latest.json').read_text())
    filename = f"SIFT Update {manifest['version']}.zip"
    target = directory / filename
    temporary = directory / (filename + '.tmp')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as bundle:
        for relative in ['SIFT Updater.exe', 'latest.json', manifest['installer']]:
            bundle.write(directory / relative, relative)
        bundle.writestr('START HERE.txt',
            'Extract this entire ZIP to a folder, then run SIFT Updater.exe.\r\n'
            'Keep the updater, latest.json and version folder together.\r\n'
            'The updater verifies the installer, closes SIFT and installs the new version.\r\n'
            'Old installed application files are replaced. Documents, index and settings are preserved.\r\n'
            'This is an offline development release; no update server is contacted.\r\n')
    temporary.replace(target)
    with target.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {filename}\n')
    print(f'Update bundle ready: {target}')


if __name__ == '__main__':
    main(sys.argv[1])
