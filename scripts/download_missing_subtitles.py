#!/usr/bin/env python3
"""Download manual English subtitles for video_footage items missing .en.vtt on disk."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"

from download_series import media_root, output_path, resolve_yt_auth  # noqa: E402
from download_subtitles import (  # noqa: E402
    MANUAL_EN_PRIORITY,
    process_item_subtitle,
    subtitle_output_path,
)
from footage_schema import FOOTAGE_VIDEO, ensure_footage_schema  # noqa: E402
from subtitle_schema import ensure_subtitle_schema  # noqa: E402


def section_path_pattern(section_prefix: str | None) -> str:
    if not section_prefix:
        return "library/%"
    if len(section_prefix) == 1 and section_prefix.isdigit():
        return f"library/{section_prefix}%"
    return f"library/{section_prefix}-%"


def has_manual_subtitle(
    future_path: str,
    series_code: str | None,
    *,
    root: Path,
    code: str,
) -> bool:
    fp_audio = future_path.replace(".mp4", ".m4a")
    for lang in MANUAL_EN_PRIORITY:
        dest = subtitle_output_path(
            fp_audio, lang, root=root, series_code=series_code or ""
        )
        if dest.is_file() and dest.stat().st_size > 50:
            return True
    video_dest = output_path(
        future_path, "video", root=root, series_code=series_code or ""
    )
    if video_dest.parent.is_dir():
        for path in video_dest.parent.glob("*.en*.vtt"):
            if code in path.name and path.stat().st_size > 50:
                return True
    return False


def missing_items(
    conn: sqlite3.Connection, section_prefix: str | None, *, root: Path
) -> list[tuple[int, str, str, str | None, str, str]]:
    pattern = section_path_pattern(section_prefix)
    rows = conn.execute(
        """
        SELECT i.id, i.code, i.title, i.series_code, i.future_path, l.url
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source IN ('kft_pdf_youtube', 'kft_channel_scan') AND l.link_kind = 'primary'
        WHERE i.footage_type = ? AND i.future_path LIKE ?
        ORDER BY i.pdf_order
        """,
        (FOOTAGE_VIDEO, pattern),
    ).fetchall()
    missing: list[tuple[int, str, str, str | None, str, str]] = []
    for row in rows:
        item_id, code, title, series_code, future_path, url = row
        if not has_manual_subtitle(
            future_path, series_code, root=root, code=code
        ):
            missing.append(row)
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download missing manual English subtitles for video_footage items"
    )
    parser.add_argument(
        "section",
        nargs="?",
        default=None,
        help="Section prefix (e.g. 1A, or 1 for all section-1 folders)",
    )
    parser.add_argument("--library-root", type=Path, default=None)
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        default="chrome",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=2.0,
        help="Seconds between items (default: 2)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    browser = (
        args.cookies_from_browser
        or os.environ.get("KRISHNAMURTI_YT_COOKIES_BROWSER")
        or "chrome"
    )
    cookies_file, cookies_browser = resolve_yt_auth(
        cookies_file_arg=None,
        browser=browser,
        prefer_live=False,
    )

    root = media_root(args.library_root)
    conn = sqlite3.connect(DB_PATH)
    ensure_footage_schema(conn)
    ensure_subtitle_schema(conn)
    items = missing_items(conn, args.section, root=root)
    if not items:
        scope = args.section or "all"
        print(f"No missing manual subtitles for section {scope!r}")
        return

    print(
        f"Missing subtitles: {len(items)} item(s)"
        + (f" in {args.section}" if args.section else "")
    )
    if args.dry_run:
        for _item_id, code, _title, *_rest in items:
            print(f"  {code}")
        return

    stats = {"downloaded": 0, "skipped": 0, "missing": 0, "failed": 0}
    for i, (item_id, code, title, series_code, future_path, url) in enumerate(
        items, 1
    ):
        print(f"\n[{i}/{len(items)}] {code}: {title[:55]}")
        result = process_item_subtitle(
            conn,
            item_id=item_id,
            future_path=future_path,
            series_code=series_code,
            url=url,
            root=root,
            cookies_file=cookies_file,
            cookies_browser=cookies_browser,
            dry_run=False,
        )
        if result == "downloaded":
            print("  subs OK")
        elif result == "skipped":
            print("  subs SKIP (already on disk)")
        elif result == "missing":
            print("  subs: no manual English")
        else:
            print("  subs FAILED")
        stats[result if result in stats else "failed"] += 1
        time.sleep(args.sleep)

    print(
        f"\nDone: {stats['downloaded']} downloaded, {stats['skipped']} skipped, "
        f"{stats['missing']} no manual EN, {stats['failed']} failed"
    )
    if stats["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()