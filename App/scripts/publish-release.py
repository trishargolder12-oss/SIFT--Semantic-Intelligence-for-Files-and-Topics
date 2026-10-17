"""Publish the existing verified installer; enable downloads only after remote verification.

Uses the configured Git credential helper for this exact GitHub repository. Credentials
stay in memory and are never printed or written to project files.
"""
import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def credential(repo):
    env = {**os.environ, 'GCM_INTERACTIVE': 'never', 'GIT_TERMINAL_PROMPT': '0'}
    result = subprocess.run(['git', 'credential', 'fill'], cwd=ROOT, env=env,
                            input=f'protocol=https\nhost=github.com\npath={repo}.git\n\n',
                            capture_output=True, text=True, timeout=30)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or not fields.get('password'):
        raise RuntimeError('GitHub publishing requires signing in with Git Credential Manager first.')
    return fields['password']


def api(token, route, payload=None, method=None):
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'SIFT-release-publisher'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(f'https://api.github.com{route}',
                                     data=json.dumps(payload).encode() if payload is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and method is None and payload is None:
            return None
        # Do not include request headers or credentials in an error.
        raise RuntimeError(f'GitHub API returned HTTP {error.code} for {route}') from None


def upload(token, repo, release_id, file, name):
    connection = http.client.HTTPSConnection('uploads.github.com', timeout=180)
    route = f'/repos/{repo}/releases/{release_id}/assets?name={urllib.parse.quote(name)}'
    try:
        connection.putrequest('POST', route)
        connection.putheader('Authorization', f'Bearer {token}')
        connection.putheader('Accept', 'application/vnd.github+json')
        connection.putheader('User-Agent', 'SIFT-release-publisher')
        connection.putheader('Content-Type', 'application/octet-stream')
        connection.putheader('Content-Length', str(file.stat().st_size))
        connection.endheaders()
        with file.open('rb') as source:
            while block := source.read(1024 * 1024):
                connection.send(block)
        response = connection.getresponse()
        data = json.load(response)
        if response.status != 201:
            raise RuntimeError(f'GitHub asset upload returned HTTP {response.status}')
        return data
    finally:
        connection.close()


def verify_download(url, size, sha256):
    # Deliberately unauthenticated: every visitor must be able to download this file.
    request = urllib.request.Request(url, headers={'User-Agent': 'SIFT-release-verification'})
    with urllib.request.urlopen(request, timeout=180) as response:
        hasher, total = hashlib.sha256(), 0
        while block := response.read(1024 * 1024):
            hasher.update(block)
            total += len(block)
    if total != size or hasher.hexdigest() != sha256:
        raise RuntimeError('Public download differs from the verified local installer; website stays disabled.')


def main():
    metadata_file = ROOT / 'App/release.json'
    metadata = json.loads(metadata_file.read_text())
    installer = ROOT / 'App/Installer' / metadata['installer']
    if installer.stat().st_size != metadata['sizeBytes'] or digest(installer) != metadata['sha256']:
        raise RuntimeError('Local installer differs from release.json; publishing blocked.')
    repo, tag = metadata['repository'], metadata['tag']
    token = credential(repo)
    base = f'/repos/{repo}/releases'
    release = api(token, f'{base}/tags/{tag}')
    if release is None:
        notes = (ROOT / 'App/RELEASE-NOTES.md').read_text(encoding='utf-8')
        release = api(token, base, {'tag_name': tag, 'target_commitish': 'main',
                                   'name': f'SIFT V0 Beta — {metadata["version"]}',
                                   'body': notes, 'draft': True, 'prerelease': True})
    checksums = ROOT / 'App/Installer/SHA256SUMS.txt'
    checksums.write_text(f'{metadata["sha256"]}  {metadata["assetName"]}\n', encoding='utf-8')
    existing = {item['name']: item for item in release['assets']}
    for file, name in [(installer, metadata['assetName']), (checksums, 'SHA256SUMS.txt')]:
        if name in existing:
            asset = existing[name]
            expected_digest = 'sha256:' + digest(file)
            if asset['size'] != file.stat().st_size or asset.get('digest') != expected_digest:
                raise RuntimeError(f'Existing release asset {name} differs; refusing to overwrite it.')
        else:
            if not release['draft']:
                raise RuntimeError('Existing public release is incomplete; refusing to modify it.')
            print(f'Uploading {name} ({file.stat().st_size:,} bytes)...', flush=True)
            upload(token, repo, release['id'], file, name)
    if release['draft']:
        release = api(token, f'{base}/{release["id"]}', {'draft': False, 'prerelease': True}, 'PATCH')
    url = f'https://github.com/{repo}/releases/download/{tag}/{metadata["assetName"]}'
    print('Verifying anonymous public download...', flush=True)
    verify_download(url, metadata['sizeBytes'], metadata['sha256'])
    release_date = datetime.datetime.fromisoformat(release['published_at'].replace('Z', '+00:00')).astimezone(
        datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date().isoformat()
    website_file = ROOT / 'Website/public/release.json'
    website = json.loads(website_file.read_text())
    website.update(status='published', approved=True, version=metadata['version'],
                   installerFilename=metadata['assetName'], downloadUrl=url,
                   sizeBytes=metadata['sizeBytes'], sha256=metadata['sha256'], releaseDate=release_date,
                   signingStatus=metadata['signingStatus'], lastReviewed=release_date,
                   message='SIFT V0 Beta for Windows x64 is available as one complete installer.')
    website_file.write_text(json.dumps(website, indent=2) + '\n')
    metadata.update(published=True, downloadUrl=url, releaseDate=release_date)
    metadata_file.write_text(json.dumps(metadata, indent=2) + '\n')
    print(f'Published and verified: {url}\nWebsite metadata enabled. Build, test, commit and push the updated metadata.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
