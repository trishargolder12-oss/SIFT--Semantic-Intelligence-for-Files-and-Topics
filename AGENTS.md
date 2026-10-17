# SIFT V0 Beta

This is the launch checkout. App contains the desktop/backend/updater source and local distribution files. Website is the Vercel project root. Keep the website's release metadata consistent with the actual published GitHub asset.

Preserve org.sift.local-library and the existing NSIS identity. Increment the desktop version for application changes and run npm run dist in App/desktop; its final step refreshes the local updater and latest.json. Keep updater, manifest and referenced version directory together. Never delete user libraries, originals, model storage or old installation folders as custom cleanup.

Never commit installers, update ZIPs, dependencies, caches, credentials or user data. Publish binaries as GitHub Release assets. Run updater tests and frozen --verify-only validation; distinguish these from a real installed upgrade.

Save test/progress/issue reports under test_logs/test_log_YYYY-MM-DD_HH-mm-ss.md using Asia/Calcutta time. Check Codex usage periodically and pause at 10% remaining in either available window.
