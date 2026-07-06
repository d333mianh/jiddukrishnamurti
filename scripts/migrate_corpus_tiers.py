#!/usr/bin/env python3
"""Apply explicit corpus tiers to the live catalog and generated corpus."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DB_PATH = ROOT / "catalog" / "krishnamurti.db"
CORPUS_DB_PATH = ROOT / "corpus" / "krishnamurti-corpus.db"

from segment_schema import ensure_corpus_schema, ensure_corpus_tiers


def _readonly_uri(path: Path) -> str:
    return path.expanduser().resolve().as_uri() + "?mode=ro"


def migrate(catalog_db: Path, corpus_db: Path) -> tuple[int, int, int]:
    if not catalog_db.is_file():
        raise FileNotFoundError(f"catalog database not found: {catalog_db}")
    if not corpus_db.is_file():
        raise FileNotFoundError(f"corpus database not found: {corpus_db}")

    catalog_conn = sqlite3.connect(catalog_db)
    try:
        ensure_corpus_tiers(catalog_conn)
        catalog_conn.commit()
    finally:
        catalog_conn.close()

    conn = sqlite3.connect(corpus_db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        ensure_corpus_schema(conn, catalog_db)
        conn.execute("ATTACH DATABASE ? AS catalog", (_readonly_uri(catalog_db),))
        missing = [
            row[0] for row in conn.execute(
                """SELECT DISTINCT t.item_code
                   FROM transcripts t
                   LEFT JOIN catalog.items i ON i.code=t.item_code
                   WHERE i.code IS NULL ORDER BY t.item_code"""
            )
        ]
        if missing:
            raise RuntimeError(
                "corpus transcripts missing from catalog: " + ", ".join(missing)
            )

        conn.execute(
            """UPDATE transcripts
               SET corpus_tier=(
                   SELECT i.corpus_tier FROM catalog.items i
                   WHERE i.code=transcripts.item_code
               )
               WHERE corpus_tier IS NOT (
                   SELECT i.corpus_tier FROM catalog.items i
                   WHERE i.code=transcripts.item_code
               )"""
        )
        before = conn.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0]
        tier_c_before = conn.execute(
            """SELECT COUNT(*)
               FROM passages_fts f
               JOIN passages p ON p.id=f.rowid
               JOIN transcripts t ON t.id=p.transcript_id
               JOIN catalog.items i ON i.code=t.item_code
               WHERE i.corpus_tier='C'"""
        ).fetchone()[0]
        conn.execute(
            """DELETE FROM passages_fts
               WHERE rowid IN (
                   SELECT p.id
                   FROM passages p
                   JOIN transcripts t ON t.id=p.transcript_id
                   JOIN catalog.items i ON i.code=t.item_code
                   WHERE i.corpus_tier='C'
               )"""
        )
        after = conn.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0]
        null_tiers = conn.execute(
            "SELECT COUNT(*) FROM transcripts WHERE corpus_tier IS NULL"
        ).fetchone()[0]
        if null_tiers:
            raise RuntimeError(f"{null_tiers} transcript rows still have NULL corpus_tier")
        removed = before - after
        if removed != tier_c_before:
            raise RuntimeError(
                f"FTS removal mismatch: removed={removed}, "
                f"tier-C before={tier_c_before}"
            )
        conn.commit()
    finally:
        conn.close()

    print(f"passages_fts before={before} after={after} removed={removed}")
    return before, after, removed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog-db", type=Path, default=CATALOG_DB_PATH)
    ap.add_argument("--corpus-db", type=Path, default=CORPUS_DB_PATH)
    args = ap.parse_args()
    try:
        migrate(args.catalog_db, args.corpus_db)
    except (FileNotFoundError, RuntimeError, sqlite3.Error) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
