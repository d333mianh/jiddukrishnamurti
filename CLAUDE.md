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
complete Krishnamurti Foundation Trust (KFT) recordings archive (1,541 items,
1,963 h). It parses the KFT 2026 Full-Length Directory PDF into a SQLite catalog,
resolves YouTube links, downloads media into an iCloud-hosted `library/`,
transcribes where no manual subtitles exist, and builds a searchable teachings
corpus (transcripts → speaker segments → citable K passages with FTS) plus an L3
registry of 36 concept "roots".

Read **`STRATEGY.md`** first — it is the single strategy document (L0–L4
roadmap, live numbers, open questions, dated decision log) and the source of
truth for *why* things are done a certain way (STT engine choice, citation
granularity, relevance tiers, the concept registry). This file is the
operational contract: *how* to work in the repo.
`.claude/workflows/quick-finish-review.js` is an adversarial diff-review
workflow for `parse_vtt.py` / `build_catalog.py` changes.

### Key directories

- **`scripts/`** — all pipeline code. Schema DDL lives in `scripts/*_schema.py`;
  never alter table shape with ad-hoc SQL.
- **`catalog/`** — SQLite DB, `manifest.json` (import-run metadata only; its
  counts lag the live DB — trust SQLite), supplement JSONs
  (`education_directory_2026.json`, `channel_recordings_2026.json`),
  `link_cache.json`, `exports/` (CSV/XLSX), `logs/` (gitignored).
- **`corpus/`** — the L1/L2 DB. The live `krishnamurti-corpus.db` is gitignored;
  a compressed snapshot (`krishnamurti-corpus.db.zst`, 67 MB) **is** tracked —
  see "Restoring the corpus from a fresh clone" below.
- **`concepts/`** — tracked L3 data: `concepts.jsonl` (36 roots + 3 deprecated
  tombstones) and `citations.jsonl` (the curated L4 quotations).
- **`library/`** — gitignored media tree:
  `{section-slug}/{pdf_order:04d}-{series_code}/{CODE} - Title.{m4a|mp4|en.vtt|whisper.*}`.
  Paths stored in `items.future_path`.
- **`obsidian/`** — generated vault. Two generators own disjoint parts of it;
  see "Obsidian vault" below. Never hand-edit generated notes.
- **`compare/`** — gitignored STT evaluation sandbox; not part of the production
  pipeline.
- **`archive/`** — parked work, deliberately outside the live pipeline. Nothing
  here is imported or run; each subdirectory has a `README.md` saying what it
  was and how to restore it. Currently: `archive/iching/` (the I Ching
  navigation layer, parked 2026-07-25 pending a decision).

## Commands

```bash
# run from the repo root (the iCloud jiddu-krishnamurti/ folder)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # openpyxl, pandas, pypdf
.venv/bin/python scripts/build_catalog.py    # rebuild DB + exports + Obsidian (--pdf PATH, --force)
.venv/bin/python -m unittest discover tests  # parser/schema regressions (tests/test_*.py)
```

The system Homebrew Python is PEP 668 externally-managed — install into the
repo-local `.venv` (gitignored), not system-wide.

External tools the scripts shell out to (not in requirements.txt): `pdftotext`
(poppler), `yt-dlp` (downloads), `ffmpeg` + `whisper-cli` (whisper.cpp, local
transcription). `compare/` (including `compare/build_keyterms.py`) additionally
needs `jiwer` and `wordfreq`. Parser regressions use stdlib `unittest`; there is
no linter config or CI.

Pipeline scripts are standalone argparse CLIs with `--help`; most take `--dry-run`
and `--limit N`. Run any directly, e.g. `python3 scripts/download_series.py LO61T1`.
The `*_schema.py` modules are primarily importable helpers (some take simple
positional smoke-test args instead of argparse).

### Restoring the corpus from a fresh clone

A clone is ~31 MB and self-sufficient for the vault: the tests pass and
`build_concept_vault.py --check` regenerates all 37 notes, because
`concepts/citations.jsonl` carries each quote and link. It is **not** sufficient
for phase 3 — `retrieve_concept.py` and `build_citations.py` need the corpus DB,
which is gitignored. Restore it first:

```bash
zstd -d corpus/krishnamurti-corpus.db.zst -o corpus/krishnamurti-corpus.db
.venv/bin/python scripts/build_citations.py --verify   # 25/25 = corpus is good
```

`library/` (media + manual VTTs) and the YouTube cookie files are not in the
repo and cannot be — so downloading, transcribing, and re-ingesting only work on
a machine that has the iCloud tree. Curation does not need them. Refresh the
snapshot deliberately, on milestones; see `corpus/README.md` for how and why.

## The SQLite catalog is canonical pipeline state

`catalog/krishnamurti.db` is the source of truth for catalog and pipeline state;
CSV/XLSX exports and the Obsidian vault are regenerated from it. Generated
L1/L2 transcript text lives separately in the gitignored
`corpus/krishnamurti-corpus.db`. Catalog schema (see `.schema`):

- **`items`** — one row per recording, keyed by `code` (e.g. `LO61T1`). `code`
  is the join key everywhere. `future_path` is the catalog-relative media path
  (always begins `library/...`).
- **`sections`** / **`series`** — PDF-order groupings (`mega_group`, `pdf_order`).
- **Phase-2 tables** (`item_links`, `item_subtitles`, `item_media`) — link
  discovery and per-item download/transcription state. `item_subtitles` and
  `item_media` carry explicit `status` fields; `item_links` stores discovery/match
  metadata (no `status` column).

Schema DDL is split: catalog core plus the `item_links`/bootstrap subtitle DDL
live in `build_catalog.py`; reusable media/subtitle/footage/corpus schema helpers
live in `scripts/*_schema.py` (`footage_schema`, `media_schema`, `subtitle_schema`,
`segment_schema`). **Change a table's shape at its canonical definition, not in
ad-hoc SQL.** Inspect the live DB directly with
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

Catalog rebuilds do not create, clear, or restore corpus tables. Corpus rows are
keyed by stable item code, so the separate corpus DB survives a rebuild.

**Canonical pipeline order:** `build_catalog.py` (includes 10A/11A) →
`discover_links.py` → (downloads) → `backfill_media.py` → `parse_vtt.py`.

## Teachings corpus — L1/L2 (Phase 1)

The searchable-corpus layer sits *on top of* the catalog in the separate,
gitignored `corpus/krishnamurti-corpus.db`. `segment_schema.py` defines its
tables and FTS index, built from manual VTTs by `parse_vtt.py`:

- **`transcripts`** (L1) — one row per ingested transcript file (provenance),
  including the catalog `corpus_tier` (`A|B|C|X`) at ingest time.
- **`segments`** (L2) — speaker-attributed turns. A segment is one atomic
  contiguous same-speaker turn; unlabeled continuation cues do not split it.
  Speaker tags: `K`, `Q`, named interlocutors, `ANN`, `UNK`. Both `segments`
  and `passages` record an `attribution` provenance (`label`, `inherit`,
  `assumed_k`, `q_boundary_heuristic`).
- **`passages`** — K monologues sub-chunked at sentence boundaries (150-word
  target, 260-word hard max, short tails <60 words merged); non-K turns stay
  one passage. **This is the citation unit** (each carries its own
  `t_start`/`t_end`).
- **`speaker_labels`** — per-transcript registry of raw label forms → canonical
  speaker codes (unique on `(transcript_id, raw_label)`).
- **`transcript_qa`** — per-ingest validation status and collapse diagnostics.
- **`passages_fts`** — FTS5 over K-only passage text.
- **`corpus_meta`** — parser version, source catalog path, and creation time.

`parse_vtt.py` is idempotent per `(item, kind, language)` (re-ingest deletes prior
rows first). It attaches `catalog/krishnamurti.db` read-only for item and subtitle
metadata, while all generated writes go to the corpus DB. Its per-item registry
admits known labels at cue start or mid-cue; unknown labels must recur at cue
start and be short initials, preventing prose-colon false speakers. Run batch
ingestion with `--event-type T [--limit N]` or one file with
`--vtt … --item …`. Use `corpus_stats.py` for per-item, per-event-type, and
per-tier coverage/FTS statistics, validation failures, and collapsed-item
reporting (`--csv PATH` also writes adjacent `-events` and `-tiers` rollups).

Ingestion guards: `parse_vtt.py` refuses a 0-cue parse in *both* batch and
standalone modes (`ingest()` itself raises — protects existing transcripts from
header-only/evicted files), marks word-interpolated split timestamps synthetic,
records event-aware assumed-K provenance, and stores per-item QA warnings.

### Corpus relevance tiers

Each catalog item gets an explicit `items.corpus_tier`: **A** (core teachings),
**B** (secondary, e.g. conversations/interviews), **C** (archival films),
**X** (the 12 `EBM` excerpts, duplicates of parent talks). The derived
`items.corpus_include` is 0 only for X. Batch ingestion gates on
`corpus_include = 1` (so A/B/C are ingested), but only tier A/B K-passages
enter `passages_fts`. Tier assignment is centralized in
`segment_schema.corpus_tier_for_event_type()` (populated on rebuild via
`ensure_corpus_tiers()`); unknown event types default to B with a warning —
don't hard-code tier decisions elsewhere. For DBs predating explicit tiers,
`scripts/migrate_corpus_tiers.py` is the one-time migration (adds/populates the
tier columns, syncs `transcripts.corpus_tier`, removes tier-C rows from FTS);
normal rebuilds and new ingests apply tiers automatically.

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
and `redownload_audio.py` (replaces sub-bitrate/corrupt audio).
`download_subtitles.py` fetches the manual (not auto-generated) English YouTube
subtitles into `item_subtitles`. YouTube auth uses
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

`import_kft_web_transcript.py` imports an official untimed KFT web transcript
for items whose media can't be downloaded. It deliberately writes **plain text,
not synthetic VTT** — estimated timestamps would create false citations in the
L2 passage pipeline; keep it that way.

## Concept registry & the Obsidian vault — L3/L4

The concept layer is **tracked, hand-curated data**, not generated output:

- **`concepts/concepts.jsonl`** — one JSON object per line, keyed by `slug` (not
  `id`). 36 `active` roots + 3 `deprecated` tombstones (`sacred`, `self`,
  `word-naming`), each with definition, include/exclude criteria, aliases (with
  period notes for K's shifting vocabulary), and typed relations. Tombstones stay
  so predictions keyed to their ids remain resolvable; consumers filter by
  `status`. **The registry is closed at 36** — see STRATEGY.md before proposing a
  change.
- **Facet membership lives in code**, in `FACETS` inside
  `scripts/build_concept_vault.py` (4 facets of 8/9/11/8), not in the JSONL.
- **`concepts/citations.jsonl`** — the L4 counterpart: the curated passages that
  make a concept note say something, one line per citation, grouped into
  `theme`s that are rendered in file order (the sequence *is* the argument).
  Citations are keyed on **`(item_code, t_start)`**, never on `passages.id` —
  passage ids are reassigned on every re-ingest, so an id-keyed citation would
  drift silently onto different words. Each line also stores the resolved quote
  and `youtu.be` link, so the vault rebuilds from a fresh clone without the
  gitignored corpus DB. Pick candidates with `retrieve_concept.py`, then run
  `build_citations.py --sync` (see below).
- The **I Ching navigation layer** is **archived** in `archive/iching/` (parked
  2026-07-25, undecided). Don't reintroduce it into `scripts/`, `concepts/`, or
  the generated vault without reading `archive/iching/README.md` first — a test
  (`test_iching_layer_stays_archived`) fails if it leaks back into the notes.
- **`scripts/import_concepts.py`** is the only supported path from the JSONL into
  the corpus DB's `concepts`/alias/relation tables. Never hand-edit those tables;
  re-run the importer after touching the JSONL.

**Obsidian vault ownership** — two generators, disjoint subtrees:

| Path | Owner |
|---|---|
| `obsidian/*.md` (index + mega-group notes) | `build_catalog.py` |
| `obsidian/roots/**` (37 notes: 36 concepts + Map) | `build_concept_vault.py` |

`build_catalog.py` clears the vault on every rebuild but **reserves `roots/`**
(`reserved = {"roots"}` in `build_obsidian_series`). The generated set is exactly
the 36 concept notes plus `Map of the 36 Roots.md`; `obsidian/roots/reference/`
**and `Roots of Knowledge.md`** (the hub) are hand-authored, and everything else
under `roots/` is generated.

```bash
python3 scripts/build_concept_vault.py           # regenerate the 37 root notes
python3 scripts/build_concept_vault.py --check    # CI-style gate: fails on stale
                                                  # notes AND on dead wikilinks
python3 scripts/import_concepts.py                # JSONL → corpus DB
python3 scripts/retrieve_concept.py fear --format md   # BM25 candidates to judge
python3 scripts/build_citations.py --sync         # resolve curated citations
python3 scripts/build_citations.py --verify       # gate: citations still resolve
python3 scripts/strategy_stats.py                 # refresh STRATEGY.md live numbers
```

`--check` resolves every `[[wikilink]]` in the whole `obsidian/` tree by
basename (the vault root is `obsidian/`, not `obsidian/roots/`), tolerating the
`[[Note.md]]` form. Run it after editing any vault note or the registry.

**Adding a citation** is one hand-written line (`slug`, `theme`, `seq`,
`item_code`, `t_start`) plus `build_citations.py --sync`, then regenerate the
vault. `--sync` refuses a passage that isn't K's, has no video link, or carries
synthetic (word-interpolated) timestamps — a citation asserts the offset is a
real cue boundary in the published recording. Run `--verify` after any
re-ingest: it fails if a cited passage moved or its quoted text changed.

## Code conventions

- **Style**: Python 3.10+, `from __future__ import annotations`, `pathlib.Path`,
  union types. No formatter or linter config — match surrounding code.
- **Script anatomy**: standalone `argparse` CLI + `main()` +
  `if __name__ == "__main__"`. Most support `--help`, `--dry-run`, `--limit N`.
  Exceptions: `build_catalog.py` and `add_*.py` take no args.
- **Paths**: every script derives `ROOT = Path(__file__).resolve().parents[1]`.
  Media-root override: `KRISHNAMURTI_MEDIA_ROOT` env or `--library-root`; reuse
  `media_root()` / `resolve_media_path()` from `scripts/download_series.py`.
- **Cross-module reuse**: shared download/auth helpers live in
  `download_series.py`; siblings use `sys.path.insert(0, scripts_dir)` + lazy
  imports.
- **Idempotency**: DB writes use `INSERT ... ON CONFLICT DO UPDATE`;
  `parse_vtt.py` is idempotent per `(item, kind, language)` via
  delete-before-reinsert. Re-add scripts are safe to re-run.
- **Error handling / logging**: `print()` to stdout, `sys.exit(1)` after failure
  counts. No logging framework.
- **Naming**: item codes = place + year + event + number (`LO61T1`,
  `GSBR74DT01`); section slugs `{number}{letter}-{kebab-title}`.
- **YouTube auth**: cookies resolved via `resolve_yt_auth()` — env vars
  (`KRISHNAMURTI_YT_COOKIES_FILE`, `KRISHNAMURTI_YT_COOKIES_BROWSER`),
  `www.youtube.com_cookies.txt`, `catalog/.yt-browser-cookies.txt`, or
  `--cookies-from-browser chrome` (preferred for video; stale Netscape files
  403). Cookie files are gitignored — keep them out of git.
- **Git hygiene**: `library/`, `compare/`, `corpus/*.db`, `catalog/logs/`, all
  `*cookies*.txt`, and venvs are gitignored. Never commit media or cookies.

## Files worth knowing

- `scripts/build_catalog.py` — largest module; PDF parse, DB save, exports,
  Obsidian generation, phase-2 snapshot/restore.
- `scripts/parse_vtt.py` — corpus ingest (`Cue`/`Segment` dataclasses, speaker
  registry, passage chunking).
- `scripts/download_series.py` — hub for media paths and yt-dlp auth; the other
  download scripts delegate to it.
- `scripts/*_schema.py` — the only place table DDL may change.
- `scripts/transcribe_whisper.py` — interim STT; settings are pilot-frozen.
- `scripts/build_concept_vault.py` — L3/L4 concept vault generator.
- `scripts/retrieve_concept.py` — BM25 candidate retrieval for one root; the
  retrieval-first alternative to exhaustive passage classification.
- `scripts/build_citations.py` — resolves `concepts/citations.jsonl` against the
  corpus; `--verify` is the gate that a published quote still says what it said.
- `scripts/strategy_stats.py` — regenerates STRATEGY.md's "Where things stand"
  block from the DBs; `--check` is the gate that its numbers are not stale.
- `CLAUDE.md` (operational contract) and `STRATEGY.md` (plan, state, open
  questions, decision log) — the only two docs. Don't add a third. In STRATEGY.md
  everything is referenced by slug (`Q-scribe-needed`, `P-notes`), never by
  position, and `tests/test_strategy_doc.py` fails on a dangling one.

## Testing & QA

```bash
.venv/bin/python -m unittest discover tests      # stdlib unittest; no linter, no CI
python3 scripts/build_concept_vault.py --check   # vault staleness + dead links
python3 scripts/build_citations.py --verify      # cited passages still resolve
python3 scripts/strategy_stats.py --check        # STRATEGY.md numbers vs the DBs
python3 scripts/segment_schema.py corpus/krishnamurti-corpus.db catalog/krishnamurti.db
python3 scripts/corpus_stats.py [--csv catalog/exports/corpus-stats.csv]
```

Most CLIs offer `--dry-run` and `--limit N` — use them to smoke-test before full
runs, and inspect effects with `corpus_stats.py`, `sqlite3`, and
`catalog/exports/*.csv`.

Transcription QA lives in `compare/` (below).

## STT evaluation (`compare/`)

How the production STT engine was chosen (verdict: **ElevenLabs Scribe v2 +
keyterm prompting**, recorded in STRATEGY.md). `run_stt.sh elevenlabs|xai <audio>
<label> [keyterms.json]` calls a provider (one multipart `keyterms` field *per
term*); `compare/build_keyterms.py` mines the keyterm lexicon from the manual-sub
corpus using `wordfreq` zipf rarity; `compare_texts.py` / `compare_piece.py` score
WER/CER with `jiwer` against manual VTTs (the reference). When evaluating, exclude
a test item's own subs from the keyterm lexicon to avoid leakage.
