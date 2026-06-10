#!/usr/bin/env python3
"""Redownload audio items as YouTube format 140 (129 kbps AAC, no re-encode).

By default selects items whose on-disk bitrate (item_media.file_size over
PDF duration) falls below --below-kbps — catching both low-quality early
downloads (format 18 audio ~96k) and corrupt/truncated files. Downloads
to a temp name and only replaces the original after a size sanity check.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"

from download_series import (  # noqa: E402
    media_root,
    output_path,
    resolve_yt_auth,
    yt_auth_args,
)
from media_schema import ensure_media_schema, record_media_result  # noqa: E402

# Accept files no smaller than this fraction of the bitrate-implied size.
MIN_EXPECTED_RATIO = 0.5
FORMAT_140_KBPS = 129


def select_items(
    conn: sqlite3.Connection, codes: list[str], below_kbps: float
) -> list[tuple]:
    base = """
        SELECT i.id, i.code, i.title, i.future_path, i.series_code,
               i.duration_minutes, l.url
        FROM item_media m
        JOIN items i ON i.id = m.item_id
        JOIN item_links l ON l.item_id = i.id
          AND l.source = 'kft_pdf_youtube' AND l.link_kind = 'primary'
        WHERE m.media = 'audio' AND m.status = 'downloaded'
    """
    if codes:
        marks = ",".join("?" for _ in codes)
        return conn.execute(f"{base} AND i.code IN ({marks})", codes).fetchall()
    return conn.execute(
        f"""
        {base}
          AND i.duration_minutes > 0 AND m.file_size IS NOT NULL
          AND m.file_size * 8.0 / 1000.0 / (i.duration_minutes * 60) < ?
        ORDER BY i.pdf_order
        """,
        (below_kbps,),
    ).fetchall()


def download_140(
    url: str,
    tmp_dest: Path,
    *,
    cookies_file: Path | None,
    cookies_browser: str | None,
    dry_run: bool,
) -> int:
    out_tpl = str(tmp_dest.with_suffix("")) + ".%(ext)s"
    cmd = [
        "yt-dlp",
        "--no-update",
        "--no-playlist",
        "-f",
        "140",
        "--embed-metadata",
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--sleep-interval",
        "5",
        "--max-sleep-interval",
        "15",
        "-o",
        out_tpl,
    ]
    cmd.extend(yt_auth_args(cookies_file=cookies_file, cookies_browser=cookies_browser))
    cmd.append(url)
    if dry_run:
        print(" ".join(cmd))
        return 0
    return subprocess.call(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Redownload audio as format 140 (129k AAC)"
    )
    parser.add_argument(
        "codes", nargs="*", help="Item codes; default: all below --below-kbps"
    )
    parser.add_argument("--below-kbps", type=float, default=110.0)
    parser.add_argument("--library-root", type=Path, default=None)
    parser.add_argument("--cookies", type=Path, default=None)
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", default="chrome")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = media_root(args.library_root)
    if not root.is_dir() and not args.dry_run:
        raise SystemExit(f"Media root not found: {root}")

    conn = sqlite3.connect(DB_PATH)
    ensure_media_schema(conn)
    rows = select_items(conn, args.codes, args.below_kbps)
    if not rows:
        raise SystemExit("No matching audio items")

    print(f"Redownloading {len(rows)} item(s) as format 140 (129k AAC)")
    cookies_file, cookies_browser = resolve_yt_auth(
        cookies_file_arg=args.cookies,
        browser=args.cookies_from_browser,
        prefer_live=False,
    )

    replaced = failed = 0
    for item_id, code, title, future_path, series_code, minutes, url in rows:
        dest = output_path(future_path, "best", root=root, series_code=series_code or "")
        tmp_dest = dest.parent / f"{dest.stem}.redl.m4a"
        print(f"\n=== {code}: {title[:60]} ===")
        print(f"  -> {dest}")
        if args.dry_run:
            download_140(
                url,
                tmp_dest,
                cookies_file=cookies_file,
                cookies_browser=cookies_browser,
                dry_run=True,
            )
            continue

        rc = download_140(
            url,
            tmp_dest,
            cookies_file=cookies_file,
            cookies_browser=cookies_browser,
            dry_run=False,
        )
        expected = minutes * 60 * FORMAT_140_KBPS * 1000 / 8 if minutes else 0
        if rc != 0 or not tmp_dest.is_file():
            print(f"  FAILED (exit {rc}); keeping existing file")
            failed += 1
        elif expected and tmp_dest.stat().st_size < expected * MIN_EXPECTED_RATIO:
            print(
                f"  FAILED size check ({tmp_dest.stat().st_size} bytes, "
                f"expected ~{int(expected)}); keeping existing file"
            )
            tmp_dest.unlink()
            failed += 1
        else:
            old = dest.stat().st_size if dest.is_file() else 0
            os.replace(tmp_dest, dest)
            record_media_result(
                conn, item_id=item_id, media="audio", dest=dest, root=root, rc=0
            )
            print(f"  OK ({old} -> {dest.stat().st_size} bytes)")
            replaced += 1
        # clean any yt-dlp leftovers (.part etc.) for the temp name
        for stray in dest.parent.glob(f"{dest.stem}.redl.*"):
            stray.unlink()

    print(f"\nDone: {replaced} replaced, {failed} failed, {len(rows)} total")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
