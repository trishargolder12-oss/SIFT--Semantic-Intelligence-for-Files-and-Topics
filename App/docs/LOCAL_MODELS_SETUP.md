# Optional local models on Windows

SIFT 0.3.0 also offers an explicit local OCR pack and optional Qwen3-VL visual descriptions. See the [syllabus organizer setup and measured limits](SYLLABUS_ORGANIZER.md). The text discovery setup below still applies.

SIFT 0.2.0 works offline immediately in keyword mode. Local models are optional. They are disabled by default, and SIFT never starts a download automatically.

## Start without models

1. Add folders in the library using **Add folder** and let indexing finish.
2. Open **Find it with SIFT** from the navigation or search area.
3. Ask for a file/topic, choose folder/type filters, or select a virtual section. Results show why they match and source excerpts.

Keyword mode supports conversational phrasing, library-supported acronyms, spelling suggestions, dates, and follow-ups. It does not claim meaning-based retrieval without the embedding model.

## Enable meaning-based retrieval

1. Install [Ollama for Windows](https://ollama.com/download/windows). SIFT's **Local models & processing → Get Ollama for Windows** opens that fixed official page. This runtime is installed separately.
2. Configure Ollama for local-only operation. Set user environment variable `OLLAMA_NO_CLOUD` to `1`; keep `OLLAMA_HOST` at `127.0.0.1:11434`. Fully quit and restart Ollama after changing environment variables. See [Ollama's FAQ](https://docs.ollama.com/faq).
3. In SIFT, expand **Local models & processing** and choose **Enable local models**. The panel reports whether the local runner is available.
4. Press **Download 46 MB** for `all-minilm:22m`. This is an explicit internet download through the local runner; library files and messages are not part of the download request. Wait for completion and background discovery preparation.
5. Meaning + keyword retrieval becomes available. Existing keyword evidence remains useful while vectors are being prepared. Use **Rebuild discovery index** to retry deferred work or refresh incomplete preparation.
6. Optionally download `qwen2.5:1.5b` using **Download 986 MB** for additional query interpretation. It is not required for keyword or embedding retrieval. Replies continue to use verified retrieval evidence.

SIFT accepts only its configured model versions. A differently tagged or changed model may not show as installed; use the supported download or await a catalog update. A failed/cancelled download can be retried; the runner may retain partial artifacts.

## Storage and memory

| Item | Location / requirement |
|---|---|
| Extracted text, chunks, vectors, groups, chat history | `library.sqlite` in Electron's local app user-data directory |
| Ollama model files | Normally `%USERPROFILE%\.ollama\models`; a separately configured `OLLAMA_MODELS` can change this |
| MiniLM model | Approximately 46 MB download; estimated 200–500 MB working memory |
| Qwen model | Approximately 986 MB download; estimated 2–3 GB working memory |
| Per-chunk vector | 1,536 bytes plus SQLite overhead |

Estimates exclude SIFT, Ollama runtime, operating system, database text/indexes, and download/cache overhead. They are not measured performance guarantees. Both model artifacts use Apache-2.0; the runner uses MIT. Details and primary links are in the [architecture document](INTELLIGENCE_ARCHITECTURE.md).

## Offline use, cancellation, and removal

After setup, disconnecting the internet does not prevent normal indexing, grouping, keyword discovery, or installed local model inference. SIFT communicates with Ollama only at loopback and rejects proxies/redirects.

Use **Cancel processing** for rebuild/download work or **Cancel request** for chat. Cancellation is cooperative; a current local model call may finish or time out first. Completed preparation remains saved. A cancelled request does not publish a partial assistant turn.

**Disable local models** returns SIFT to keyword processing without deleting model files. Model storage is managed by Ollama separately. No model download or real model quality benchmark was performed during this implementation.

If Ollama is stopped, missing, or returns incompatible data, SIFT keeps keyword discovery available. If a folder was revoked, its old search results and chat citations stop working. Pausing indexing preserves access to existing current files.
