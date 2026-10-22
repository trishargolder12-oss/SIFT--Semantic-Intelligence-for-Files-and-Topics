# SIFT website — Vercel

**Live:** https://sift-v0-beta.vercel.app/ · [Vercel project](https://vercel.com/monolith-vi/sift-v0-beta)

The existing Monolith VI Vercel project is connected to the SIFT GitHub repository. Its Root Directory is Website and its framework is Vite. Pushes to main trigger website builds and production updates. Downloads continue to use the verified GitHub Release installer. The original launch used source upload; the current update workflow uses Git.

This folder is a standalone React/TypeScript/Vite project. It builds five pre-rendered pages and static policy/release pages. It does not run the desktop app or Python backend on Vercel.

```powershell
npm ci
npm run build
npm run preview
```

In Vercel, import `trishargolder12-oss/SIFT--Semantic-Intelligence-for-Files-and-Topics`, choose **Website** as Root Directory, Node.js **22.x**, and deploy. `vercel.json` defines the build, output and response headers. No database, API keys or runtime backend are required. Keep direct `.html` URLs; there is no catch-all rewrite.

The build uses `SITE_URL` if supplied, then `site.json`, then Vercel's production domain to generate canonical URLs and the sitemap. Use your actual public HTTPS origin when setting a custom domain.

`public/release.json` is the single source for download buttons, checksum, release notes and version. The release publisher verifies the hosted installer before enabling the download. GitHub hosts the installer; Vercel serves only this site's static assets. Never copy `.exe` or update ZIP files into `public/`.

`npm test` exercises the production pages in installed Microsoft Edge (or set `SIFT_BROWSER_CHANNEL=chrome`). This test saves a timestamped report under the repository's `test_logs/` and screenshots under `Website/screenshots/`.

The site distinguishes public installer 0.3.3 from local-only build 0.4.3. Screenshot provenance is recorded in public/assets/app-capture.json. To regenerate captures from a separate local app source tree, set SIFT_DESKTOP_SOURCE before running scripts/capture-app.mjs. Never advertise a newer installer until its hosted bytes are verified.
