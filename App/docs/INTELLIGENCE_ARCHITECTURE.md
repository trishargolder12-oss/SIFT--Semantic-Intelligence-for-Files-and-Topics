# Conversational discovery architecture

Implemented in SIFT 0.2.0, 15 October 2026. Scope: finding files and grouping the approved library.

Version 0.3.0 extends this foundation with [syllabus organization and source-linked visual evidence](SYLLABUS_ORGANIZER.md). OCR text and labeled visual descriptions join the same permission-filtered chunks/FTS index. This document describes the original discovery foundation; the linked guide describes the added page and collection pipeline.

## Existing foundation and selected pipeline

The inspected project already used Electron, React/TypeScript, a token-protected FastAPI service, SQLite migrations/FTS5, and local PDF/DOCX/TXT parsers. The implementation builds on that stack and Edit 4's parser limits, scan queue, cancellation, and atomic document publication.

**Message → intent/context → permitted retrieval → ranked evidence → controlled reply.**

1. Electron accepts named renderer bridge calls. The renderer has no filesystem API, service token, arbitrary URL proxy, or model client.
2. `discovery_language.py` interprets conversational phrasing, corpus-supported acronyms, spelling variants, filters, and preceding result context. Ambiguous acronyms/folder references request clarification. Date filters distinguish discovery from modification and use the client's timezone offset.
3. `access.py` and retrieval build an eligible set of approved, accessible, current document versions. A temporary SQLite table restricts FTS/chunk reads to that set. Optional query embeddings rank only eligible vectors.
4. Retrieval combines FTS5 terms, document/group metadata, and optional cosine similarity. One best evidence chunk represents each file. All matches are retained and paginated; discovery shows ten cards per page.
5. Replies are templates grounded in actual retrieval. Weak/semantic-only matches are presented as likely. No-match and clarification states do not invent file references.
6. History stores evidence identifiers and versions. Cards and excerpts are hydrated again under current permissions. Native file actions recheck the citation, approved root, canonical path, and current file before opening.

The optional language model supplies only a short query suggestion. It never selects file IDs, constructs paths, executes commands, or writes the assistant's final evidence claims. Document instructions are inert text.

## Intelligence components and resource decisions

| Component | Role | Storage and estimated memory | License |
|---|---|---|---|
| SQLite FTS5 | Immediate offline keyword retrieval | Existing database plus chunk text/FTS indexes; grows with corpus | SQLite public domain |
| Source-located chunks | Evidence and retrieval units | At most 160 words/1,100 characters per chunk, with 24-word overlap | Project code |
| `all-minilm:22m` through Ollama | Optional 384-dimensional meaning vectors | About 46 MB model download; estimated 200–500 MB working memory, excluding application/OS overhead | Apache-2.0 |
| `qwen2.5:1.5b` through Ollama | Optional query interpretation | About 986 MB model download; estimated 2–3 GB working memory, excluding application/OS overhead | Apache-2.0 |
| Ollama runtime | Optional local model runner | Separate installation; additional runtime/disk overhead | MIT |

Memory figures are planning estimates, not measurements on this computer. Model downloads and installation consume additional temporary/cache storage. Models are not bundled and were not downloaded during implementation.

Vectors use normalized float32 SQLite BLOBs: 384 × 4 = 1,536 bytes per embedded chunk before database/index overhead. Exact cosine ranking avoids adding a vector database or native vector extension. Its linear cost needs benchmarking before a large-library release.

Model artifacts and licenses: [MiniLM registry](https://ollama.com/library/all-minilm:22m), [Qwen registry](https://ollama.com/library/qwen2.5:1.5b), [Ollama license](https://github.com/ollama/ollama/blob/main/LICENSE), [SQLite copyright](https://www.sqlite.org/copyright.html). Integration uses the official [embedding](https://docs.ollama.com/api/embed) and [generation](https://docs.ollama.com/api/generate) APIs.

`local_models.py` connects only to `127.0.0.1:11434`, ignores environment proxies, rejects redirects, and accepts the configured names plus digest prefixes `1b226e2802db` and `65ec06548149`. Unknown versions are not treated as ready. No arbitrary model URL can be supplied through the UI. Downloads require enabled models and an explicit confirmed request.

Only approved chunk text reaches the local embedding runner. The language model receives the user message, without document contents. No cloud API is integrated. See [local-only setup](LOCAL_MODELS_SETUP.md) for the runner settings.

## Database and lifecycle

Migration 4 adds:

- `intelligence_documents`: content hash, parser version, engine version, preparation state.
- `chunks` and `chunks_fts`: source position/location, text, optional versioned embedding.
- `library_groups`, `group_assignments`, `group_corrections`: generated and corrected virtual membership.
- `conversations`, `discovery_turns`: intent/context and versioned evidence references.
- `intelligence_jobs`, `intelligence_settings`: durable work and opt-in configuration.

Migration backfills pending work from existing extracted documents. It does not open source files. Background workers prepare cached text, preserving page/section/block locations. Original indexing still supplies SHA-256 hashes and parser versions.

Document publication and file status/hash triggers invalidate obsolete chunks and generated memberships. New derived data publishes in one transaction after access/version checks. Metadata-only moves can preserve matching chunks/vectors and update path-based classification. Unchanged completed documents are skipped; enabling embeddings can fill missing vectors without replacing unchanged chunks. Manual group assignments override automatic assignments for the corrected kind and survive document changes.

The grouping baseline uses explicit subjects/course labels, headings, filenames, approved folder context, and established library subjects. It supports multiple subjects/topics/types per file and uses Uncategorized when subject evidence is insufficient. It is a conservative rules baseline, not trained semantic classification.

Chat runs on a separate worker from rebuild/download work. Queued/running jobs are recorded in SQLite, cancellation is checked between units/batches, and interrupted background work is recovered on restart. Cancelling preparation defers pending work so automatic retries do not defeat cancellation; a manual rebuild resumes it. An in-flight model request may take up to its timeout before cancellation completes. Completed documents remain usable after partial cancellation.

## Permission enforcement

- Active and paused approved roots permit retrieval. Revoked roots do not.
- Canonical containment and every path component are checked; symlinks/reparse points, including Windows junctions, are rejected. Scans skip them too.
- Current size/mtime and published content/engine/parser versions exclude stale evidence. Scan hashing establishes the content version; same-size edits that deliberately preserve timestamps require a rescan to detect.
- Access is checked before text retrieval/model batches, before publishing results, when hydrating history, and before native actions. An already submitted local request cannot be recalled; its output is discarded if access/version changed.
- Removing a folder clears visible evidence immediately. Cached source text may remain in the database under excluded records for existing indexer behavior, but is inaccessible through search, preview, groups, and citations. This is access revocation, not secure erasure.
- User-authored conversation messages remain in history. They are not document excerpts and are not rewritten on revocation.

## Code boundaries

| Area | Files |
|---|---|
| Access, migration, invalidation | `backend/sift_indexer/access.py`, `intelligence_schema.py`, `db.py` |
| Language, grouping, model transport | `discovery_language.py`, `grouping.py`, `local_models.py` |
| Jobs, retrieval, evidence, history | `intelligence.py`, `intelligence_api.py` |
| Existing index/search integration | `indexer.py`, `api.py` |
| Trusted native boundary | `desktop/electron/main.ts`, `preload.ts` |
| Approved chat UI | `desktop/src/components/DiscoveryPanel.tsx`, `discovery.css`, `App.tsx`, shared types/icons |

API routes under `/intelligence` cover status, model configuration/download, rebuild, chat, jobs/cancellation, conversations/turns/citations, and group editing. They reuse service authentication. The API binds only to loopback; the renderer never receives its token.

## Deliberate limits

English-first language/grouping rules have limited vocabulary and can require clarification or manual corrections. Optional models do not guarantee recall or correct classification. Real model quality, mixed-library scale, CPU latency, and memory use have not been benchmarked. No document answering, summarization, OCR, file modification, sync, accounts, or unrelated modules were added.
