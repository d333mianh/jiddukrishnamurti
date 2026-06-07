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


def series_in_section(conn: sqlite3.Connection, section_prefix: str) -> list[str]:
    """section_prefix e.g. '1A' matches library/1A-public-meetings-england/..."""
    pattern = f"library/{section_prefix}-%"
    rows = conn.execute(
        """
        SELECT i.series_code
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source = 'kft_pdf_youtube' AND l.link_kind = 'primary'
        WHERE i.future_path LIKE ? AND i.series_code IS NOT NULL
        GROUP BY i.series_code
        ORDER BY MIN(i.pdf_order)
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
    parser.add_argument("--audio", choices=("best", "mp3"), default="best")
    parser.add_argument("--library-root", type=Path, default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    codes = series_in_section(conn, args.section)
    if not codes:
        raise SystemExit(f"No linked series for section {args.section!r}")

    if args.from_series:
        try:
            start = codes.index(args.from_series)
            codes = codes[start:]
        except ValueError:
            raise SystemExit(f"Series {args.from_series!r} not in section {args.section}")

    print(f"Section {args.section}: {len(codes)} series to process")
    failed: list[str] = []
    for i, code in enumerate(codes, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(codes)}] {code}\n{'=' * 60}")
        cmd = [
            sys.executable,
            str(DOWNLOAD_SERIES),
            code,
            "--audio",
            args.audio,
            "--cookies-from-browser",
            args.cookies_from_browser,
        ]
        if args.library_root:
            cmd.extend(["--library-root", str(args.library_root)])
        if args.dry_run:
            cmd.append("--dry-run")
        rc = subprocess.call(cmd)
        if rc != 0:
            failed.append(code)
            print(f"  !! {code} failed (exit {rc})", file=sys.stderr)

    if failed:
        print(f"\nFinished with failures: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)
    print(f"\nSection {args.section}: all {len(codes)} series complete.")


if __name__ == "__main__":
    main()