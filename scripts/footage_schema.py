"""SQLite schema for PDF audio vs filmed video footage."""

from __future__ import annotations

import sqlite3

FOOTAGE_AUDIO_ONLY = "audio_only"
FOOTAGE_VIDEO = "video_footage"


def footage_type_from_media_type(media_type: str | None) -> str | None:
    if media_type == "audio":
        return FOOTAGE_AUDIO_ONLY
    if media_type == "video":
        return FOOTAGE_VIDEO
    return None


def ensure_footage_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    if "footage_type" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN footage_type TEXT")
    conn.execute(
        """
        UPDATE items SET footage_type = ?
        WHERE media_type = 'audio' AND (footage_type IS NULL OR footage_type = '')
        """,
        (FOOTAGE_AUDIO_ONLY,),
    )
    conn.execute(
        """
        UPDATE items SET footage_type = ?
        WHERE media_type = 'video' AND (footage_type IS NULL OR footage_type = '')
        """,
        (FOOTAGE_VIDEO,),
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_items_footage_type ON items(footage_type)
        """
    )
    conn.commit()