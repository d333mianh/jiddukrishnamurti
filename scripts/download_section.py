#!/usr/bin/env python3
"""Download all catalog series in a section (e.g. 1A) via download_series.py."""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
DOWNLOAD_SERIES = ROOT / "scripts" / "download_series.py"
DOWNLOAD_ITEM = ROOT / "scripts" / "download_item.py"


def series_in_section(
    conn: sqlite3.Connection, section_prefix: str, *, video_only: bool = False
) -> list[str]:
    """section_prefix e.g. '1A' matches library/1A-public-meetings-england/..."""
    pattern = f"library/{section_prefix}-%"
    footage_clause = " AND i.footage_type = 'video_footage'" if video_only else ""
    rows = conn.execute(
        f"""
        SELECT i.series_code
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source = 'kft_pdf_youtube' AND l.link_kind = 'primary'
        WHERE i.future_path LIKE ? AND i.series_code IS NOT NULL{footage_clause}
        GROUP BY i.series_code
        ORDER BY MIN(i.pdf_order)
        """,
        (pattern,),
    ).fetchall()
    return [r[0] for r in rows]


def orphan_video_codes(conn: sqlite3.Connection, section_prefix: str) -> list[str]:
    pattern = f"library/{section_prefix}-%"
    rows = conn.execute(
        """
        SELECT i.code
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source = 'kft_pdf_youtube' AND l.link_kind = 'primary'
        WHERE i.future_path LIKE ? AND i.series_code IS NULL
          AND i.footage_type = 'video_footage'
        ORDER BY i.pdf_order
        """,
        (pattern,),
    ).fetchall()
    return [r[0] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download all series in a catalog section")
    parser.add_argument(
        "section",
        help="Section id prefix (e.g. 1A for library/1A-... paths)",
    )
    parser.add_argument("--from-series", default=None, help="Start at this series_code (inclusive)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        default="chrome",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--video",
        action="store_true",
        help="Download best-quality MP4 video (passes through to download_series.py)",
    )
    mode.add_argument("--audio", choices=("best", "mp3"), default="best")
    parser.add_argument(
        "--no-subs",
        action="store_true",
        help="Skip subtitles (default with --video in download_series.py)",
    )
    parser.add_argument(
        "--subs",
        action="store_true",
        help="Download manual EN subtitles with --video",
    )
    parser.add_argument("--library-root", type=Path, default=None)
    args = parser.parse_args()

    from footage_schema import ensure_footage_schema  # noqa: WPS433

    conn = sqlite3.connect(DB_PATH)
    ensure_footage_schema(conn)
    codes = series_in_section(conn, args.section, video_only=args.video)
    orphans = orphan_video_codes(conn, args.section) if args.video else []
    if not codes and not orphans:
        label = "video series" if args.video else "linked series"
        raise SystemExit(f"No {label} for section {args.section!r}")

    if args.from_series:
        try:
            start = codes.index(args.from_series)
            codes = codes[start:]
        except ValueError:
            raise SystemExit(f"Series {args.from_series!r} not in section {args.section}")

    print(
        f"Section {args.section}: {len(codes)} series"
        + (f", {len(orphans)} orphan video item(s)" if orphans else "")
        + " to process"
    )
    failed: list[str] = []
    for i, code in enumerate(codes, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(codes)}] {code}\n{'=' * 60}")
        cmd = [
            sys.executable,
            str(DOWNLOAD_SERIES),
            code,
            "--cookies-from-browser",
            args.cookies_from_browser,
        ]
        if args.video:
            cmd.append("--video")
            if args.subs:
                cmd.append("--subs")
            else:
                cmd.append("--no-subs")
        else:
            cmd.extend(["--audio", args.audio])
            if args.no_subs:
                cmd.append("--no-subs")
            elif args.subs:
                pass
        if args.library_root:
            cmd.extend(["--library-root", str(args.library_root)])
        if args.dry_run:
            cmd.append("--dry-run")
        rc = subprocess.call(cmd)
        if rc != 0:
            failed.append(code)
            print(f"  !! {code} failed (exit {rc})", file=sys.stderr)

    if orphans:
        print(f"\n{'=' * 60}\nOrphan video items: {', '.join(orphans)}\n{'=' * 60}")
        cmd = [
            sys.executable,
            str(DOWNLOAD_ITEM),
            *orphans,
            "--cookies-from-browser",
            args.cookies_from_browser,
        ]
        if args.video:
            cmd.append("--video")
            cmd.append("--no-subs")
        if args.library_root:
            cmd.extend(["--library-root", str(args.library_root)])
        if args.dry_run:
            cmd.append("--dry-run")
        rc = subprocess.call(cmd)
        if rc != 0:
            failed.extend(orphans)

    succeeded = len(codes) - len([c for c in failed if c in codes])
    if failed:
        print(
            f"\nSection {args.section}: {succeeded}/{len(codes)} series OK; "
            f"failures: {', '.join(failed)}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"\nSection {args.section}: all {len(codes)} series complete.")


if __name__ == "__main__":
    main()