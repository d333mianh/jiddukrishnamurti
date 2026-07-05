#!/usr/bin/env python3
"""Report per-item and per-event L1/L2 corpus QA and speaker shares."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DB_PATH = ROOT / "corpus" / "krishnamurti-corpus.db"
CATALOG_DB_PATH = ROOT / "catalog" / "krishnamurti.db"
CATEGORIES = ("K", "Q", "ANN", "UNK")


def _readonly_uri(path: Path) -> str:
    return path.expanduser().resolve().as_uri() + "?mode=ro"


def _pct(value: float, total: float) -> float:
    return 100.0 * value / total if total else 0.0


def _table(headers: list[str], rows: list[list[object]]) -> str:
    rendered = [[str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in rendered:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(value))
    lines = ["  ".join(header.ljust(widths[i]) for i, header in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(
        "  ".join(value.ljust(widths[i]) for i, value in enumerate(row))
        for row in rendered
    )
    return "\n".join(lines)


def collect(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    base_rows = conn.execute(
        """SELECT t.id, t.item_code, COALESCE(i.event_type,t.event_type,'?'),
                  t.kind, t.language, t.segment_count, t.passage_count,
                  q.k_passage_count, q.status, COALESCE(q.failure_codes,'')
           FROM transcripts t
           LEFT JOIN catalog.items i ON i.code=t.item_code
           LEFT JOIN transcript_qa q ON q.transcript_id=t.id
           ORDER BY COALESCE(i.pdf_order,2147483647), t.item_code, t.kind"""
    ).fetchall()
    item_rows: list[dict] = []
    for row in base_rows:
        tid, code, event_type, kind, language, segs, passages, k_pass, qa, failures = row
        metric = {
            "transcript_id": tid,
            "item_code": code,
            "event_type": event_type,
            "kind": kind,
            "language": language,
            "segments": segs or 0,
            "passages": passages or 0,
            "k_passages": k_pass or 0,
            "qa_status": qa or "missing",
            "qa_failures": failures,
            "collapsed": int((k_pass or 0) == 0),
            "word_total": 0,
            "duration_total": 0.0,
        }
        for category in CATEGORIES:
            metric[f"word_{category.lower()}"] = 0
            metric[f"duration_{category.lower()}"] = 0.0
        for speaker, words, duration in conn.execute(
            """SELECT speaker_code, SUM(word_count),
                      SUM(CASE WHEN t_end > t_start THEN t_end-t_start ELSE 0 END)
               FROM segments WHERE transcript_id=? GROUP BY speaker_code""",
            (tid,),
        ):
            words = words or 0
            duration = duration or 0.0
            metric["word_total"] += words
            metric["duration_total"] += duration
            if speaker in CATEGORIES:
                metric[f"word_{speaker.lower()}"] += words
                metric[f"duration_{speaker.lower()}"] += duration
        for category in CATEGORIES:
            low = category.lower()
            metric[f"word_pct_{low}"] = _pct(
                metric[f"word_{low}"], metric["word_total"]
            )
            metric[f"duration_pct_{low}"] = _pct(
                metric[f"duration_{low}"], metric["duration_total"]
            )
        item_rows.append(metric)

    grouped: dict[str, dict] = {}
    for item in item_rows:
        event = item["event_type"]
        if event not in grouped:
            grouped[event] = {
                "event_type": event,
                "items": 0,
                "segments": 0,
                "passages": 0,
                "qa_failures": 0,
                "collapsed": 0,
                "word_total": 0,
                "duration_total": 0.0,
                **{f"word_{c.lower()}": 0 for c in CATEGORIES},
                **{f"duration_{c.lower()}": 0.0 for c in CATEGORIES},
            }
        event_row = grouped[event]
        event_row["items"] += 1
        event_row["segments"] += item["segments"]
        event_row["passages"] += item["passages"]
        event_row["qa_failures"] += int(item["qa_status"] == "warn")
        event_row["collapsed"] += item["collapsed"]
        event_row["word_total"] += item["word_total"]
        event_row["duration_total"] += item["duration_total"]
        for category in CATEGORIES:
            low = category.lower()
            event_row[f"word_{low}"] += item[f"word_{low}"]
            event_row[f"duration_{low}"] += item[f"duration_{low}"]
    event_rows = []
    for event_row in grouped.values():
        for category in CATEGORIES:
            low = category.lower()
            event_row[f"word_pct_{low}"] = _pct(
                event_row[f"word_{low}"], event_row["word_total"]
            )
            event_row[f"duration_pct_{low}"] = _pct(
                event_row[f"duration_{low}"], event_row["duration_total"]
            )
        event_rows.append(event_row)
    event_rows.sort(key=lambda row: row["event_type"])
    return item_rows, event_rows


def _share_cells(row: dict, prefix: str) -> list[str]:
    return [f"{row[f'{prefix}_pct_{category.lower()}']:.1f}" for category in CATEGORIES]


def print_report(item_rows: list[dict], event_rows: list[dict]) -> None:
    share_headers = ["K%", "Q%", "ANN%", "UNK%"]
    print("Shares use all segment speech as the denominator; named speakers are the remainder.")
    print("PER ITEM (word share, then duration share)")
    print(_table(
        ["ITEM", "EVT", "KIND", "SEG", "PASS", "KP", "QA", "COLL",
         *["W" + h for h in share_headers], *["D" + h for h in share_headers]],
        [[
            row["item_code"], row["event_type"], row["kind"], row["segments"],
            row["passages"], row["k_passages"], row["qa_status"], row["collapsed"],
            *_share_cells(row, "word"), *_share_cells(row, "duration"),
        ] for row in item_rows],
    ))
    print("\nPER EVENT TYPE (word share, then duration share)")
    print(_table(
        ["EVT", "ITEMS", "SEG", "PASS", "FAIL", "COLL",
         *["W" + h for h in share_headers], *["D" + h for h in share_headers]],
        [[
            row["event_type"], row["items"], row["segments"], row["passages"],
            row["qa_failures"], row["collapsed"], *_share_cells(row, "word"),
            *_share_cells(row, "duration"),
        ] for row in event_rows],
    ))
    failures = [row for row in item_rows if row["qa_status"] == "warn"]
    if failures:
        print("\nVALIDATION FAILURES")
        print(_table(
            ["ITEM", "EVT", "FAILURE"],
            [[row["item_code"], row["event_type"], row["qa_failures"]]
             for row in failures],
        ))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=CORPUS_DB_PATH)
    ap.add_argument("--catalog-db", type=Path, default=CATALOG_DB_PATH)
    ap.add_argument(
        "--csv", type=Path,
        help="write item CSV here and an adjacent '<stem>-events.csv'",
    )
    args = ap.parse_args()
    if not args.db.is_file():
        sys.exit(f"corpus database not found: {args.db}")
    if not args.catalog_db.is_file():
        sys.exit(f"catalog database not found: {args.catalog_db}")
    conn = sqlite3.connect(_readonly_uri(args.db), uri=True)
    conn.execute("ATTACH DATABASE ? AS catalog", (_readonly_uri(args.catalog_db),))
    item_rows, event_rows = collect(conn)
    print_report(item_rows, event_rows)
    if args.csv:
        write_csv(args.csv, item_rows)
        event_path = args.csv.with_name(args.csv.stem + "-events" + args.csv.suffix)
        write_csv(event_path, event_rows)
        print(f"\nCSV: {args.csv}")
        print(f"CSV: {event_path}")


if __name__ == "__main__":
    main()
