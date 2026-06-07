"""SQLite schema for manual YouTube subtitles."""

from __future__ import annotations

import sqlite3

ITEM_SUBTITLES_DDL = """
CREATE TABLE IF NOT EXISTS item_subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'manual',
    format TEXT NOT NULL DEFAULT 'vtt',
    future_path TEXT NOT NULL,
    file_size INTEGER,
    status TEXT NOT NULL,
    error_message TEXT,
    probed_at TEXT,
    downloaded_at TEXT,
    UNIQUE(item_id, language, kind)
);
CREATE INDEX IF NOT EXISTS idx_item_subtitles_item ON item_subtitles(item_id);
CREATE INDEX IF NOT EXISTS idx_item_subtitles_status ON item_subtitles(status);
"""


def ensure_subtitle_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(ITEM_SUBTITLES_DDL)