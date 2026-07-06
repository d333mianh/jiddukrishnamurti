# Repository Guidelines

## Project Overview

Personal archive pipeline for the complete Krishnamurti Foundation Trust (KFT) recordings catalog (~1,541 items, ~1,960 hours). Parses the KFT 2026 Full-Length Directory PDF into a SQLite catalog, resolves YouTube links, downloads media into an iCloud-hosted `library/`, transcribes where no manual subtitles exist, and builds a searchable teachings corpus (transcripts → speaker segments → citable K passages with FTS). Read `STRATEGY.md` first for the L0–L4 roadmap and the dated decision log; `CLAUDE.md` is the operational contract this file mirrors.

## Architecture & Data Flow

Canonical state lives in **`catalog/krishnamurti.db`** (SQLite). Everything else — CSV/XLSX exports, the Obsidian vault, `manifest.json` — is regenerated output. `items.code` (e.g. `LO61T1`) is the universal join key.

Pipeline order (each stage a standalone script in `scripts/`):

```
KFT PDF ─ build_catalog.py ─→ krishnamurti.db + catalog/exports/ + obsidian/
             │   (applies 10A/11A overlays from catalog/*.json inside the rebuild
             │    via add_education_directory.apply / add_channel_recordings.apply;
             │    the add_* scripts remain standalone idempotent repair tools)
             ├─ discover_links.py            (PDF youtu.be links → item_links)
             ├─ download_series|section|item.py  (yt-dlp → library/, item_media)
             ├─ backfill_media.py            (disk → item_media reconcile)
             ├─ download_subtitles.py        (manual VTTs → item_subtitles)
             ├─ transcribe_whisper.py        (interim STT where no manual subs)
             └─ parse_vtt.py                 (VTT → corpus/krishnamurti-corpus.db)
```

Catalog DB tables include `sections` (22), `items` (1,541), `series` (259), `item_links`, `item_media`, and `item_subtitles`. The separate gitignored corpus DB contains `transcripts`, `segments`, `passages`, `speaker_labels`, `transcript_qa`, `corpus_meta`, and `passages_fts`.

**Critical rebuild semantics**: `build_catalog.py` recreates the catalog DB from the PDF every run — **atomically** (builds `krishnamurti.db.rebuild`, `os.replace()` after commit; a failed rebuild leaves the old DB intact). `validate_parse` aborts before anything is touched on unknown section numbers, a >2% item-count drop vs the last import, or PDF items reaching the overlay range (`pdf_order >= 1484`). `--force` overrides the item-count check and permits manual-subtitle orphan drops; it does NOT bypass the unknown-section or overlay-range guards. Phase-2 tables (`item_links`, `item_subtitles`, `item_media`) are snapshotted/restored keyed by `code` — overlay items included, since overlays are applied before the restore. A restore that would drop `kind='manual'` subtitle rows fails the rebuild listing the codes. The separate corpus DB is keyed by item code and is not touched by catalog rebuilds. Canonical order: `build_catalog` (includes 10A/11A) → `discover_links` → downloads → `backfill_media` → `parse_vtt`.

**Link discovery is destructive**: each `discover_links.py` run deletes and rebuilds `item_links`, preserving only rows whose notes start with "Manually verified". Mark hand-checked links that way or they will be wiped.

## Key Directories

- `scripts/` — all pipeline code (~21 Python scripts + 2 shell wrappers). Schema DDL lives in `scripts/*_schema.py` (`footage_schema`, `media_schema`, `subtitle_schema`, `segment_schema`); never alter table shape with ad-hoc SQL.
- `catalog/` — SQLite DB, `manifest.json`, supplement JSONs (`education_directory_2026.json`, `channel_recordings_2026.json`), `link_cache.json`, `exports/` (CSV/XLSX), `logs/` (gitignored run logs).
- `corpus/` — generated, gitignored L1/L2 SQLite DB (`krishnamurti-corpus.db`); tracked README only.
- `library/` — gitignored media tree: `{section-slug}/{pdf_order:04d}-{series_code}/{CODE} - Title.{m4a|mp4|en.vtt|whisper.*}` (e.g. `library/1A-public-meetings-england/0000-LO61T1-12/`). Paths stored in `items.future_path`.
- `obsidian/` — generated vault (index + 10 mega-group notes). `build_catalog.py` runs `shutil.rmtree` on the whole directory — never hand-edit these files.
- `compare/` — gitignored STT evaluation sandbox (WER/CER scoring vs manual VTT references). Not part of the production pipeline; verdict (ElevenLabs Scribe v2 + keyterms) is recorded in `STRATEGY.md`.

## Development Commands

```bash
# From repo root (the iCloud jiddu-krishnamurti/ folder)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # system pip is PEP 668-managed
.venv/bin/python scripts/build_catalog.py   # rebuild (needs pdftotext); --pdf PATH, --force
python3 scripts/add_education_directory.py  # standalone overlay repair (also runs inside rebuild)
python3 scripts/add_channel_recordings.py   # standalone overlay repair (also runs inside rebuild)
python3 scripts/discover_links.py [--archive]
python3 scripts/download_series.py LO61T1-12 --cookies-from-browser chrome
python3 scripts/download_section.py 1A --video --no-subs --cookies-from-browser chrome
python3 scripts/download_item.py LO61T1 --audio best
python3 scripts/backfill_media.py [--dry-run]
python3 scripts/transcribe_whisper.py [--limit N] [--dry-run]
python3 scripts/parse_vtt.py --event-type T --limit 50           # batch corpus ingest
python3 scripts/parse_vtt.py --vtt path/to/X.en.vtt --item X --kind manual
python3 scripts/corpus_stats.py [--csv catalog/exports/corpus-stats.csv]
python3 -m unittest discover tests
sqlite3 catalog/krishnamurti.db          # .tables / .schema for inspection
```

External binaries required (not in `requirements.txt`): `pdftotext` (poppler), `yt-dlp`, `ffmpeg`, `whisper-cli`; `brctl` (macOS) for iCloud materialization. `compare/` additionally needs `jiwer` and `wordfreq`.

## Code Conventions & Common Patterns

- **Style**: Python 3.10+, `from __future__ import annotations`, `pathlib.Path`, union types. No formatter/linter config — match surrounding code.
- **Script anatomy**: standalone `argparse` CLI + `main()` + `if __name__ == "__main__"`. Most support `--help`, `--dry-run`, `--limit N`. Exceptions: `build_catalog.py`, `add_*.py` take no args.
- **Paths**: every script derives `ROOT = Path(__file__).resolve().parents[1]`; catalog state is `catalog/krishnamurti.db`, generated L1/L2 data is `corpus/krishnamurti-corpus.db`, and `future_path` values are repo-relative `library/...`. Media root override: `KRISHNAMURTI_MEDIA_ROOT` env or `--library-root`; reuse `media_root()` / `resolve_media_path()` from `scripts/download_series.py`.
- **Cross-module reuse**: shared download/auth helpers live in `scripts/download_series.py`; siblings use `sys.path.insert(0, scripts_dir)` + lazy imports.
- **Idempotency**: DB writes use `INSERT ... ON CONFLICT DO UPDATE`; `parse_vtt.py` is idempotent per `(item, kind, language)` via delete-before-reinsert. Re-add scripts are safe to re-run.
- **Error handling / logging**: `print()` to stdout; `sys.exit(1)` after failure counts; `transcribe_whisper.py` uses a timestamped `log()` and a graceful stop file (`catalog/logs/whisper_backfill.stop`). No logging framework.
- **Provenance via `kind`**: subtitle precedence is manual > (future) Scribe > `whisper-large-v3-turbo`. Filter or supersede by `item_subtitles.kind`; **never overwrite manual subtitles**.
- **YouTube auth**: cookies resolved via `resolve_yt_auth()` — env vars (`KRISHNAMURTI_YT_COOKIES_FILE`, `KRISHNAMURTI_YT_COOKIES_BROWSER`), `www.youtube.com_cookies.txt`, `catalog/.yt-browser-cookies.txt`, or `--cookies-from-browser chrome` (preferred for video; stale Netscape files 403). Cookie files are gitignored — keep them out of git.
- **Naming**: item codes = place+year+event+number (`LO61T1`, `GSBR74DT01`); section slugs `{number}{letter}-{kebab-title}` (`6C-k-school-discussions-usa-and-canada`).

## Important Files

- `scripts/build_catalog.py` — largest module; PDF parse, DB save, exports, Obsidian generation, phase-2 snapshot/restore.
- `scripts/parse_vtt.py` — corpus ingest (`Cue`/`Segment` dataclasses, speaker registry, passage chunking ~150–260 words).
- `scripts/download_series.py` — hub for media paths and yt-dlp auth; other download scripts delegate to it.
- `scripts/segment_schema.py` / `subtitle_schema.py` / `media_schema.py` / `footage_schema.py` — the only place table DDL may change.
- `scripts/transcribe_whisper.py` — interim STT; settings (`large-v3-turbo`, `-mc 0`, no prompt) are pilot-frozen: do not change without updating its docstring and `STRATEGY.md`.
- `CLAUDE.md`, `STRATEGY.md`, `STRATEGY_REVIEW.md` — operational contract, roadmap/decision log, adversarial review of both.
- `catalog/manifest.json` — import-run metadata only (its counts lag the live DB; trust SQLite).

## Runtime/Tooling Preferences

- **Runtime**: system `python3` (3.10+); no virtualenv or lockfile committed; `pip install -r requirements.txt`. No Node/Bun toolchain (the lone `.claude/workflows/*.js` is a Claude Code workflow, not app code).
- **Platform**: macOS + iCloud Drive. The repo root *is* the iCloud folder; files can exist as zero-byte placeholders until materialized (`brctl download <path>`). Check file size before assuming readable media.
- **Git hygiene**: `library/`, `compare/`, `catalog/logs/`, all `*cookies*.txt`, and venvs are gitignored. Never commit media or cookies.

## Testing & QA

- Parser regression tests use stdlib `unittest`; there is no linter or CI. Verification is otherwise script-level:
  - `.venv/bin/python -m unittest discover tests`
  - Most CLIs offer `--dry-run` and `--limit N` — use them to smoke-test changes before full runs.
  - `python3 scripts/segment_schema.py corpus/krishnamurti-corpus.db catalog/krishnamurti.db` smoke-ensures corpus schema.
  - Inspect effects with `scripts/corpus_stats.py`, SQLite, and `catalog/exports/*.csv`.
- **Transcription QA** lives in `compare/`: `run_stt.sh elevenlabs|xai <audio> <label> [keyterms.json]` generates hypotheses; `compare_texts.py` / `compare_piece.py` score WER/CER vs manual `.en.vtt` references and emit `.diff.txt` word alignments. Avoid keyterm leakage when evaluating (exclude the eval item from `build_keyterms.py`).
- `.claude/workflows/quick-finish-review.js` defines an adversarial diff-review workflow for `parse_vtt.py` / `build_catalog.py` changes.
