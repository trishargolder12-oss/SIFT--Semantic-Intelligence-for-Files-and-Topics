# SIFT website — Vercel

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
