# Updating SIFT before v1.0

Each application release includes a refreshed local updater. Online hosting will be connected when the website is ready.

## Install the latest local release

1. Extract the entire **SIFT Update 0.3.0.zip** into a folder.
2. Run **SIFT Updater.exe** inside that folder and confirm installation.
3. The updater verifies the installer, closes the registered SIFT application normally, and starts the Windows installer. The installer replaces the previous application files and preserves the library database, preferences, documents, and separately installed models.

Keep `SIFT Updater.exe`, `latest.json`, and the referenced version folder together. Running the updater directly from the repository's `desktop/release` folder also works. It needs no Python installation and makes no network requests.

The updater refuses an older version and reports when the same/newer version is already installed. It checks installation registration before reporting success. If the application cannot close, the installer fails, or the user cancels, no custom delete operation is attempted. Close SIFT manually and retry if requested.

Old **installed application files** are cleaned up by the existing NSIS upgrade mechanism. Downloaded release archives, development source folders, and previous build artifacts remain available. The updater does not search the computer for unrelated files to delete.

## How releases stay current

For application changes, increment the version in `desktop/package.json` and its lockfile, then run `npm run dist` from `desktop`.

The release pipeline builds the renderer, Electron code, frozen local service, Windows installer, and updater. Its final step writes a fresh manifest with the exact version, installer path, byte size, and SHA-256; verifies it using the frozen updater; and creates a self-contained update ZIP with a checksum file.

For updater-only changes against an already built current installer, use `npm run build:updater`. Use `npm run test:updater` for the focused tests. Stable app identity is essential for replacing an existing installation and is preserved.

The manifest checksum detects changed/incomplete installer files. It is local integrity checking, not publisher authentication. These development executables are unsigned. Code signing and a trusted online feed remain work for deployment.

## Verification scope

Focused tests cover manifest validation, path containment/junctions, checksums, version ordering, registry identity/scopes, user cancellation, installer failure/cancellation, changed releases during confirmation, and installer handoff. A real Windows fixture confirms normal window closing targets only the registered executable path and leaves another same-named process running.

The build also runs the frozen updater with `--verify-only`. A real upgrade of the user's installed SIFT application is not run automatically; that changes the active installation and remains the final manual acceptance check.
