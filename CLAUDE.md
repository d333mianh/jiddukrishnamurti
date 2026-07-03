# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout

As of 2026-07-01 the git repo **is** this directory, which lives in iCloud Drive
alongside the media library it drives:

    ~/Library/Mobile Documents/com~apple~CloudDocs/00-cod3/jiddu-krishnamurti/

All catalog code, scripts, the SQLite DB, the Obsidian vault, and the directory
PDFs live at the repo root; **run scripts and `git` from here.** Because the repo
root now equals the media root, `library/` (gitignored) sits *inside* the tree
and all `ROOT`-relative paths resolve automatically (each script sets
`ROOT = Path(__file__).resolve().parents[1]`). Paths below are relative to this
root.

- **`compare/`** — a standalone STT-provider evaluation sandbox (**gitignored,
  not under git**). One-off scripts and transcripts used to pick the
  speech-to-text engine; see "STT evaluation" below. No dependency on the catalog
  code.

## What this project is

A catalog + media library + (in-progress) searchable teachings corpus built on the
complete Krishnamurti Foundation Trust (KFT) recordings archive (~1,540 items).
Read **`STRATEGY.md`** first for the multi-phase roadmap and the
dated decision log — it is the source of truth for *why* things are done a
certain way (STT engine choice, citation granularity, relevance tiers, etc.).

## Commands

```bash
# run from the repo root (the iCloud jiddu-krishnamurti/ folder)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # openpyxl, pandas, pypdf
.venv/bin/python scripts/build_catalog.py    # rebuild DB + exports + Obsidian (--pdf PATH, --force)
```

The system Homebrew Python is PEP 668 externally-managed — install into the
repo-local `.venv` (gitignored), not system-wide.

External tools the scripts shell out to (not in requirements.txt): `pdftotext`
(poppler), `yt-dlp` (downloads), `ffmpeg` + `whisper-cli` (whisper.cpp, local
transcription). `compare/` and `scripts/build_keyterms.py` additionally need
`jiwer` and `wordfreq`. There is no test suite, linter config, or CI.

Each script is a standalone CLI with `--help`; most take `--dry-run` and
`--limit N`. Run any of them directly, e.g. `python3 scripts/download_series.py LO61T1`.

## The SQLite catalog is canonical

`catalog/krishnamurti.db` is the single source of truth; CSV/XLSX exports and the
Obsidian vault are regenerated from it. Schema (see `.schema`):

- **`items`** — one row per recording, keyed by `code` (e.g. `LO61T1`). `code`
  is the join key everywhere. `future_path` is the catalog-relative media path
  (always begins `library/...`).
- **`sections`** / **`series`** — PDF-order groupings (`mega_group`, `pdf_order`).
- **Phase-2 tables** (`item_links`, `item_subtitles`, `item_media`) — link
  discovery and per-item download/transcription **state**, tracked by `status`.

Table DDL is not inline in `build_catalog.py`; each state table has its own
`scripts/*_schema.py` module (`footage_schema`, `media_schema`, `subtitle_schema`,
`segment_schema`) imported by the build/backfill scripts. **Change a table's shape
in its schema module, not in ad-hoc SQL.** Inspect the live DB directly with
`sqlite3 catalog/krishnamurti.db` (`.schema`, `.tables`).

### Rebuild semantics — the central gotcha

`build_catalog.py` **recreates the DB from the PDF every run — atomically**: it
builds into `catalog/krishnamurti.db.rebuild` and `os.replace()`s over the
canonical DB only after a successful commit, so any mid-rebuild failure leaves
the old DB intact. Before touching anything it validates the parse
(`validate_parse`): unknown section numbers, a >2% item-count drop vs the last
`import_runs` row, or PDF items reaching the overlay range (`pdf_order >= 1484`)
abort the rebuild. `--force` overrides the item-count check and permits
manual-subtitle orphan drops (below); it does NOT bypass the unknown-section or
overlay-range guards.

- The three phase-2 tables are snapshotted and restored keyed by item `code`
  (`snapshot_phase2_tables` / `restore_phase2_tables` in `build_catalog.py`).
- The non-PDF overlay sections are applied **inside** the rebuild — save_db calls
  `add_education_directory.apply(conn)` (10A, 11 `GSBR74DT` items) and
  `add_channel_recordings.apply(conn)` (11A, @KFoundation channel items) *before*
  the phase-2 restore — so overlay items **and their subtitle/media/link rows
  survive every rebuild**. Both `add_*` scripts remain standalone idempotent CLIs
  for incremental use.
- If the restore would drop `kind='manual'` subtitle rows (an item code vanished
  from the catalog — e.g. a PDF code change), the rebuild **fails listing the
  codes**; investigate before reaching for `--force`.
- After a rebuild, `backfill_media.py` still re-syncs `item_media` from disk.

**Canonical rebuild order:** `build_catalog.py` (includes 10A/11A) →
`discover_links.py` → (downloads) → `backfill_media.py` → `parse_vtt.py`.

## Teachings corpus — L1/L2 (Phase 1)

The searchable-corpus layer sits *on top of* the catalog. `segment_schema.py`
defines four tables + an FTS index, built from manual VTTs by `parse_vtt.py`:

- **`transcripts`** (L1) — one row per ingested transcript file (provenance).
- **`segments`** (L2) — speaker-attributed turns (contiguous same-speaker cues
  merged). Speaker tags: `K`, `Q`, named interlocutors, `ANN`, `UNK`.
- **`passages`** — K monologues sub-chunked to ~150–200 words at sentence
  boundaries; **this is the citation unit** (each carries its own `t_start`/`t_end`).
- **`speaker_labels`** — the per-item label registry.
- **`passages_fts`** — FTS5 over K-only passage text.

`parse_vtt.py` is idempotent per `(item, kind, language)` (re-ingest deletes prior
rows first). It builds a **per-item** speaker registry, admitting a `Label:` only
if it's a trusted seed *or* recurs ≥2× — this is what rejects false positives like
`"We are asking:"`. Run it from the catalog (`--event-type T [--limit N]`) or
standalone on a single file (`--vtt … --item …`).

**Gotcha — these tables are deliberately NOT in `PHASE2_TABLES`.** The
snapshot/restore (above) re-keys rows by `items.code` with fresh autoincrement
ids; doing that here would corrupt the `transcript_id`/`segment_id`
cross-references. Instead `ensure_segment_schema()` (called from
`build_catalog.init_db`) recreates them **empty** on every rebuild, and
`parse_vtt.py` re-populates them afterward. So corpus repopulation is a step
*after* the rebuild order, not part of the phase-2 restore.

Ingestion guards: `parse_vtt.py` refuses a 0-cue parse in *both* batch and
standalone modes (`ingest()` itself raises — protects existing transcripts from
header-only/evicted files), sets `PRAGMA foreign_keys=ON`, and batch mode only
ingests items with `items.corpus_include = 1`. That scope gate
(`ensure_corpus_include()` in `segment_schema.py`, populated on rebuild) marks
the 12 `EBM` excerpts 0 so re-cut passages never duplicate their parent talks
in FTS.

## Media lives in iCloud (now at the repo root)

Media files are **not** in git (`library/` is gitignored). The root is iCloud
Drive: `~/Library/Mobile Documents/com~apple~CloudDocs/00-cod3/jiddu-krishnamurti/`
— since 2026-07-01 this is also the repo root, so `library/<section>/<series>/`
sits *inside* the working tree (still gitignored). Override with
`KRISHNAMURTI_MEDIA_ROOT` or `--library-root` (see `media_root()` /
`resolve_media_path()` in `download_series.py`, which other scripts import).

Because iCloud evicts files locally, scripts materialize on demand (`brctl
download`) and may evict again afterward — relevant when a path "exists" but has
zero local bytes.

## Download & discovery pipeline

`discover_links.py` populates `item_links` purely from `youtu.be` hyperlinks
embedded in the PDF (it wipes and rebuilds the table each run **except** rows whose
`notes` start with "Manually verified"). Downloads go through `yt-dlp`, preferring
audio format 140 (129 kbps AAC). Layered entry points, all writing `item_media` /
`item_subtitles` status: `download_item.py` (one code) → `download_series.py` (a
series) → `download_section.py` (a section); plus targeted `download_missing_*.py`
and `redownload_audio.py` (replaces sub-bitrate/corrupt audio). YouTube auth uses
`www.youtube.com_cookies.txt` / `catalog/.yt-browser-cookies.txt` (both gitignored).

`organize_library.py` moves/renames already-downloaded media under `library/` to
match the catalog's series subfolders and PDF order (takes `--dry-run`); run it
after `backfill_media.py` if on-disk layout has drifted from the DB.

## Transcription

`scripts/transcribe_whisper.py` is the **interim** local pass (whisper.cpp
`large-v3-turbo`, `-mc 0`, **no prompt** — these exact settings were chosen by a
pilot eval; do not "improve" them without re-reading the docstring and STRATEGY.md).
It is idempotent/resumable, writes `<stem>.whisper.{vtt,json,txt}` next to the
media, records `item_subtitles.kind='whisper-large-v3-turbo'`, and stops gracefully
when `catalog/logs/whisper_backfill.stop` exists.

The corpus distinguishes transcript provenance by `item_subtitles.kind`: `manual`
(KFT-edited, gold standard) > a future ElevenLabs Scribe v2 pass > local whisper.
Filter/supersede by `kind`; never overwrite manual subs.

## STT evaluation (`compare/`)

How the production STT engine was chosen (verdict: **ElevenLabs Scribe v2 +
keyterm prompting**, recorded in STRATEGY.md). `run_stt.sh elevenlabs|xai <audio>
<label> [keyterms.json]` calls a provider (one multipart `keyterms` field *per
term*); `scripts/build_keyterms.py` mines the keyterm lexicon from the manual-sub
corpus using `wordfreq` zipf rarity; `compare_texts.py` / `compare_piece.py` score
WER/CER with `jiwer` against manual VTTs (the reference). When evaluating, exclude
a test item's own subs from the keyterm lexicon to avoid leakage.
