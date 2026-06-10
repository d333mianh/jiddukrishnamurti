#!/usr/bin/env python3
"""Move/rename library media to match catalog (series subfolders, PDF order)."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from download_series import (
    DB_PATH,
    media_root,
    ordered_series_future_path,
    resolve_media_path,
    series_dir_name,
)

ROOT = Path(__file__).resolve().parents[1]


def flat_legacy_path(future_path: str, *, root: Path) -> Path | None:
    """Pre-migration path: library/<section>/<file> (no series folder)."""
    p = Path(future_path)
    if len(p.parts) != 4 or p.parts[0] != "library":
        return None
    _lib, section, _series, filename = p.parts
    return root / "library" / section / filename


def bare_series_dir(root: Path, section: str, series_code: str) -> Path:
    return root / "library" / section / series_code


def update_db_series_paths(conn: sqlite3.Connection, *, dry_run: bool) -> int:
    rows = conn.execute(
        """
        SELECT id, series_code, series_order, future_path
        FROM items
        WHERE series_code IS NOT NULL AND trim(series_code) != ''
        """
    ).fetchall()
    changed = 0
    for item_id, series_code, series_order, future_path in rows:
        new_path = ordered_series_future_path(
            future_path,
            series_code=series_code,
            series_order=series_order,
        )
        if new_path == future_path:
            continue
        print(f"DB {series_code}: {future_path} -> {new_path}")
        if not dry_run:
            conn.execute(
                "UPDATE items SET future_path = ? WHERE id = ?",
                (new_path, item_id),
            )
        changed += 1
    if not dry_run and changed:
        conn.commit()
    return changed


def rename_series_folders(
    conn: sqlite3.Connection,
    *,
    root: Path,
    section: str | None,
    series: str | None,
    dry_run: bool,
) -> int:
    sql = """
        SELECT DISTINCT
            substr(future_path, 9, instr(substr(future_path, 9), '/') - 1) AS section_slug,
            series_code,
            series_order
        FROM items
        WHERE series_code IS NOT NULL AND trim(series_code) != ''
          AND future_path LIKE 'library/%/%/%'
    """
    params: list[str] = []
    if series:
        sql += " AND series_code = ?"
        params.append(series)
    rows = conn.execute(sql, params).fetchall()

    renamed = 0
    for section_slug, series_code, series_order in rows:
        if section and section_slug != section:
            continue
        ordered = series_dir_name(series_code, series_order)
        src = bare_series_dir(root, section_slug, series_code)
        dst = root / "library" / section_slug / ordered
        if src == dst or not src.is_dir():
            continue
        if dst.exists():
            print(f"SKIP rename {series_code}: {dst.relative_to(root)} exists")
            continue
        print(
            f"RENAME {series_code}\n"
            f"  {src.relative_to(root)}\n"
            f"  -> {dst.relative_to(root)}"
        )
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        renamed += 1
    return renamed


def move_flat_into_series(
    conn: sqlite3.Connection,
    *,
    root: Path,
    section: str | None,
    series: str | None,
    dry_run: bool,
) -> tuple[int, int, int]:
    sql = """
        SELECT code, series_code, future_path
        FROM items
        WHERE series_code IS NOT NULL AND trim(series_code) != ''
    """
    params: list[str] = []
    if series:
        sql += " AND series_code = ?"
        params.append(series)
    if section:
        sql += " AND future_path LIKE ?"
        params.append(f"library/{section}/%")
    rows = conn.execute(sql, params).fetchall()

    moved = skipped = missing = 0
    for code, _series_code, future_path in rows:
        src = flat_legacy_path(future_path, root=root)
        dst = resolve_media_path(future_path, root=root)
        if src is None:
            continue
        if not src.is_file():
            if dst.is_file():
                skipped += 1
            else:
                missing += 1
            continue
        if dst.is_file():
            print(f"SKIP {code}: already at {dst.relative_to(root)}")
            skipped += 1
            continue
        print(f"MOVE {code}\n  {src.relative_to(root)}\n  -> {dst.relative_to(root)}")
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        moved += 1
    return moved, skipped, missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Align on-disk library with catalog series folders (PDF order)"
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=None,
        help="Media root (default: iCloud …/00-cod3/jiddu-krishnamurti)",
    )
    parser.add_argument(
        "--section",
        help="Only this section slug, e.g. 1A-public-meetings-england",
    )
    parser.add_argument(
        "--series",
        help="Only this series code, e.g. LO61T1-12",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Do not update future_path in SQLite",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = media_root(args.library_root)
    conn = sqlite3.connect(DB_PATH)

    db_changed = 0
    if not args.skip_db:
        db_changed = update_db_series_paths(conn, dry_run=args.dry_run)

    renamed = rename_series_folders(
        conn,
        root=root,
        section=args.section,
        series=args.series,
        dry_run=args.dry_run,
    )
    moved, skipped, missing = move_flat_into_series(
        conn,
        root=root,
        section=args.section,
        series=args.series,
        dry_run=args.dry_run,
    )
    conn.close()

    tag = "Would" if args.dry_run else ""
    print(
        f"\n{tag} update DB paths: {db_changed}, "
        f"{tag.lower() or ''}rename series dirs: {renamed}, "
        f"{tag.lower() or ''}move flat files: {moved}, "
        f"already in place: {skipped}, not on disk: {missing}"
    )


if __name__ == "__main__":
    main()