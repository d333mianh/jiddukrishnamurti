# Jiddu Krishnamurti Recordings Library

Structured catalog of KFT full-length recordings, built from the **Krishnamurti Foundation Trust – Full Length Directory 2026** PDF.

## Contents

- `catalog/krishnamurti.db` — SQLite catalog (canonical)
- `catalog/exports/` — CSV and Excel exports
- `obsidian/` — Compact series-grouped vault (9 notes)
- `scripts/build_catalog.py` — Rebuild catalog from PDF

## Rebuild

```bash
pip install -r requirements.txt
python3 scripts/build_catalog.py
```

Requires `pdftotext` (poppler).

## License

Catalog metadata © Krishnamurti Foundation Trust. This repo is a personal indexing tool; recordings remain property of KFT / rights holders.