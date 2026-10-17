"""Verify the distributed ZIP and run its extracted frozen updater without installing."""
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main(archive):
    archive = Path(archive).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='sift-update-check-') as temporary:
        directory = Path(temporary).resolve()
        assert directory.parent == Path(tempfile.gettempdir()).resolve()
        assert directory.name.startswith('sift-update-check-')
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read('latest.json'))
            expected = {'latest.json', 'SIFT Updater.exe', 'START HERE.txt', manifest['installer']}
            if set(bundle.namelist()) != expected:
                raise ValueError('Unexpected update ZIP contents')
            for name in expected:
                candidate = (directory / name).resolve()
                candidate.relative_to(directory)
            if bundle.testzip():
                raise ValueError('Update ZIP failed its integrity check')
            bundle.extractall(directory)
        result = subprocess.run([str(directory / 'SIFT Updater.exe'), '--verify-only'], cwd=directory)
        if result.returncode:
            raise ValueError('Extracted updater failed validation')
    with archive.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if archive.with_suffix('.zip.sha256').read_text().split()[0] != digest:
        raise ValueError('Archive checksum does not match')
    print(json.dumps({'archive': archive.name, 'version': manifest['version'], 'verified': True, 'installation_performed': False}))


if __name__ == '__main__':
    main(sys.argv[1])
