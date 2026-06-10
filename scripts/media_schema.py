"""SQLite schema for downloaded media files (audio/video)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ITEM_MEDIA_DDL = """
CREATE TABLE IF NOT EXISTS item_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    media TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT '',
    future_path TEXT NOT NULL,
    file_size INTEGER,
    status TEXT NOT NULL,
    error_message TEXT,
    downloaded_at TEXT,
    verified_at TEXT,
    UNIQUE(item_id, media)
);
CREATE INDEX IF NOT EXISTS idx_item_media_item ON item_media(item_id);
CREATE INDEX IF NOT EXISTS idx_item_media_status ON item_media(status);
"""

MEDIA_AUDIO = "audio"
MEDIA_VIDEO = "video"


def ensure_media_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(ITEM_MEDIA_DDL)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_mtime_utc(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def upsert_media_row(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    media: str,
    fmt: str,
    future_path: str,
    status: str,
    file_size: int | None = None,
    error_message: str | None = None,
    downloaded_at: str | None = None,
    verified_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO item_media (
            item_id, media, format, future_path, file_size, status,
            error_message, downloaded_at, verified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id, media) DO UPDATE SET
            format = excluded.format,
            future_path = excluded.future_path,
            file_size = excluded.file_size,
            status = excluded.status,
            error_message = excluded.error_message,
            downloaded_at = COALESCE(excluded.downloaded_at, item_media.downloaded_at),
            verified_at = COALESCE(excluded.verified_at, item_media.verified_at)
        """,
        (
            item_id,
            media,
            fmt,
            future_path,
            file_size,
            status,
            error_message,
            downloaded_at,
            verified_at,
        ),
    )


def record_media_result(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    media: str,
    dest: Path,
    root: Path,
    rc: int | None,
) -> None:
    """Record one download attempt: rc 0/None with file on disk = downloaded.

    rc None means the download was skipped because dest already exists.
    """
    try:
        rel = str(dest.relative_to(root))
    except ValueError:
        rel = str(dest)
    fmt = dest.suffix.lstrip(".")
    if dest.is_file():
        upsert_media_row(
            conn,
            item_id=item_id,
            media=media,
            fmt=fmt,
            future_path=rel,
            status="downloaded",
            file_size=dest.stat().st_size,
            downloaded_at=file_mtime_utc(dest),
            verified_at=utc_now(),
        )
    elif rc == 0:
        upsert_media_row(
            conn,
            item_id=item_id,
            media=media,
            fmt=fmt,
            future_path=rel,
            status="failed",
            error_message="yt-dlp exit 0 but file not on disk",
        )
    else:
        upsert_media_row(
            conn,
            item_id=item_id,
            media=media,
            fmt=fmt,
            future_path=rel,
            status="failed",
            error_message=f"yt-dlp exit {rc}",
        )
    conn.commit()
