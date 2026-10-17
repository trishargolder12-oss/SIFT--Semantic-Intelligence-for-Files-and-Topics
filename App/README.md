# SIFT Windows app — 0.3.3 beta

**Install:** open `Installer/0.3.3/SIFT Setup 0.3.3.exe`. This single file includes SIFT and its local service. End users do not need Python or Node.js. Windows x64 only. The installer is unsigned.

**Update:** the same installer replaces the existing SIFT installation using its original NSIS identity. The local helper is `Installer/SIFT Updater.exe`; keep it together with `latest.json` and the `0.3.3/` directory. The complete offline update ZIP is in `Offline Update/`. Library data, approved documents and models are preserved. No automatic online update feed is configured.

Installers/ZIPs are present locally and ignored by Git. The public installer is hosted as `SIFT-Setup.exe` on the versioned GitHub Release; the bytes and SHA-256 remain identical. `release.json` records the exact version, size and hash.

## Develop or rebuild on Windows

Requires Node.js 22 and Python 3.11. From this folder:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt pyinstaller
cd desktop
npm ci
npm run dev
```

Run `npm run dist` in `desktop` for a new complete installer and refreshed local updater. Run `npm run test:updater` and the frozen updater's `--verify-only` validation. An unchanged release must keep its existing installer bytes; rebuilding is not a way to recreate the same SHA-256.

The source is organized as `desktop/`, `backend/`, `updater/`, and `docs/`. Optional local models and OCR packs are separate opt-in downloads; they are not bundled in the installer.

## Publish the prepared installer

After checks, run `python App/scripts/publish-release.py` from the repository root. It uses the existing GitHub credential helper without displaying credentials, stages the exact installer and checksum in a draft release, then publishes the beta. Only after an anonymous download matches the size/hash does it enable website download buttons. Commit and push the resulting `App/release.json` and `Website/public/release.json` to deploy the updated website.
