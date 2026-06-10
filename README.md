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
- `obsidian/` — Compact series-grouped vault (9 notes)
- `scripts/build_catalog.py` — Rebuild catalog from PDF

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