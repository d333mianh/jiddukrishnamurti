"""SQLite schema for the generated L1/L2 teachings corpus.

The corpus lives in ``corpus/krishnamurti-corpus.db``, separate from the
catalog and pipeline-state database. Corpus rows use the stable catalog item
code rather than ``items.id``: SQLite foreign keys cannot cross an attached
database, and catalog row ids may change on rebuild.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PARSER_VERSION = "l2-parser-v2"

SEGMENT_DDL = """
CREATE TABLE IF NOT EXISTS corpus_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL
);

-- L1: one row per ingested transcript file (provenance).
CREATE TABLE IF NOT EXISTS transcripts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code      TEXT    NOT NULL,
    event_type     TEXT,
    kind           TEXT    NOT NULL,
    language       TEXT    NOT NULL,
    source_path    TEXT    NOT NULL,
    resolved_via   TEXT    NOT NULL,
    cue_count      INTEGER,
    segment_count  INTEGER,
    passage_count  INTEGER,
    word_count     INTEGER,
    duration_secs  REAL,
    parser_version TEXT    NOT NULL,
    assumed_k      INTEGER NOT NULL DEFAULT 0,
    parsed_at      TEXT    NOT NULL,
    UNIQUE(item_code, kind, language)
);
CREATE INDEX IF NOT EXISTS idx_transcripts_item ON transcripts(item_code);
CREATE INDEX IF NOT EXISTS idx_transcripts_kind ON transcripts(kind);

-- L2a: per-transcript speaker-label registry.
CREATE TABLE IF NOT EXISTS speaker_labels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    raw_label     TEXT    NOT NULL,
    speaker_code  TEXT    NOT NULL,
    display_name  TEXT,
    cue_hits      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(transcript_id, raw_label)
);
CREATE INDEX IF NOT EXISTS idx_speaker_labels_transcript ON speaker_labels(transcript_id);

-- L2b: atomic speaker turns (one contiguous same-speaker run of cues).
CREATE TABLE IF NOT EXISTS segments (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id        INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    item_code            TEXT    NOT NULL,
    seq                  INTEGER NOT NULL,
    speaker_code         TEXT    NOT NULL,
    raw_label            TEXT,
    t_start              REAL    NOT NULL,
    t_end                REAL    NOT NULL,
    timestamps_synthetic INTEGER NOT NULL DEFAULT 0,
    text                 TEXT    NOT NULL,
    word_count           INTEGER NOT NULL,
    answers_seq          INTEGER,
    UNIQUE(transcript_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_segments_item ON segments(item_code);
CREATE INDEX IF NOT EXISTS idx_segments_transcript ON segments(transcript_id);
CREATE INDEX IF NOT EXISTS idx_segments_speaker ON segments(speaker_code);

-- L2c: K monologues are sub-chunked; non-K turns remain one passage each.
CREATE TABLE IF NOT EXISTS passages (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id        INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    segment_id           INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    item_code            TEXT    NOT NULL,
    seq                  INTEGER NOT NULL,
    speaker_code         TEXT    NOT NULL,
    t_start              REAL    NOT NULL,
    t_end                REAL    NOT NULL,
    timestamps_synthetic INTEGER NOT NULL DEFAULT 0,
    text                 TEXT    NOT NULL,
    word_count           INTEGER NOT NULL,
    UNIQUE(transcript_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_passages_item ON passages(item_code);
CREATE INDEX IF NOT EXISTS idx_passages_segment ON passages(segment_id);
CREATE INDEX IF NOT EXISTS idx_passages_speaker ON passages(speaker_code);

CREATE TABLE IF NOT EXISTS transcript_qa (
    transcript_id    INTEGER PRIMARY KEY REFERENCES transcripts(id) ON DELETE CASCADE,
    item_code        TEXT    NOT NULL,
    status           TEXT    NOT NULL CHECK(status IN ('pass', 'warn')),
    validation_rule  TEXT    NOT NULL,
    failure_codes    TEXT,
    detail           TEXT,
    speaker_count    INTEGER NOT NULL,
    k_passage_count  INTEGER NOT NULL,
    k_word_count     INTEGER NOT NULL,
    checked_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcript_qa_status ON transcript_qa(status);
CREATE INDEX IF NOT EXISTS idx_transcript_qa_item ON transcript_qa(item_code);

-- Plain FTS5 (not external-content) keeps K-only population and re-ingest simple.
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def ensure_corpus_include(conn: sqlite3.Connection) -> None:
    """Add the catalog-side corpus scope flag when building the catalog."""
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "items" not in tables:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    if "corpus_include" not in cols:
        conn.execute(
            "ALTER TABLE items ADD COLUMN corpus_include INTEGER NOT NULL DEFAULT 1"
        )
        conn.execute("UPDATE items SET corpus_include = 0 WHERE event_type = 'EBM'")


def ensure_corpus_schema(
    conn: sqlite3.Connection, catalog_db_path: Path | str | None = None
) -> None:
    """Ensure corpus tables and record database-level provenance."""
    conn.executescript(SEGMENT_DDL)
    now = utc_now()
    conn.execute(
        "INSERT OR IGNORE INTO corpus_meta(key,value) VALUES('created_at',?)", (now,)
    )
    conn.execute(
        "INSERT INTO corpus_meta(key,value) VALUES('parser_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (PARSER_VERSION,),
    )
    if catalog_db_path is not None:
        source = str(Path(catalog_db_path).expanduser().resolve())
        conn.execute(
            "INSERT INTO corpus_meta(key,value) VALUES('source_catalog_db',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (source,),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    import sys

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("corpus/krishnamurti-corpus.db")
    catalog = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("catalog/krishnamurti.db")
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_corpus_schema(conn, catalog)
    conn.commit()
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
        )
    ]
    print(f"corpus schema ensured on {db}")
    print("corpus tables present:", [t for t in tables if t in {
        "corpus_meta", "transcripts", "speaker_labels", "segments", "passages",
        "passages_fts", "transcript_qa",
    }])
