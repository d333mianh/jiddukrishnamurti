# Generated corpus storage

`krishnamurti-corpus.db` is the generated L1/L2 teachings corpus: transcript
provenance, speaker segments, citable passages, parser QA, and K-only FTS data.
The live database and its SQLite sidecar files are gitignored — 195 MB of
generated data that changes on every ingest. Recreate or update it with
`scripts/parse_vtt.py`; the tracked catalog remains in `catalog/krishnamurti.db`.

## The tracked snapshot

`krishnamurti-corpus.db.zst` **is** tracked (61 MB, holding 988 transcripts and
154,916 passages as of 2026-08-03), against the usual rule that generated
artifacts stay out of git. Two reasons:

1. Without it a fresh clone cannot run the citation loop at all:
   `retrieve_concept.py` and `build_citations.py` both need the corpus, so the
   loop that produces concept notes is dead on a machine that has only the repo.
2. It is expensive to rebuild — re-ingesting every manual VTT is a long run, and
   it needs the gitignored `library/` tree, which a clone does not have.

It is no longer *irreplaceable*, which it was until 2026-07-26. This file used to
say that 111 manual VTTs were absent from disk and all 111 had been ingested, so
the corpus DB was the only surviving copy of their text. That was wrong twice
over: only 29 of the 111 had ever been ingested (the rest had no copy anywhere),
and all 111 have since been re-downloaded and re-ingested. `backup_corpus.py`
now reports `corpus-only items: 0`. See the 2026-07-26 entries in STRATEGY.md.

The repo is private, which is what makes shipping verbatim transcript text here
acceptable — see the STRATEGY.md decision log.

### Restore, on a fresh clone

```bash
zstd -d corpus/krishnamurti-corpus.db.zst -o corpus/krishnamurti-corpus.db
shasum -a 256 -c corpus/krishnamurti-corpus.db.zst.sha256   # optional, from repo root
python3 scripts/build_citations.py --verify                  # 83/83 = you are up
```

### Refresh, after ingesting

Deliberately, on milestones — **not** after every run. Each refresh adds ~61 MB
to git history permanently.

Compress from the backup-API copy, never from the live file: that copy is both
consistent under a concurrent write *and* free of the live DB's unused pages.
The 2026-08-03 refresh came out at 61 MB against the previous 67 MB while
carrying 13% more text, which is the freed pages showing up.

```bash
python3 - <<'PY'
import sqlite3, pathlib, tempfile
src = pathlib.Path("corpus/krishnamurti-corpus.db")
tmp = pathlib.Path(tempfile.mkdtemp()) / "snap.db"
s = sqlite3.connect(f"file:{src}?mode=ro", uri=True); d = sqlite3.connect(tmp)
s.backup(d); d.close(); s.close(); print(tmp)
PY
# then, with the path it printed:
zstd -19 -T0 -f -o corpus/krishnamurti-corpus.db.zst <that path>
shasum -a 256 corpus/krishnamurti-corpus.db.zst > corpus/krishnamurti-corpus.db.zst.sha256
```

The sqlite3 backup API is used rather than `cp` so the snapshot is consistent
even if something is mid-write. `scripts/backup_corpus.py` remains the fuller
local backup — it also bundles the manual VTTs, which are *not* in this
snapshot.
