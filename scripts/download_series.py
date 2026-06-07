#!/usr/bin/env python3
"""Download a catalog series from KFT PDF YouTube links (audio or video)."""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
DEFAULT_COOKIES_FILE = ROOT / "www.youtube.com_cookies.txt"
CACHED_BROWSER_COOKIES = ROOT / "catalog" / ".yt-browser-cookies.txt"

# Default: iCloud Drive (override with --library-root or KRISHNAMURTI_MEDIA_ROOT)
DEFAULT_MEDIA_ROOT = (
    Path.home()
    / "Library/Mobile Documents/com~apple~CloudDocs/Krishnamurti"
)


def media_root(path: Path | None = None) -> Path:
    if path is not None:
        return path.expanduser().resolve()
    env = os.environ.get("KRISHNAMURTI_MEDIA_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_MEDIA_ROOT.resolve()


def resolve_media_path(future_path: str, *, root: Path) -> Path:
    """Map catalog future_path (library/...) under media root."""
    rel = Path(future_path)
    if rel.parts and rel.parts[0] == "library":
        rel = Path(*rel.parts[1:])
    return root / "library" / rel


def series_dir_name(series_code: str, series_order: int | None) -> str:
    """Folder name sorted like PDF: 0000-LO61T1-12."""
    sc = (series_code or "").strip()
    if not sc:
        return ""
    if series_order is not None:
        return f"{int(series_order):04d}-{sc}"
    return sc


def ordered_series_future_path(
    future_path: str, *, series_code: str, series_order: int | None
) -> str:
    """Rewrite library/<section>/<series-dir>/<file> with PDF-order folder prefix."""
    p = Path(future_path)
    if len(p.parts) < 4 or p.parts[0] != "library":
        return future_path
    section, filename = p.parts[1], p.parts[-1]
    folder = series_dir_name(series_code, series_order)
    if not folder:
        return future_path
    return str(Path("library") / section / folder / filename)


def fetch_series(conn: sqlite3.Connection, series_code: str) -> list[tuple]:
    return conn.execute(
        """
        SELECT i.id, i.code, i.title, i.future_path, l.url
        FROM items i
        JOIN item_links l ON l.item_id = i.id
          AND l.source = 'kft_pdf_youtube' AND l.link_kind = 'primary'
        WHERE i.series_code = ?
        ORDER BY i.series_order NULLS LAST, i.pdf_order
        """,
        (series_code,),
    ).fetchall()


def download_subtitle_for_item(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    future_path: str,
    series_code: str,
    url: str,
    root: Path,
    cookies_file: Path | None,
    cookies_browser: str | None,
    dry_run: bool,
) -> str:
    from download_subtitles import process_item_subtitle  # noqa: WPS433
    from subtitle_schema import ensure_subtitle_schema  # noqa: WPS433

    ensure_subtitle_schema(conn)
    return process_item_subtitle(
        conn,
        item_id=item_id,
        future_path=future_path,
        series_code=series_code,
        url=url,
        root=root,
        cookies_file=cookies_file,
        cookies_browser=cookies_browser,
        dry_run=dry_run,
    )


def output_path(
    future_path: str,
    audio_mode: str,
    *,
    root: Path,
    series_code: str,
) -> Path:
    """Resolve catalog path; ensure series subfolder when catalog row is still flat."""
    p = resolve_media_path(future_path, root=root)
    rel = p.relative_to(root / "library")
    # legacy DB paths: library/<section>/<file> → library/<section>/<series-dir>/<file>
    if series_code and len(rel.parts) == 2:
        p = root / "library" / rel.parts[0] / series_dir_name(series_code, None) / rel.parts[1]
    if audio_mode == "mp3":
        return p.with_suffix(".mp3")
    return p


def export_browser_cookies(browser: str, dest: Path) -> Path | None:
    """One keychain unlock per series; reuse Netscape file for each episode."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        [
            "yt-dlp",
            "--no-update",
            "--cookies-from-browser",
            browser,
            "--cookies",
            str(dest),
            "--simulate",
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        ],
        capture_output=True,
    )
    if probe.returncode == 0 and dest.is_file() and dest.stat().st_size > 200:
        return dest
    return None


def resolve_cookies_file(path: Path | None) -> Path | None:
    if path is not None:
        p = path.expanduser().resolve()
        return p if p.is_file() else None
    env = os.environ.get("KRISHNAMURTI_YT_COOKIES_FILE")
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_file() else None
    return DEFAULT_COOKIES_FILE if DEFAULT_COOKIES_FILE.is_file() else None


def yt_auth_args(
    *,
    cookies_file: Path | None,
    cookies_browser: str | None,
) -> list[str]:
    browser = (
        cookies_browser
        or os.environ.get("KRISHNAMURTI_YT_COOKIES")
        or os.environ.get("KRISHNAMURTI_YT_COOKIES_BROWSER")
    )
    if browser:
        return ["--cookies-from-browser", browser]
    if cookies_file is not None:
        return ["--cookies", str(cookies_file)]
    # Live Chrome session avoids 403 seen with exported Netscape cookies.txt
    return ["--cookies-from-browser", "chrome"]


def download_audio(
    url: str,
    dest: Path,
    *,
    audio_mode: str,
    write_info_json: bool,
    cookies_file: Path | None,
    cookies_browser: str | None,
    dry_run: bool,
) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and not dry_run:
        return 0
    out_tpl = str(dest.with_suffix("")) + ".%(ext)s"

    # Prefer format 18 (360p MP4+AAC); fall back to 360p HLS when Google returns 403.
    cmd = [
        "yt-dlp",
        "--no-update",
        "--no-playlist",
        "-f",
        "18/93/91",
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--sleep-interval",
        "15",
        "--max-sleep-interval",
        "60",
        "-o",
        out_tpl,
    ]
    cmd.extend(
        yt_auth_args(cookies_file=cookies_file, cookies_browser=cookies_browser)
    )

    if audio_mode == "best":
        # Preserve source AAC (~128 kbps) — no MP3 re-encode.
        cmd.extend(
            [
                "-x",
                "--audio-format",
                "m4a",
                "--postprocessor-args",
                "ExtractAudio:-c:a copy",
                "--embed-metadata",
            ]
        )
    elif audio_mode == "mp3":
        cmd.extend(
            [
                "-x",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "0",
                "--embed-metadata",
            ]
        )
    else:
        raise ValueError(f"unknown audio_mode: {audio_mode}")

    if write_info_json:
        cmd.append("--write-info-json")

    cmd.append(url)

    if dry_run:
        print(" ".join(cmd))
        return 0
    return subprocess.call(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download one series from PDF YouTube links (audio)"
    )
    parser.add_argument("series_code", help="e.g. LO61T1-12")
    parser.add_argument(
        "--audio",
        choices=("best", "mp3"),
        default="best",
        help="best = AAC copy to catalog .m4a (no re-encode); mp3 = transcode to .mp3",
    )
    parser.add_argument(
        "--info-json",
        action="store_true",
        help="Write yt-dlp .info.json sidecar per file",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--library-root",
        type=Path,
        default=None,
        help=f"Media root (default: iCloud …/Krishnamurti, or KRISHNAMURTI_MEDIA_ROOT)",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        default=None,
        help=f"Netscape cookies.txt (default: {DEFAULT_COOKIES_FILE.name} if present)",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        default="chrome",
        help="Export cookies from browser once per run (default: chrome)",
    )
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
            # Stale cookies.txt often 403s; use live browser session instead.
            cookies_browser = browser
            if DEFAULT_COOKIES_FILE.is_file():
                print(
                    f"  Warning: could not export {browser} cookies; "
                    f"ignoring {DEFAULT_COOKIES_FILE.name}"
                )
    root = media_root(args.library_root)
    if not root.is_dir() and not args.dry_run:
        raise SystemExit(f"Media root not found: {root}")

    conn = sqlite3.connect(DB_PATH)
    rows = fetch_series(conn, args.series_code)
    if not rows:
        raise SystemExit(f"No linked items for series {args.series_code!r}")

    print(f"Media root: {root}")
    print(
        f"Series {args.series_code}: {len(rows)} episodes "
        f"(kft_pdf_youtube, audio={args.audio}"
        f"{', subs=manual-en' if not args.no_subs else ''})"
    )
    if args.audio == "best":
        print("  Note: YouTube only offers ~128 kbps AAC for these talks; best = no MP3 loss.")
    if cookies_file == CACHED_BROWSER_COOKIES:
        print(f"  Cookies: exported from browser ({browser}) -> {cookies_file.name}")
    elif cookies_file:
        print(f"  Cookies: {cookies_file}")
    elif cookies_browser:
        print(f"  Cookies: live browser ({cookies_browser}) per download")
    else:
        print(f"  Cookies: browser ({browser}) per download")

    failed = 0
    skipped = 0
    sub_stats = {"downloaded": 0, "skipped": 0, "missing": 0, "failed": 0}
    for item_id, code, title, future_path, url in rows:
        dest = output_path(
            future_path, args.audio, root=root, series_code=args.series_code
        )
        print(f"\n=== {code}: {title[:60]} ===")
        print(f"  -> {dest}")
        if dest.is_file() and not args.dry_run:
            print("  audio SKIP (already on disk)")
            skipped += 1
        else:
            rc = download_audio(
                url,
                dest,
                audio_mode=args.audio,
                write_info_json=args.info_json,
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
                series_code=args.series_code,
                url=url,
                root=root,
                cookies_file=cookies_file,
                cookies_browser=cookies_browser,
                dry_run=args.dry_run,
            )
            sub_stats[sub_result if sub_result in sub_stats else "failed"] += 1
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
    print(
        f"\nDone: {len(rows) - failed - skipped}/{len(rows)} audio downloaded, "
        f"{skipped} audio skipped, {failed} audio failed"
    )
    if not args.no_subs:
        print(
            f"Subs: {sub_stats['downloaded']} downloaded, {sub_stats['skipped']} skipped, "
            f"{sub_stats['missing']} missing manual EN, {sub_stats['failed']} failed"
        )


if __name__ == "__main__":
    main()