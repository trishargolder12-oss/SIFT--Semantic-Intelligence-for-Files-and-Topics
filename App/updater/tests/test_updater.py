import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('sift_updater', Path(__file__).parents[1] / 'sift_updater.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


@pytest.fixture
def release(tmp_path):
    directory = tmp_path / '0.3.0'
    directory.mkdir()
    exe = directory / 'SIFT Setup 0.3.0.exe'
    exe.write_bytes(b'temporary installer fixture')
    data = {'appId': updater.APP_ID, 'version': '0.3.0', 'installer': '0.3.0/' + exe.name,
            'sizeBytes': exe.stat().st_size, 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
    manifest = tmp_path / 'latest.json'
    manifest.write_text(json.dumps(data))
    return manifest, exe, data


def test_real_manifest_and_semantic_version_order(release):
    manifest, exe, data = release
    assert updater.validate(manifest) == (data, exe)
    assert updater.version('0.10.0') > updater.version('0.9.9')


@pytest.mark.parametrize('key,value', [
    ('appId', 'other.app'), ('version', '0.3'), ('version', '00.3.0'),
    ('installer', '../SIFT Setup 0.3.0.exe'), ('installer', 'C:escape.exe'),
    ('installer', '\\escape.exe'), ('installer', '0.3.0/SIFT Setup 0.3.0.exe:stream'),
    ('sizeBytes', True), ('sizeBytes', 1), ('sha256', '0'*64), ('sha256', None),
])
def test_invalid_release_blocked(release, key, value):
    manifest, _, data = release
    data[key] = value
    manifest.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        updater.validate(manifest)


def test_same_size_corruption_blocked(release):
    manifest, exe, _ = release
    exe.write_bytes(b'X' * exe.stat().st_size)
    with pytest.raises(ValueError, match='checksum'):
        updater.validate(manifest)


def test_junction_blocked(release, tmp_path):
    manifest, exe, data = release
    target = tmp_path / 'target'
    target.mkdir()
    (target / exe.name).write_bytes(exe.read_bytes())
    junction = tmp_path / 'linked'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(target)], capture_output=True)
    assert result.returncode == 0, result.stderr
    data['installer'] = 'linked/' + exe.name
    manifest.write_text(json.dumps(data))
    try:
        with pytest.raises(ValueError, match='Linked'):
            updater.validate(manifest)
    finally:
        junction.rmdir()  # Removes only the junction, never its target.


def setup_flow(monkeypatch, installed=()):
    notices, launches, closes = [], [], []
    state = list(installed)
    monkeypatch.setattr(updater, 'installed_releases', lambda: state)
    monkeypatch.setattr(updater, 'notify', lambda message, flags=0x40: notices.append(message) or 1)
    monkeypatch.setattr(updater, 'close_sift', lambda items: closes.append(items))
    def run(args, **kwargs):
        launches.append(args)
        state.append({'version': (0, 3, 0)})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(updater.subprocess, 'run', run)
    return notices, launches, closes


@pytest.mark.parametrize('installed', [(0, 3, 0), (0, 10, 0)])
def test_already_current_or_downgrade_never_launches(release, monkeypatch, installed):
    _, launches, closes = setup_flow(monkeypatch, [{'version': installed}])
    assert updater.install(release[0]) == 0
    assert not launches and not closes


def test_installer_handoff_and_originals_preserved(release, monkeypatch, tmp_path):
    notices, launches, closes = setup_flow(monkeypatch, [{'version': (0, 2, 0)}])
    source = tmp_path / 'notes.txt'
    source.write_bytes(b'original')
    database = tmp_path / 'library.sqlite'
    database.write_bytes(b'index fixture')
    assert updater.install(release[0]) == 0
    assert launches == [[str(release[1])]] and len(closes) == 1
    assert source.read_bytes() == b'original' and database.read_bytes() == b'index fixture'
    assert 'is installed' in notices[-1]


def test_user_cancel_does_not_close_or_install(release, monkeypatch):
    _, launches, closes = setup_flow(monkeypatch)
    monkeypatch.setattr(updater, 'notify', lambda *args: 2)
    assert updater.install(release[0]) == 0
    assert not launches and not closes


def test_installer_failure_and_silent_cancel_are_not_success(release, monkeypatch):
    notices, _, _ = setup_flow(monkeypatch)
    monkeypatch.setattr(updater.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=5))
    with pytest.raises(RuntimeError, match='code 5'):
        updater.install(release[0])
    monkeypatch.setattr(updater.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError, match='cancelled'):
        updater.install(release[0])
    assert not any('is installed' in message for message in notices)


def test_change_after_confirmation_blocks_launch(release, monkeypatch):
    _, launches, _ = setup_flow(monkeypatch)
    monkeypatch.setattr(updater, 'close_sift', lambda _: release[1].write_bytes(b'changed'))
    with pytest.raises(ValueError):
        updater.install(release[0])
    assert not launches


def test_registry_lookup_uses_stable_app_identity_and_both_scopes(monkeypatch):
    opened = []
    class Key:
        def __init__(self, hive, name, access):
            self.hive, self.name = hive, name
            opened.append((hive, name, access))
        def __enter__(self): return self
        def __exit__(self, *_): pass
    def query(key, field):
        if field == 'DisplayVersion':
            return ('0.10.0' if key.hive == 2 else '0.2.0', 1)
        return ('C:/SIFT installation', 1)
    fake = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2,
        KEY_WOW64_64KEY=256, KEY_WOW64_32KEY=512, KEY_READ=1,
        OpenKey=lambda hive, name, reserved, access: Key(hive, name, access), QueryValueEx=query)
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    releases = updater.installed_releases()
    assert max(item['version'] for item in releases) == (0, 10, 0)
    assert {item[0] for item in opened} == {1, 2}
    assert {item[2] for item in opened} == {257, 513}
    assert all(updater.APP_GUID in item[1] for item in opened)
