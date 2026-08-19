# Repository Guidelines

Merged into **[CLAUDE.md](CLAUDE.md)** on 2026-07-25 — read that file. It is the
operational contract (layout, pipeline, schema, conventions, QA). **[STRATEGY.md](STRATEGY.md)**
holds the roadmap, live numbers, open questions, and the decision log.

This stub exists only because agent tooling looks for `AGENTS.md` by convention.
Do not add content here; it will drift.

## Cursor Cloud specific instructions

This is a Python 3 CLI / data-pipeline project (no web app, no long-running
service). Read `CLAUDE.md` for the full operational contract; the notes below are
only the non-obvious cloud caveats.

- **Use the repo-local venv:** run everything through `.venv/bin/python` (e.g.
  `.venv/bin/python -m unittest discover tests`), not the system interpreter.
  The startup update script creates `.venv` and installs `requirements.txt`.
- **The corpus DB is restored from a tracked snapshot, not downloaded.** The
  startup script decompresses `corpus/krishnamurti-corpus.db.zst` →
  `corpus/krishnamurti-corpus.db` (gitignored). The retrieval/citation loop and
  some tests need it; if it is missing, run
  `zstd -d -f corpus/krishnamurti-corpus.db.zst -o corpus/krishnamurti-corpus.db`.
- **`build_catalog.py` rewrites tracked artifacts every run** — it atomically
  regenerates `catalog/krishnamurti.db`, `catalog/manifest.json`, and
  `catalog/exports/*` from the PDF. After a smoke-test rebuild, `git checkout --`
  those paths unless you intend to commit refreshed data.
- **System tools live in the base image, not the update script:** `pdftotext`
  (poppler-utils) is required by `build_catalog.py`; `zstd` and `python3-venv`
  are required for the steps above. `yt-dlp`, `whisper-cli`, and `ffmpeg` are
  only for downloading/transcribing media, which needs the gitignored `library/`
  tree and YouTube cookies — neither exists on a clone, so those flows cannot run
  here and are out of scope for cloud dev.
- **QA gates (all fast, run before committing):**
  `build_citations.py --verify`, `build_concept_vault.py --check`,
  `retrieval_report.py --check`, `strategy_stats.py --check`.
