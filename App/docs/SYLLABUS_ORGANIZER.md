# Syllabus organizer â€” SIFT 0.3.1

## Use it

Open **Find it with SIFT â†’ Organize syllabus**. Choose **Attach syllabus** for a PDF/PNG/JPEG or paste syllabus text. Attaching grants access to that file only. It does not approve its parent folder.

On first organization, choose an output folder. SIFT creates an owned `SIFT Study Collections` directory inside it and remembers the destination. A conflicting existing directory gets a separate name. Use **Disconnect output folder** to revoke further writes; existing generated files are left in place. Original documents and your index/settings are preserved.

SIFT reads the syllabus, shows its ordered unit/topic outline, matches permitted library evidence, and prepares shortcut folders. The UI distinguishes matching from export completion. Counts are calculated from actual assignments. Coverage means topics with matching material, not complete exam preparation.

**Edit outline** supports names, aliases, topic/unit ordering, merging, splitting at semicolons, and adding entries. Original wording, source page/position and extraction method remain recorded. Corrections persist during refresh. Repeated requests for the same attachment or identical pasted text reuse the collection. Refreshing an edited attachment produces a visible revision.

For a changed pasted syllabus or replacement attachment, enable **Update the selected collection instead of creating a new one** in the intake form. The collection identity and physical tree remain stable. If you previously edited the outline, SIFT retains those edits and flags the changed source for comparison.

Substantive matches get shortcuts automatically. Brief mentions, tables of contents, uncertain OCR, ambiguous acronyms, visual descriptions and weak candidates remain related/review evidence. Approve, reject, or move an assignment explicitly. A source can belong to multiple topics without copying its contents.

## Optional visual setup

Digital PDF text works immediately. For scanned PDFs and photographs, extract **SIFT OCR Pack 1.zip**, then choose **Local OCR & visual models â†’ Select extracted OCR pack** and select the folder containing `pack.json`, `models`, and `sift-ocr`. Keep that extracted folder available; its path is remembered.

The pack contains Python and its required runtime, so users do not need to install Python. It uses pinned PaddleOCR 3.2.0, PaddlePaddle 3.2.1 and PP-OCRv5 mobile detection/recognition weights. The current pack is approximately **286 MB compressed / 698 MB extracted**. CPU inference is tested; a GPU is not required. Actual sample working memory was roughly 501â€“601 MiB, with a 1.5 GiB job limit for the page worker and its OCR descendants. Runtime networking and model auto-downloads are blocked. File hashes are validated when the pack is selected.

PP-StructureV3 was evaluated as an additional layout/table/formula pipeline. It is not included: this release uses one small OCR stack and retains reading-order boxes, while complex columns, tables and formulas require review. No claim of accurate structural table reconstruction is made. [PaddleOCR installation](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/installation.html), [PP-OCRv5](https://paddlepaddle.github.io/PaddleOCR/v3.0.1/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html).

For difficult visual regions, the existing local-model settings support optional **Qwen3-VL 2B** through Ollama: about **1.9 GB download**, estimated **4â€“6 GB working memory**, Apache-2.0. Enable local models and explicitly press its Download button. The fixed loopback transport rejects proxies and redirects and requires digest prefix `0635d9d857d4`. It is used selectively after page inspection, rather than on every page. Its output is labeled a generated visual description and always requires review. It never becomes syllabus transcription or a command. The text-only intent model is not used for images. [Model artifact/license](https://ollama.com/library/qwen3-vl:2b).

The OCR code/model project and Paddle runtime use Apache-2.0; package metadata/license files are included in the pack. See the [PaddleOCR repository](https://github.com/PaddlePaddle/PaddleOCR). PDFium/Pillow and OCR dependency licenses remain with their distributions. The separate OCR pack is an explicit local setup action; app updates do not install/download it silently. Qwen3-VL weights were not downloaded or quality-tested during this implementation.

## Storage, permissions and recovery

Migration 5 adds attachment grants, output grants, source-located visual pages/thumbnails, collection outlines/revisions, assignment decisions, background jobs and export operation plans. Visual text joins the existing chunk/FTS index; there is no competing library index. Transcription, OCR confidence, retrieval relevance, and generated description uncertainty stay separate.

Page caches are keyed by source identity, SHA-256, page, extraction configuration and supported engine versions. Native text is retained for mixed PDFs. Pages are limited to 64 MB source files, 200 pages per source, 2,000-pixel rendering, bounded image pixels, a 90-second page timeout and a 70-second OCR subprocess timeout. An unprocessed page is reported. Failed pages can be retried with refresh; successful pages reuse their cache. Interrupted collection jobs recover with a two-attempt startup limit. Cancellation preserves completed evidence and can leave a retryable partial export.

Reading approved folders, reading an attached source, and writing output are separate grants. Canonical path and junction/symlink checks are enforced in the service and native boundary. Permissions/version checks run before model work, matching, publication, page previews and file actions. Revoked/missing/changed evidence is excluded from results; old app-routed shortcuts recheck the stable reference. Cached source data may remain locally but is not accessible after revocation. Deliberate same-size/timestamp-preserving edits still require a scan/hash to identify.

The main process uses `shell.writeShortcutLink`. Arguments contain stable IDs, never document paths or commands. Cold and already-running launches are handled. Filesystem writes follow a durable SQLite plan plus an app-data ownership journal. Staging, hashes and link-property checks support idempotent retry. Cleanup deletes only verified owned shortcuts and empty owned directories. Unrelated/modified files remain intact and conflicts produce a retryable error. Generated output roots are excluded from scanning. Database matching can finish before export; completion is not reported until the native operation is acknowledged.

## Measured limits

See [visual measurements](VISUAL_QUALITY_MEASUREMENTS.json), [matching measurements](MATCHING_QUALITY_MEASUREMENTS.json) and [real mixed-PDF smoke](REAL_VISION_SMOKE.json).

The labeled visual set is small, synthetic and English. A handwriting-style font is not a real handwritten dataset. Blurred and difficult samples failed badly; even a high-confidence font sample had an error. OCR confidence is not a probability of correctness. Diagrams with labels were transcribed; connections and unlabeled diagram meaning were not validated. The table/equation sample measures token recovery, not mathematical or layout correctness. Representative real handwriting and Qwen visual-quality acceptance remain necessary.


## Maintenance behavior in 0.3.1

OCR and visual-model failures retain successful native/OCR stages and are retried by Refresh. A bounded source probe determines PDF page count before page analysis, so a failed first page does not hide later pages. Page-specific failures keep the collection partial. OCR cache identity now includes the pack manifest digest and updated extraction configuration; existing schema-5 collections, outlines and decisions stay intact. The first refresh may analyze old-version page caches once. Unchanged current caches do not republish chunks or request their embeddings again.

Automatic matching requires a topic-linked explanatory clause close to the mention. A word count for the entire paragraph is insufficient. Bibliographies, contents, repeated headings, subject conflicts, ambiguous aliases, uncertain OCR and generated descriptions remain nonautomatic. This conservative rule can still miss relevant material; approval and moving evidence remain available. Scores are relevance indicators, not probabilities.

Page previews discard late responses and failures when the collection, topic, evidence version or permission scope changes. Closing a preview invalidates outstanding preview requests.

### Chat result references and dates

Result numbers restart at 1 on each ten-slot page. “The second one” selects slot 2 on the latest turn's displayed page. Numbers remain attached to the original identities; unavailable slots are omitted without renumbering later cards. Totals and pagination describe the original result snapshot, which may contain unavailable slots. An unavailable, out-of-range or stale-page reference asks for clarification. Selection displays evidence; opening remains an explicit button action.

Included and excluded file formats are independent. “PDF or TXT but not Word” permits PDF/TXT and excludes DOCX. “Without PDF and Word” excludes both. Contradictory message/UI constraints ask for clarification. Optional model query suggestions cannot change these constraints.

Dates use the client's JavaScript timezone offset (minutes UTC minus local), with no named timezone support. “Before 2026-10-15” excludes all of 15 October locally. “After 2026-10-15” starts at local midnight on 16 October. “From 2026-10-15 through 2026-10-17” includes both endpoint days: UTC-converted start inclusive, following-day end exclusive. Relative days follow the same boundary conversion. Named-zone daylight-saving behavior is outside this contract.

Current maintenance measurements and acceptance limits are in [the 0.3.1 report](../test_logs/test_log_2026-10-16_11-45-51.md). The earlier JSON measurements above are historical 0.3.0 synthetic results, not new visual acceptance. Representative real handwriting, blur, multicolumn layouts, equations/tables and diagram relationships remain unvalidated without supplied samples. No new OCR stack or model was downloaded for this maintenance work.
