"""SQLite schema for the L1/L2 teachings-corpus layer (transcripts → segments → passages).

Built on top of the catalog (items) and download-state (item_subtitles) tables.
One row per ingested transcript file (L1), one per speaker turn (L2 segments),
and K monologues sub-chunked into ~150-200-word passages (the citation unit).
A K-only FTS5 index sits over passages for full-text search of Krishnamurti's words.

Deliberately NOT registered in build_catalog.py PHASE2_TABLES: that snapshot/restore
re-keys rows by items.code with fresh autoincrement ids, which would corrupt the
transcript_id/segment_id cross-references here. Instead these tables are rebuilt by
parse_vtt.py, which is idempotent per (item, kind) and safe to re-run after any
catalog rebuild. ensure_segment_schema() is called from build_catalog.init_db so a
fresh DB always has an empty-but-valid corpus schema.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

PARSER_VERSION = "l2-parser-v1"

SEGMENT_DDL = """
-- L1: one row per ingested transcript file (provenance).
CREATE TABLE IF NOT EXISTS transcripts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id        INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    kind           TEXT    NOT NULL,            -- mirrors item_subtitles.kind: 'manual' | 'whisper-large-v3-turbo' | future 'scribe-v2'
    language       TEXT    NOT NULL,            -- 'en' OR 'en-GB' (do NOT filter to 'en' only)
    source_path    TEXT    NOT NULL,            -- resolved on-disk path actually parsed (relative to media root)
    resolved_via   TEXT    NOT NULL,            -- 'direct' | 'combined-multipart' | 'override'
    cue_count      INTEGER,
    segment_count  INTEGER,
    passage_count  INTEGER,
    word_count     INTEGER,
    duration_secs  REAL,
    parser_version TEXT    NOT NULL,
    parsed_at      TEXT    NOT NULL,
    UNIQUE(item_id, kind, language)
);
CREATE INDEX IF NOT EXISTS idx_transcripts_item ON transcripts(item_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_kind ON transcripts(kind);

-- L2a: per-item speaker-label registry, learned by scanning the file's actual labels.
CREATE TABLE IF NOT EXISTS speaker_labels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    raw_label     TEXT    NOT NULL,             -- as seen, sans trailing ': '  e.g. 'K','Krishnamurti','DB','David Bohm','Q'
    speaker_code  TEXT    NOT NULL,             -- canonical: 'K' | 'Q' | 'DB' | 'AWA' | 'ANN' | 'UNK' | ...
    display_name  TEXT,                         -- 'Krishnamurti' | 'David Bohm' | 'Questioner'
    cue_hits      INTEGER NOT NULL DEFAULT 0,   -- how many cues opened with this raw label
    UNIQUE(transcript_id, raw_label)
);
CREATE INDEX IF NOT EXISTS idx_speaker_labels_transcript ON speaker_labels(transcript_id);

-- L2b: atomic speaker turns (one contiguous same-speaker run of cues).
CREATE TABLE IF NOT EXISTS segments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    item_id       INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,  -- denormalized for stats joins
    seq           INTEGER NOT NULL,             -- 0-based turn order within the transcript
    speaker_code  TEXT    NOT NULL,
    raw_label     TEXT,                         -- label that opened the turn; NULL if inherited
    t_start       REAL    NOT NULL,             -- seconds, from first cue of the turn
    t_end         REAL    NOT NULL,             -- seconds, from last cue of the turn
    text          TEXT    NOT NULL,             -- cues joined, label stripped
    word_count    INTEGER NOT NULL,
    answers_seq   INTEGER,                      -- for a K turn answering a Q: that Q turn's seq (else NULL)
    UNIQUE(transcript_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_segments_item ON segments(item_id);
CREATE INDEX IF NOT EXISTS idx_segments_transcript ON segments(transcript_id);
CREATE INDEX IF NOT EXISTS idx_segments_speaker ON segments(speaker_code);

-- L2c: passages — K monologues sub-chunked to ~150-200 words at sentence boundaries;
-- non-K turns are one passage each. This is the unit L3 tags and L4 cites.
CREATE TABLE IF NOT EXISTS passages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    segment_id    INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    item_id       INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,             -- 0-based passage order within the transcript
    speaker_code  TEXT    NOT NULL,
    t_start       REAL    NOT NULL,
    t_end         REAL    NOT NULL,
    text          TEXT    NOT NULL,
    word_count    INTEGER NOT NULL,
    UNIQUE(transcript_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_passages_item ON passages(item_id);
CREATE INDEX IF NOT EXISTS idx_passages_segment ON passages(segment_id);
CREATE INDEX IF NOT EXISTS idx_passages_speaker ON passages(speaker_code);

-- L2d: full-text index over K-only passage text. Plain FTS5 (not external-content) so
-- K-only population and per-item re-ingest deletes stay simple. rowid == passages.id.
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def ensure_segment_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SEGMENT_DDL)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    # Smoke test: ensure the schema against whatever DB path is passed (default: a temp copy is safer).
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else "catalog/krishnamurti.db"
    conn = sqlite3.connect(db)
    ensure_segment_schema(conn)
    conn.commit()
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table') OR sql LIKE '%VIRTUAL%' ORDER BY name"
        )
    ]
    print(f"schema ensured on {db}")
    print("corpus tables present:", [t for t in tables if t in
          ("transcripts", "speaker_labels", "segments", "passages", "passages_fts")])
