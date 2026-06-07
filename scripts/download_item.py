#!/usr/bin/env python3
"""Download one catalog item by code (including orphans without series_code)."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
CACHED_BROWSER_COOKIES = ROOT / "catalog" / ".yt-browser-cookies.txt"

from download_series import (  # noqa: E402
    export_browser_cookies,
    download_audio,
    download_subtitle_for_item,
    media_root,
    output_path,
    resolve_cookies_file,
)


def fetch_item(conn: sqlite3.Connection, code: str) -> tuple[int, str, str, str | None, str, str]:
    row = conn.execute(
        """
        SELECT i.id, i.code, i.title, i.series_code, i.future_path, l.url
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source = 'kft_pdf_youtube' AND l.link_kind = 'primary'
        WHERE i.code = ?
        """,
        (code,),
    ).fetchone()
    if not row:
        raise SystemExit(f"No linked item for code {code!r}")
    return row[0], row[1], row[2], row[3], row[4], row[5]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download one catalog item by code")
    parser.add_argument("codes", nargs="+", help="Item codes e.g. UN84T MA84TR")
    parser.add_argument("--audio", choices=("best", "mp3"), default="best")
    parser.add_argument("--library-root", type=Path, default=None)
    parser.add_argument("--cookies", type=Path, default=None)
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", default="chrome")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-subs",
        action="store_true",
        help="Skip manual English subtitle download (default: download with audio)",
    )
    args = parser.parse_args()

    browser = (
        args.cookies_from_browser
        or os.environ.get("KRISHNAMURTI_YT_COOKIES_BROWSER")
        or "chrome"
    )
    cookies_file: Path | None = None
    cookies_browser: str | None = None
    if args.cookies:
        cookies_file = resolve_cookies_file(args.cookies)
    else:
        exported = export_browser_cookies(browser, CACHED_BROWSER_COOKIES)
        if exported:
            cookies_file = exported
        else:
            cookies_browser = browser

    root = media_root(args.library_root)
    conn = sqlite3.connect(DB_PATH)
    failed = 0
    for code in args.codes:
        item_id, _code, title, series_code, future_path, url = fetch_item(conn, code)
        audio_future = future_path.replace(".mp4", ".m4a")
        dest = output_path(
            audio_future, args.audio, root=root, series_code=series_code or ""
        )
        print(f"\n=== {code}: {title[:60]} ===")
        print(f"  -> {dest}")
        if dest.is_file() and not args.dry_run:
            print("  audio SKIP (already on disk)")
        else:
            rc = download_audio(
                url,
                dest,
                audio_mode=args.audio,
                write_info_json=False,
                cookies_file=cookies_file,
                cookies_browser=cookies_browser,
                dry_run=args.dry_run,
            )
            if rc != 0:
                print(f"  audio FAILED (exit {rc})")
                failed += 1
            else:
                print("  audio OK")

        if not args.no_subs:
            sub_result = download_subtitle_for_item(
                conn,
                item_id=item_id,
                future_path=future_path,
                series_code=series_code or "",
                url=url,
                root=root,
                cookies_file=cookies_file,
                cookies_browser=cookies_browser,
                dry_run=args.dry_run,
            )
            if sub_result == "downloaded":
                print("  subs OK")
            elif sub_result == "skipped":
                print("  subs SKIP (already on disk)")
            elif sub_result == "missing":
                print("  subs: no manual English")
            else:
                print("  subs FAILED")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()