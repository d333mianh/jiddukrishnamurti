#!/usr/bin/env python3
"""Re-attach stable L3 passage anchors after L2 transcript re-ingest."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DB_PATH = ROOT / "corpus" / "krishnamurti-corpus.db"


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reanchor(
    conn: sqlite3.Connection, item_code: str | None = None, include_all: bool = False
) -> tuple[int, int]:
    where = ["1=1" if include_all else "a.passage_id IS NULL"]
    params: list[object] = []
    if item_code:
        where.append("a.item_code = ?")
        params.append(item_code)
    anchors = conn.execute(
        "SELECT a.id,a.item_code,a.transcript_kind,a.transcript_language,"
        "a.passage_seq,a.text_sha256 "
        "FROM passage_anchors AS a WHERE " + " AND ".join(where) + " ORDER BY a.id",
        params,
    ).fetchall()

    relinked = stale = 0
    passage_maps: dict[
        tuple[str, str, str], tuple[dict[str, list[int]], dict[tuple[int, str], int]]
    ] = {}
    for anchor_id, code, kind, language, expected_seq, expected_sha in anchors:
        transcript_key = (code, kind, language)
        if transcript_key not in passage_maps:
            candidates = conn.execute(
                """SELECT p.id,p.seq,p.text
                   FROM passages AS p
                   JOIN transcripts AS t ON t.id=p.transcript_id
                   WHERE p.item_code=? AND t.kind=? AND t.language=?""",
                transcript_key,
            ).fetchall()
            by_hash: dict[str, list[int]] = {}
            by_seq_hash: dict[tuple[int, str], int] = {}
            for passage_id, seq, text in candidates:
                sha = text_sha256(text)
                by_hash.setdefault(sha, []).append(passage_id)
                by_seq_hash[(seq, sha)] = passage_id
            passage_maps[transcript_key] = (by_hash, by_seq_hash)
        by_hash, by_seq_hash = passage_maps[transcript_key]
        # Duplicate passage text occurs within transcripts; seq+hash resolves
        # those, hash-only remains the fallback when chunk boundaries shifted.
        seq_match = by_seq_hash.get((expected_seq, expected_sha))
        matches = [seq_match] if seq_match is not None else by_hash.get(expected_sha, [])
        if len(matches) == 1:
            conn.execute(
                "UPDATE passage_anchors SET passage_id=?,anchor_status='live' WHERE id=?",
                (matches[0], anchor_id),
            )
            relinked += 1
        else:
            conn.execute(
                "UPDATE passage_anchors SET passage_id=NULL,anchor_status='stale' WHERE id=?",
                (anchor_id,),
            )
            stale += 1
    return relinked, stale


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=CORPUS_DB_PATH,
                    help="corpus DB (default: corpus/krishnamurti-corpus.db)")
    ap.add_argument("--item", metavar="CODE")
    ap.add_argument("--all", action="store_true",
                    help="recheck live anchors as well as detached anchors")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.db.is_file():
        sys.exit(f"corpus database not found: {args.db}")
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("BEGIN")
        relinked, stale = reanchor(conn, args.item, args.all)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
        prefix = "dry run: " if args.dry_run else ""
        print(f"{prefix}relinked={relinked} stale={stale}")
    except sqlite3.Error as exc:
        conn.rollback()
        sys.exit(str(exc))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
