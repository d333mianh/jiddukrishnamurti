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
from download_series import (  # noqa: E402
    DEFAULT_VIDEO_MAX_SLEEP_INTERVAL,
    DEFAULT_VIDEO_SLEEP_INTERVAL,
    download_audio,
    download_video,
    download_subtitle_for_item,
    media_root,
    output_path,
    resolve_yt_auth,
)


def fetch_item(conn: sqlite3.Connection, code: str) -> tuple[int, str, str, str | None, str, str]:
    row = conn.execute(
        """
        SELECT i.id, i.code, i.title, i.series_code, i.future_path, l.url
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source IN ('kft_pdf_youtube', 'kft_channel_scan') AND l.link_kind = 'primary'
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--video",
        action="store_true",
        help="Download best-quality MP4 video to catalog .mp4 path",
    )
    mode.add_argument("--audio", choices=("best", "mp3"), default="best")
    parser.add_argument("--library-root", type=Path, default=None)
    parser.add_argument("--cookies", type=Path, default=None)
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", default="chrome")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-subs",
        action="store_true",
        help="Skip manual English subtitle download (default with --audio)",
    )
    parser.add_argument(
        "--subs",
        action="store_true",
        help="Also download manual English subtitles (off by default with --video)",
    )
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
    args = parser.parse_args()
    media_mode = "video" if args.video else args.audio
    download_subs = (not args.no_subs) if not args.video else args.subs

    browser = (
        args.cookies_from_browser
        or os.environ.get("KRISHNAMURTI_YT_COOKIES_BROWSER")
        or "chrome"
    )
    cookies_file, cookies_browser = resolve_yt_auth(
        cookies_file_arg=args.cookies,
        browser=browser,
        prefer_live=args.video,
    )

    root = media_root(args.library_root)
    conn = sqlite3.connect(DB_PATH)
    from footage_schema import FOOTAGE_VIDEO, ensure_footage_schema  # noqa: WPS433
    from media_schema import ensure_media_schema, record_media_result  # noqa: WPS433

    ensure_footage_schema(conn)
    ensure_media_schema(conn)
    failed = 0
    media_label = "video" if args.video else "audio"
    for code in args.codes:
        item_id, _code, title, series_code, future_path, url = fetch_item(conn, code)
        footage = conn.execute(
            "SELECT footage_type FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if args.video and footage and footage[0] != FOOTAGE_VIDEO:
            print(f"\n=== {code}: {title[:60]} ===")
            print("  video SKIP (PDF audio-only; no real footage)")
            continue
        dest = output_path(
            future_path, media_mode, root=root, series_code=series_code or ""
        )
        print(f"\n=== {code}: {title[:60]} ===")
        print(f"  -> {dest}")
        if dest.is_file() and not args.dry_run:
            print(f"  {media_label} SKIP (already on disk)")
            record_media_result(
                conn, item_id=item_id, media=media_label, dest=dest, root=root, rc=None
            )
        elif args.video:
            rc = download_video(
                url,
                dest,
                write_info_json=False,
                cookies_file=cookies_file,
                cookies_browser=cookies_browser,
                dry_run=args.dry_run,
                sleep_interval=args.video_sleep_interval,
                max_sleep_interval=args.video_max_sleep_interval,
            )
            if rc != 0:
                print(f"  {media_label} FAILED (exit {rc})")
                failed += 1
            else:
                print(f"  {media_label} OK")
            if not args.dry_run:
                record_media_result(
                    conn, item_id=item_id, media=media_label, dest=dest, root=root, rc=rc
                )
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
                print(f"  {media_label} FAILED (exit {rc})")
                failed += 1
            else:
                print(f"  {media_label} OK")
            if not args.dry_run:
                record_media_result(
                    conn, item_id=item_id, media=media_label, dest=dest, root=root, rc=rc
                )

        if download_subs:
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