# SIFT V0 Beta — 0.3.3

Download **SIFT-Setup.exe** for Windows x64. This one installer includes the desktop app and its local service; Python and Node.js are not needed. Run the same installer to upgrade an existing SIFT installation.

- Local PDF, DOCX and TXT library with full-text search and folder monitoring.
- Conversational file discovery, virtual sections, syllabus collections and Windows shortcut exports.
- Optional local models and OCR require separate explicit setup. They are not bundled in this download.
- Version 0.3.3 fixes document identity and citation continuity when a file is renamed during a scan.
- NSIS preserves the existing app identity and user data. Original documents remain untouched.

Installer: **unsigned**, 144,500,817 bytes.

SHA-256: `6938ceca184997c5d4772531012d5cab09368e4d43ff5c77e77a6ee7b6ca9fc5`

The published filename differs from the local `SIFT Setup 0.3.3.exe`; the bytes are identical. `SHA256SUMS.txt` provides the checksum.

Frozen-service smoke and updater verification passed on the local release. A real installed upgrade and clean-machine installation have not been exercised. No new real neural-model inference or OCR quality benchmark is claimed. This is a beta release.
