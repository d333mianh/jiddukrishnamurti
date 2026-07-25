# Jiddu Krishnamurti Recordings Library

Structured catalog of KFT full-length recordings, built from the **Krishnamurti Foundation Trust – Full Length Directory 2026** PDF.

## Contents

- `catalog/krishnamurti.db` — SQLite catalog (canonical)
  - `items` — one row per recording (full detail)
  - `series` — one row per series (`minutes_total`, PDF order)
  - `item_links` / `item_subtitles` / `item_media` — link discovery and
    download state; preserved across rebuilds (`scripts/backfill_media.py`
    re-syncs `item_media` from disk)
- `catalog/exports/` — CSV and Excel exports
- `corpus/krishnamurti-corpus.db` — generated, gitignored transcripts/segments/
  passages + FTS (see `STRATEGY.md`)
- `concepts/` — the tracked L3 registry: 36 concept "roots"
- `obsidian/` — compact series-grouped vault, plus `obsidian/roots/` — the
  generated concept vault (`scripts/build_concept_vault.py`)
- `scripts/build_catalog.py` — Rebuild catalog from PDF
- `archive/` — parked work kept out of the live pipeline (see each
  subdirectory's `README.md`)

Docs: **`STRATEGY.md`** (roadmap, live state, open questions, decision log) ·
**`CLAUDE.md`** (how to work in this repo) · **`L3-SCHEMA.md`** (concept-layer
DDL).

## Rebuild

```bash
pip install -r requirements.txt
python3 scripts/build_catalog.py
```

Requires `pdftotext` (poppler).

## Link discovery (no downloads)

Scrape official KFT YouTube URLs from PDF hyperlinks and optional Archive.org alternates:

```bash
apt install python3-pypdf   # if needed
python3 scripts/discover_links.py
python3 scripts/discover_links.py --archive --archive-limit 100
```

Outputs: `catalog/exports/links-comparison.csv`, `catalog/link_cache.json`, `item_links` in SQLite.

## License

Catalog metadata © Krishnamurti Foundation Trust. This repo is a personal indexing tool; recordings remain property of KFT / rights holders.