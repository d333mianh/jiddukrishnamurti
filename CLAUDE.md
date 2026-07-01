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
pip install -r requirements.txt        # openpyxl, pandas, pypdf
python3 scripts/build_catalog.py       # rebuild DB + exports + Obsidian from PDF
```

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

### Rebuild semantics — the central gotcha

`build_catalog.py` **deletes and recreates the DB from the PDF every run.** Before
unlinking, it snapshots the three phase-2 tables and restores them keyed by item
`code` (`snapshot_phase2_tables` / `restore_phase2_tables` in `build_catalog.py`).
Consequences:

- Only items present in the **Full-Length Directory PDF** survive a rebuild.
  Items added from other sources are **dropped**, and their phase-2 rows are
  dropped as orphans.
- Two scripts re-add the non-PDF items and are **idempotent specifically so they
  can be re-run after every rebuild**:
  - `add_education_directory.py` → section 10A (11 `GSBR74DT` items)
  - `add_channel_recordings.py` → section 11A (items found only on the
    @KFoundation YouTube channel; marked by `source_pdf` and `item_links.source =
    'kft_channel_scan'` vs PDF links' `'kft_pdf_youtube'`)
- After re-adding, run `backfill_media.py` to re-sync `item_media` from files
  already on disk (it reflects current disk state, healing drifted rows).

**Canonical rebuild order:** `build_catalog.py` → `add_education_directory.py` →
`add_channel_recordings.py` → `discover_links.py` → (downloads) → `backfill_media.py`.

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
*after* the rebuild order, not part of the phase-2 restore. (The current canonical
DB predates this wiring; the tables appear empty on the next `build_catalog.py` run.)

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
