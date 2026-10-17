# SIFT V0 Beta

**Semantic Intelligence for Files and Topics** — a Windows desktop library for PDFs, Word documents and text notes in folders you approve. SIFT keeps its index on your device and leaves originals in place. Beta version: **0.3.3**.

| Folder | Purpose |
| --- | --- |
| [App](App/) | Desktop, backend and updater source, build instructions and exact release metadata. The local checkout also contains the complete installer and offline updater package. |
| [Website](Website/) | Standalone website, ready for Vercel with its own dependencies, build and deployment configuration. |

## Get the app

Use [GitHub Releases](https://github.com/trishargolder12-oss/SIFT--Semantic-Intelligence-for-Files-and-Topics/releases). The public download is **SIFT-Setup.exe**, a single complete Windows x64 installer with the local service included. No separate Python or Node.js installation is needed. Binaries are release assets, not Git source files.

In the local `SIFT V0 Beta` folder, the installer is `App/Installer/0.3.3/SIFT Setup 0.3.3.exe`. Its SHA-256 is `6938ceca184997c5d4772531012d5cab09368e4d43ff5c77e77a6ee7b6ca9fc5` (144,500,817 bytes). The installer is unsigned. See [beta release notes](App/RELEASE-NOTES.md) for verification limits.

Optional local models and the OCR pack require separate explicit setup. No automatic online updater is configured. The existing local updater, manifest and referenced version directory stay together under `App/Installer/`; an offline update ZIP is also included locally.

## Deploy the website on Vercel

1. Import this GitHub repository in Vercel.
2. Set **Root Directory** to **Website** and Node.js to **22.x**.
3. Deploy. `Website/vercel.json` defines `npm ci`, `npm run build` and output directory `dist`.

The website is static; it needs no database, API token, Python or Electron runtime. Installers download from GitHub Releases. Website buttons are enabled only after the publisher verifies an anonymous hosted download against the local installer. Future pushes to the connected production branch rebuild the site.

Set `SITE_URL` to your real HTTPS origin if you attach a custom domain. Otherwise the build uses Vercel's production domain for canonical URLs and sitemap generation. See [website instructions](Website/README.md).

## Maintain the release

The `App/` source is self-contained for Windows development and builds; see [app instructions](App/README.md). Preserve the app ID and NSIS identity on updates. New app versions require a complete `npm run dist` build, refreshed updater and verification. Never commit credentials, indexed documents, models, dependencies or installers.

The repository is public for inspection. No open-source license has been assigned. Bundled font licenses are retained in the app and website assets.
