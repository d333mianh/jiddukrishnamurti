# Generated corpus storage

`krishnamurti-corpus.db` is the generated L1/L2 teachings corpus: transcript
provenance, speaker segments, citable passages, parser QA, and K-only FTS data.
The database and its SQLite sidecar files are gitignored because they contain
regenerable full transcript text. Recreate or update it with
`scripts/parse_vtt.py`; the tracked catalog remains in `catalog/krishnamurti.db`.
