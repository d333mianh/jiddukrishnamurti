#!/usr/bin/env python3
"""Backfill item_media from files already in the library.

Scans expected audio (.m4a, all linked items) and video (.mp4, linked
video_footage items) paths under the media root and records
downloaded/missing per item. Safe to re-run: it reflects current disk
state, healing rows that drifted (e.g. files moved or deleted).
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"

from download_series import media_root, output_path  # noqa: E402
from footage_schema import FOOTAGE_VIDEO, ensure_footage_schema  # noqa: E402
from media_schema import (  # noqa: E402
    MEDIA_AUDIO,
    MEDIA_VIDEO,
    ensure_media_schema,
    file_mtime_utc,
    upsert_media_row,
    utc_now,
)


def linked_items(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        """
        SELECT i.id, i.code, i.future_path, i.series_code, i.footage_type
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source IN ('kft_pdf_youtube', 'kft_channel_scan') AND l.link_kind = 'primary'
        ORDER BY i.pdf_order
        """
    ).fetchall()


def scan_one(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    media: str,
    media_mode: str,
    future_path: str,
    series_code: str,
    root: Path,
    dry_run: bool,
) -> str:
    dest = output_path(future_path, media_mode, root=root, series_code=series_code)
    try:
        rel = str(dest.relative_to(root))
    except ValueError:
        rel = str(dest)
    if dest.is_file():
        status = "downloaded"
        if not dry_run:
            upsert_media_row(
                conn,
                item_id=item_id,
                media=media,
                fmt=dest.suffix.lstrip("."),
                future_path=rel,
                status=status,
                file_size=dest.stat().st_size,
                downloaded_at=file_mtime_utc(dest),
                verified_at=utc_now(),
            )
    else:
        status = "missing"
        if not dry_run:
            upsert_media_row(
                conn,
                item_id=item_id,
                media=media,
                fmt=dest.suffix.lstrip("."),
                future_path=rel,
                status=status,
                file_size=None,
                verified_at=utc_now(),
            )
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill item_media from disk")
    parser.add_argument("--library-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = media_root(args.library_root)
    if not root.is_dir():
        raise SystemExit(f"Media root not found: {root}")

    conn = sqlite3.connect(DB_PATH)
    ensure_footage_schema(conn)
    ensure_media_schema(conn)

    counts = {
        (MEDIA_AUDIO, "downloaded"): 0,
        (MEDIA_AUDIO, "missing"): 0,
        (MEDIA_VIDEO, "downloaded"): 0,
        (MEDIA_VIDEO, "missing"): 0,
    }
    rows = linked_items(conn)
    for item_id, _code, future_path, series_code, footage_type in rows:
        status = scan_one(
            conn,
            item_id=item_id,
            media=MEDIA_AUDIO,
            media_mode="best",
            future_path=future_path,
            series_code=series_code or "",
            root=root,
            dry_run=args.dry_run,
        )
        counts[(MEDIA_AUDIO, status)] += 1
        if footage_type == FOOTAGE_VIDEO:
            status = scan_one(
                conn,
                item_id=item_id,
                media=MEDIA_VIDEO,
                media_mode="video",
                future_path=future_path,
                series_code=series_code or "",
                root=root,
                dry_run=args.dry_run,
            )
            counts[(MEDIA_VIDEO, status)] += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    tag = "Would record" if args.dry_run else "Recorded"
    print(f"{tag} for {len(rows)} linked items under {root}:")
    print(
        f"  audio: {counts[(MEDIA_AUDIO, 'downloaded')]} downloaded, "
        f"{counts[(MEDIA_AUDIO, 'missing')]} missing"
    )
    print(
        f"  video: {counts[(MEDIA_VIDEO, 'downloaded')]} downloaded, "
        f"{counts[(MEDIA_VIDEO, 'missing')]} missing"
    )


if __name__ == "__main__":
    main()
