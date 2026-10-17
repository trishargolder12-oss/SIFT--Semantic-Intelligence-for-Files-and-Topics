"""Offline pre-1.0 installer launcher. Never deletes documents or app data."""
import argparse
import ctypes
import hashlib
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

APP_ID = 'org.sift.local-library'
# Same stable identity as electron-builder's existing NSIS installers.
APP_GUID = str(uuid.uuid5(uuid.UUID('50e065bc-3134-11e6-9bab-38c9862bdaf3'), APP_ID))


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('Invalid release version')
    return tuple(map(int, value.split('.')))


def validate(manifest):
    manifest = Path(manifest).resolve(strict=True)
    if manifest.stat().st_size > 16384:
        raise ValueError('Release manifest is too large')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('appId') != APP_ID:
        raise ValueError('Invalid SIFT release manifest')
    version(data.get('version'))
    if (type(data.get('sizeBytes')) is not int or data['sizeBytes'] <= 0
            or not isinstance(data.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', data['sha256'])):
        raise ValueError('Invalid installer size or checksum')
    if not isinstance(data.get('installer'), str):
        raise ValueError('Missing installer path')
    relative = Path(data['installer'])
    if relative.drive or relative.root or '..' in relative.parts or ':' in str(relative):
        raise ValueError('Installer must be inside the release folder')
    candidate = manifest.parent / relative
    current = candidate
    while current != manifest.parent:
        if current.is_symlink() or getattr(current.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked installer paths are not allowed')
        current = current.parent
    installer = candidate.resolve(strict=True)
    installer.relative_to(manifest.parent)
    if installer.name != f"SIFT Setup {data['version']}.exe":
        raise ValueError('Unexpected installer filename')
    if installer.stat().st_size != data['sizeBytes']:
        raise ValueError('Installer size mismatch; rebuild the update bundle')
    with installer.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != data['sha256']:
        raise ValueError('Installer checksum mismatch; installation blocked')
    return data, installer


def installed_releases():
    import winreg
    releases = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, rf'Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_GUID}', 0, winreg.KEY_READ | view) as key:
                    installed = version(winreg.QueryValueEx(key, 'DisplayVersion')[0])
                with winreg.OpenKey(hive, rf'Software\{APP_GUID}', 0, winreg.KEY_READ | view) as key:
                    location = Path(winreg.QueryValueEx(key, 'InstallLocation')[0])
                releases.append({'version': installed, 'location': location})
            except OSError:
                continue
    return releases


def close_sift(releases):
    """Send normal window close only to SIFT in its registered install location."""
    from ctypes import wintypes as w
    kernel, user = ctypes.WinDLL('kernel32', use_last_error=True), ctypes.WinDLL('user32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    paths = {str((item['location'] / 'SIFT.exe').resolve()).casefold() for item in releases}
    handles = {}

    @callback_type
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x101000, False, pid.value)
        if handle:
            buffer, length = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
            matched = kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)) and str(Path(buffer.value).resolve()).casefold() in paths
            if matched:
                user.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE; Electron stops its service.
                if pid.value not in handles:
                    handles[pid.value] = handle
                else:
                    kernel.CloseHandle(handle)
            else:
                kernel.CloseHandle(handle)
        return True

    try:
        user.EnumWindows(visit, 0)
        for handle in handles.values():
            if kernel.WaitForSingleObject(handle, 20000) != 0:
                raise RuntimeError('SIFT could not close. Close it manually and run the updater again.')
    finally:
        for handle in handles.values():
            kernel.CloseHandle(handle)


def notify(message, flags=0x40):
    return ctypes.windll.user32.MessageBoxW(None, message, 'SIFT Updater', flags)


def install(manifest):
    data, installer = validate(manifest)
    releases = installed_releases()
    if max((item['version'] for item in releases), default=(0, 0, 0)) >= version(data['version']):
        notify('This release is already installed, or a newer version is installed.')
        return 0
    message = f"Install SIFT {data['version']}?\n\nSIFT will close while the installer replaces the old application files. Your documents, library index and settings are preserved."
    if notify(message, 0x21) != 1:
        return 0
    close_sift(releases)
    # Recheck after user interaction/closing. NSIS owns application file cleanup.
    checked_data, checked_installer = validate(manifest)
    if checked_data != data or checked_installer != installer:
        raise ValueError('Release changed during confirmation. Run the updater again.')
    result = subprocess.run([str(installer)], cwd=installer.parent, check=False)
    if result.returncode:
        raise RuntimeError(f'Installer exited with code {result.returncode}. No manual cleanup was attempted.')
    if max((item['version'] for item in installed_releases()), default=(0, 0, 0)) < version(data['version']):
        raise RuntimeError('Installation was cancelled or did not register the new version. Run the updater again when ready.')
    notify(f"SIFT {data['version']} is installed.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    default = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    parser.add_argument('--manifest', type=Path, default=default / 'latest.json')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.verify_only:
            data, _ = validate(args.manifest)
            if sys.stdout:
                print(json.dumps({'verified': True, 'version': data['version']}))
            return 0
        return install(args.manifest)
    except Exception as exc:
        if args.verify_only:
            if sys.stderr:
                print(str(exc), file=sys.stderr)
        else:
            notify(str(exc), 0x10)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
