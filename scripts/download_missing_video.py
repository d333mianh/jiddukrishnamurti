#!/usr/bin/env python3
"""Download video_footage catalog items whose .mp4 is not yet on disk."""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
DOWNLOAD_ITEM = ROOT / "scripts" / "download_item.py"

from download_series import (  # noqa: E402
    DEFAULT_VIDEO_MAX_SLEEP_INTERVAL,
    DEFAULT_VIDEO_SLEEP_INTERVAL,
    media_root,
    output_path,
)
from footage_schema import FOOTAGE_VIDEO, ensure_footage_schema  # noqa: E402


def section_path_pattern(section_prefix: str | None) -> str:
    if not section_prefix:
        return "library/%"
    if len(section_prefix) == 1 and section_prefix.isdigit():
        return f"library/{section_prefix}%"
    return f"library/{section_prefix}-%"


def missing_codes(
    conn: sqlite3.Connection, section_prefix: str | None, *, root: Path
) -> list[str]:
    pattern = section_path_pattern(section_prefix)
    rows = conn.execute(
        """
        SELECT i.code, i.future_path, i.series_code
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source = 'kft_pdf_youtube' AND l.link_kind = 'primary'
        WHERE i.footage_type = ? AND i.future_path LIKE ?
        ORDER BY i.pdf_order
        """,
        (FOOTAGE_VIDEO, pattern),
    ).fetchall()
    missing: list[str] = []
    for code, future_path, series_code in rows:
        dest = output_path(
            future_path, "video", root=root, series_code=series_code or ""
        )
        if not dest.is_file():
            missing.append(code)
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download missing MP4 video for catalog items"
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--video-sleep-interval",
        type=int,
        default=DEFAULT_VIDEO_SLEEP_INTERVAL,
        help="yt-dlp min seconds to sleep before each video download (default: %(default)s)",
    )
    parser.add_argument(
        "--video-max-sleep-interval",
        type=int,
        default=DEFAULT_VIDEO_MAX_SLEEP_INTERVAL,
        help="yt-dlp max seconds to sleep before each video download (default: %(default)s)",
    )
    parser.add_argument(
        "--subs",
        action="store_true",
        help="Also download manual English subtitles per item (default: video only)",
    )
    args = parser.parse_args()

    root = media_root(args.library_root)
    conn = sqlite3.connect(DB_PATH)
    ensure_footage_schema(conn)
    codes = missing_codes(conn, args.section, root=root)
    if not codes:
        scope = args.section or "all"
        print(f"No missing video files for section {scope!r}")
        return

    print(f"Missing video: {len(codes)} item(s)" + (f" in {args.section}" if args.section else ""))
    if args.dry_run:
        for code in codes:
            print(f"  {code}")
        return

    failed = 0
    for i, code in enumerate(codes, 1):
        print(f"\n[{i}/{len(codes)}] {code}")
        cmd = [
            sys.executable,
            str(DOWNLOAD_ITEM),
            code,
            "--video",
            "--cookies-from-browser",
            args.cookies_from_browser,
            "--video-sleep-interval",
            str(args.video_sleep_interval),
            "--video-max-sleep-interval",
            str(args.video_max_sleep_interval),
        ]
        if args.subs:
            cmd.append("--subs")
        else:
            cmd.append("--no-subs")
        if args.library_root:
            cmd.extend(["--library-root", str(args.library_root)])
        rc = subprocess.call(cmd)
        if rc != 0:
            failed += 1
            print(f"  !! {code} failed (exit {rc})", file=sys.stderr)

    if failed:
        print(f"\nFinished: {len(codes) - failed}/{len(codes)} OK, {failed} failed", file=sys.stderr)
        sys.exit(1)
    print(f"\nDone: {len(codes)} video(s) downloaded")


if __name__ == "__main__":
    main()