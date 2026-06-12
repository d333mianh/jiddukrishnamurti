#!/usr/bin/env python3
"""Download manual English YouTube subtitles for catalog items (not auto-generated)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
from download_series import (  # noqa: E402
    CACHED_BROWSER_COOKIES,
    media_root,
    output_path,
    resolve_yt_auth,
    yt_auth_args,
)
from subtitle_schema import ensure_subtitle_schema  # noqa: E402

MANUAL_EN_PRIORITY = ("en", "en-US", "en-GB")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pick_manual_english(subtitles: dict | None) -> str | None:
    subs = subtitles or {}
    for lang in MANUAL_EN_PRIORITY:
        if lang in subs:
            return lang
    for lang in sorted(subs):
        if lang == "en" or lang.startswith("en-"):
            return lang
    return None


def subtitle_future_path(audio_future_path: str, lang: str) -> str:
    p = Path(audio_future_path)
    for ext in (".m4a", ".mp4", ".mp3", ".webm", ".mkv"):
        if p.suffix.lower() == ext:
            p = p.with_suffix("")
            break
    return str(p.parent / f"{p.name}.{lang}.vtt")


def subtitle_output_path(
    audio_future_path: str,
    lang: str,
    *,
    root: Path,
    series_code: str | None,
) -> Path:
    audio_dest = output_path(
        audio_future_path, "best", root=root, series_code=series_code or ""
    )
    return audio_dest.with_suffix("").with_suffix(f".{lang}.vtt")


def probe_manual_language(
    url: str,
    *,
    cookies_file: Path | None,
    cookies_browser: str | None,
    timeout: int = 120,
    retries: int = 3,
) -> tuple[str | None, str | None]:
    cmd = [
        "yt-dlp",
        "--no-update",
        "--dump-json",
        "--skip-download",
        *yt_auth_args(cookies_file=cookies_file, cookies_browser=cookies_browser),
        url,
    ]
    last_error: str | None = None
    for attempt in range(1, retries + 1):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last_error = f"probe timed out after {timeout}s (attempt {attempt}/{retries})"
            if attempt < retries:
                time.sleep(5 * attempt)
                continue
            return None, last_error
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            last_error = err[-1] if err else f"yt-dlp exit {proc.returncode}"
            return None, last_error
        data = json.loads(proc.stdout)
        return pick_manual_english(data.get("subtitles")), None
    return None, last_error


def download_manual_subtitle(
    url: str,
    dest: Path,
    lang: str,
    *,
    cookies_file: Path | None,
    cookies_browser: str | None,
    dry_run: bool,
) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 50:
        return 0
    suffix = f".{lang}.vtt"
    if not dest.name.endswith(suffix):
        return 1
    out_base = str(dest.parent / dest.name[: -len(suffix)])

    cmd = [
        "yt-dlp",
        "--no-update",
        "--no-playlist",
        "--write-subs",
        "--sub-langs",
        lang,
        "--sub-format",
        "vtt",
        "--skip-download",
        "--retries",
        "5",
        "-o",
        out_base,
        *yt_auth_args(cookies_file=cookies_file, cookies_browser=cookies_browser),
        url,
    ]
    if dry_run:
        print(" ".join(cmd))
        return 0
    rc = subprocess.call(cmd)
    if rc == 0 and dest.is_file() and dest.stat().st_size > 50:
        return 0
    # yt-dlp may write sibling path; accept any matching lang file in folder
    if rc == 0:
        matches = list(dest.parent.glob(f"*.{lang}.vtt"))
        if matches and matches[0].stat().st_size > 50:
            if matches[0] != dest and not dest.is_file():
                matches[0].rename(dest)
            return 0
    return rc or 1


def upsert_subtitle_row(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    language: str,
    future_path: str,
    status: str,
    error_message: str | None = None,
    file_size: int | None = None,
    downloaded: bool = False,
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO item_subtitles (
            item_id, language, kind, format, future_path, file_size,
            status, error_message, probed_at, downloaded_at
        ) VALUES (?, ?, 'manual', 'vtt', ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id, language, kind) DO UPDATE SET
            future_path = excluded.future_path,
            file_size = excluded.file_size,
            status = excluded.status,
            error_message = excluded.error_message,
            probed_at = excluded.probed_at,
            downloaded_at = COALESCE(excluded.downloaded_at, item_subtitles.downloaded_at)
        """,
        (
            item_id,
            language,
            future_path,
            file_size,
            status,
            error_message,
            now,
            now if downloaded else None,
        ),
    )


def process_item_subtitle(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    future_path: str,
    series_code: str | None,
    url: str,
    root: Path,
    cookies_file: Path | None,
    cookies_browser: str | None,
    dry_run: bool = False,
) -> str:
    """Download manual EN subtitle for one item. Returns: downloaded|skipped|missing|failed."""
    fp = future_path.replace(".mp4", ".m4a")
    lang, probe_error = probe_manual_language(
        url, cookies_file=cookies_file, cookies_browser=cookies_browser
    )
    if probe_error and probe_error.startswith("probe timed out"):
        upsert_subtitle_row(
            conn,
            item_id=item_id,
            language="en",
            future_path=subtitle_future_path(fp, "en"),
            status="failed",
            error_message=probe_error,
        )
        conn.commit()
        return "failed"
    if not lang:
        upsert_subtitle_row(
            conn,
            item_id=item_id,
            language="en",
            future_path=subtitle_future_path(fp, "en"),
            status="missing",
            error_message=probe_error or "no manual English track on YouTube",
        )
        conn.commit()
        return "missing"

    sub_future = subtitle_future_path(fp, lang)
    dest = subtitle_output_path(fp, lang, root=root, series_code=series_code)
    if dest.is_file() and dest.stat().st_size > 50:
        upsert_subtitle_row(
            conn,
            item_id=item_id,
            language=lang,
            future_path=sub_future,
            status="downloaded",
            file_size=dest.stat().st_size,
            downloaded=True,
        )
        conn.commit()
        return "skipped"

    rc = download_manual_subtitle(
        url,
        dest,
        lang,
        cookies_file=cookies_file,
        cookies_browser=cookies_browser,
        dry_run=dry_run,
    )
    if rc == 0 and dest.is_file():
        upsert_subtitle_row(
            conn,
            item_id=item_id,
            language=lang,
            future_path=sub_future,
            status="downloaded",
            file_size=dest.stat().st_size,
            downloaded=True,
        )
        conn.commit()
        return "downloaded"

    upsert_subtitle_row(
        conn,
        item_id=item_id,
        language=lang,
        future_path=sub_future,
        status="failed",
        error_message=f"yt-dlp exit {rc}",
    )
    conn.commit()
    return "failed"


def fetch_items(
    conn: sqlite3.Connection,
    *,
    section: str | None,
    from_code: str | None,
) -> list[tuple[int, str, str, str | None, str, str]]:
    sql = """
        SELECT i.id, i.code, i.title, i.series_code, i.future_path, l.url
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source IN ('kft_pdf_youtube', 'kft_channel_scan') AND l.link_kind = 'primary'
    """
    params: list[str] = []
    if section:
        sql += """
        JOIN sections s ON s.id = i.section_id
        WHERE s.code = ?
        """
        params.append(section)
    else:
        sql += " WHERE 1=1 "
    sql += " ORDER BY i.pdf_order"
    rows = conn.execute(sql, params).fetchall()
    if from_code:
        codes = [r[1] for r in rows]
        try:
            idx = codes.index(from_code)
            rows = rows[idx:]
        except ValueError:
            raise SystemExit(f"Code {from_code!r} not found")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download manual English subtitles for PDF YouTube links"
    )
    parser.add_argument(
        "--section",
        default=None,
        help="Limit to section code (e.g. 1A). Default: all linked items.",
    )
    parser.add_argument("--from-code", default=None, help="Resume at this item code")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--library-root",
        type=Path,
        default=None,
        help="Media root (default: iCloud …/00-cod3/jiddu-krishnamurti)",
    )
    parser.add_argument("--cookies", type=Path, default=None)
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
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Record availability in DB without downloading files",
    )
    args = parser.parse_args()

    browser = (
        args.cookies_from_browser
        or os.environ.get("KRISHNAMURTI_YT_COOKIES_BROWSER")
        or "chrome"
    )
    cookies_file, cookies_browser = resolve_yt_auth(
        cookies_file_arg=args.cookies,
        browser=browser,
        prefer_live=False,
    )

    root = media_root(args.library_root)
    conn = sqlite3.connect(DB_PATH)
    ensure_subtitle_schema(conn)

    rows = fetch_items(conn, section=args.section, from_code=args.from_code)
    if not rows:
        raise SystemExit("No linked items matched.")

    scope = args.section or "all"
    print(f"Subtitles: {len(rows)} items ({scope}), manual en/en-US/en-GB only")
    if args.probe_only:
        print("  Mode: probe-only (no file download)")
    if cookies_file == CACHED_BROWSER_COOKIES:
        print(f"  Cookies: exported from {browser}")
    elif cookies_browser:
        print(f"  Cookies: live browser ({cookies_browser})")

    stats = {"downloaded": 0, "skipped": 0, "missing": 0, "failed": 0}
    for i, (item_id, code, title, series_code, future_path, url) in enumerate(
        rows, 1
    ):
        print(f"\n[{i}/{len(rows)}] {code}: {title[:55]}")
        if args.probe_only:
            lang, probe_error = probe_manual_language(
                url, cookies_file=cookies_file, cookies_browser=cookies_browser
            )
            if lang:
                upsert_subtitle_row(
                    conn,
                    item_id=item_id,
                    language=lang,
                    future_path=subtitle_future_path(
                        future_path.replace(".mp4", ".m4a"), lang
                    ),
                    status="available",
                )
                stats["downloaded"] += 1
            else:
                stats["missing" if not probe_error else "failed"] += 1
            conn.commit()
            time.sleep(args.sleep)
            continue

        result = process_item_subtitle(
            conn,
            item_id=item_id,
            future_path=future_path,
            series_code=series_code,
            url=url,
            root=root,
            cookies_file=cookies_file,
            cookies_browser=cookies_browser,
            dry_run=args.dry_run,
        )
        if result == "downloaded":
            print("  OK")
        elif result == "skipped":
            print("  SKIP (already on disk)")
        elif result == "missing":
            print("  no manual English subtitles")
        else:
            print("  FAILED")
        stats[result if result in stats else "failed"] += 1
        time.sleep(args.sleep)

    print(
        f"\nDone: {stats['downloaded']} downloaded, {stats['skipped']} skipped, "
        f"{stats['missing']} missing manual EN, {stats['failed']} failed"
    )
    if stats["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()