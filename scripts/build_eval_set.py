#!/usr/bin/env python3
"""Build a reproducible stratified K-passage evaluation set."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DB_PATH = ROOT / "corpus" / "krishnamurti-corpus.db"
CATALOG_DB_PATH = ROOT / "catalog" / "krishnamurti.db"
DEFAULT_SEED = 20260706

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concept_schema import ensure_concept_schema  # noqa: E402
from segment_schema import utc_now  # noqa: E402


FRAME_QUERY = """
SELECT p.id, p.item_code, t.kind, t.language, p.seq, p.text,
       p.speaker_code, p.t_start, p.t_end, p.timestamps_synthetic,
       p.attribution, t.parser_version, i.year, i.event_type, t.corpus_tier
FROM passages AS p
JOIN transcripts AS t ON t.id = p.transcript_id
JOIN catalog.items AS i ON i.code = p.item_code
WHERE p.speaker_code = 'K'
  AND t.corpus_tier IN ('A', 'B')
  AND t.kind = 'manual'
ORDER BY p.item_code, t.kind, t.language, p.seq, p.id
""".strip()


@dataclass(frozen=True)
class Candidate:
    passage_id: int
    item_code: str
    transcript_kind: str
    transcript_language: str
    passage_seq: int
    text: str
    speaker_code: str
    t_start: float
    t_end: float
    timestamps_synthetic: int
    attribution: str
    parser_version: str
    decade: str
    event_type: str
    corpus_tier: str

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def stratum_key(self) -> str:
        return (
            f"decade:{self.decade}|type:{self.event_type}|tier:{self.corpus_tier}"
            f"|synth:{self.timestamps_synthetic}"
        )

    @property
    def stratum_json(self) -> dict[str, object]:
        return {
            "stratum": self.stratum_key,
            "decade": self.decade,
            "event_type": self.event_type,
            "corpus_tier": self.corpus_tier,
            "timestamps_synthetic": self.timestamps_synthetic,
        }


def attach_catalog_readonly(conn: sqlite3.Connection, catalog_db: Path) -> None:
    catalog_db = catalog_db.expanduser().resolve()
    if not catalog_db.is_file():
        raise FileNotFoundError(f"catalog database not found: {catalog_db}")
    conn.execute("ATTACH DATABASE ? AS catalog", (catalog_db.as_uri() + "?mode=ro",))


def decade_for(year: int | None, item_code: str) -> str:
    if year is None:
        match = re.search(r"\d{2}", item_code)
        year = 1900 + int(match.group()) if match else None
    return f"{year // 10 * 10}s" if year is not None else "unknown"


def load_frame(conn: sqlite3.Connection) -> list[Candidate]:
    rows = conn.execute(FRAME_QUERY).fetchall()
    return [
        Candidate(
            passage_id=row[0], item_code=row[1], transcript_kind=row[2],
            transcript_language=row[3], passage_seq=row[4], text=row[5],
            speaker_code=row[6], t_start=row[7], t_end=row[8],
            timestamps_synthetic=int(row[9]), attribution=row[10],
            parser_version=row[11], decade=decade_for(row[12], row[1]),
            event_type=row[13] or "unknown", corpus_tier=row[14],
        )
        for row in rows
    ]


def allocate(strata: dict[str, list[Candidate]], size: int) -> dict[str, int]:
    if size <= 0:
        raise ValueError("--size must be positive")
    frame_size = sum(len(rows) for rows in strata.values())
    size = min(size, frame_size)
    if not strata:
        return {}
    if size < len(strata):
        raise ValueError(
            f"--size {size} is smaller than the {len(strata)} nonempty strata; "
            "increase --size to preserve stratum coverage"
        )

    allocation = {key: 1 for key in strata}
    remaining = size - len(strata)
    capacities = {key: len(rows) - 1 for key, rows in strata.items()}
    while remaining:
        total_capacity = sum(capacities.values())
        if total_capacity == 0:
            break
        quotas = {
            key: remaining * capacity / total_capacity
            for key, capacity in capacities.items()
        }
        floors = {
            key: min(capacities[key], int(quota)) for key, quota in quotas.items()
        }
        assigned = sum(floors.values())
        for key, count in floors.items():
            allocation[key] += count
            capacities[key] -= count
        remaining -= assigned
        if remaining:
            ranked = sorted(
                (key for key in strata if capacities[key] > 0),
                key=lambda key: (-(quotas[key] - int(quotas[key])), key),
            )
            for key in ranked[:remaining]:
                allocation[key] += 1
                capacities[key] -= 1
            remaining -= min(remaining, len(ranked))
    return allocation


def sample_frame(
    frame: list[Candidate], size: int, seed: int
) -> tuple[list[tuple[Candidate, float]], dict[str, dict[str, float | int]]]:
    strata: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in frame:
        strata[candidate.stratum_key].append(candidate)
    allocation = allocate(dict(strata), size)
    rng = random.Random(seed)
    sampled: list[tuple[Candidate, float]] = []
    summary: dict[str, dict[str, float | int]] = {}
    for key in sorted(strata):
        rows = strata[key]
        count = allocation[key]
        weight = len(rows) / count
        for candidate in rng.sample(rows, count):
            sampled.append((candidate, weight))
        summary[key] = {
            "frame_size": len(rows), "sample_size": count, "sample_weight": weight
        }
    sampled.sort(key=lambda value: (
        value[0].item_code, value[0].transcript_kind,
        value[0].transcript_language, value[0].passage_seq,
        value[0].text_sha256,
    ))
    return sampled, summary


def upsert_anchor(conn: sqlite3.Connection, candidate: Candidate, now: str) -> int:
    conn.execute(
        """INSERT INTO passage_anchors(
               passage_id,item_code,transcript_kind,transcript_language,
               passage_seq,text_sha256,parser_version,text,speaker_code,
               t_start,t_end,timestamps_synthetic,attribution,anchor_status,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'live',?)
           ON CONFLICT(item_code,transcript_kind,transcript_language,passage_seq,text_sha256)
           DO UPDATE SET passage_id=excluded.passage_id,
                         parser_version=excluded.parser_version,
                         text=excluded.text,
                         speaker_code=excluded.speaker_code,
                         t_start=excluded.t_start,
                         t_end=excluded.t_end,
                         timestamps_synthetic=excluded.timestamps_synthetic,
                         attribution=excluded.attribution,
                         anchor_status='live'""",
        (
            candidate.passage_id, candidate.item_code, candidate.transcript_kind,
            candidate.transcript_language, candidate.passage_seq,
            candidate.text_sha256, candidate.parser_version, candidate.text,
            candidate.speaker_code, candidate.t_start, candidate.t_end,
            candidate.timestamps_synthetic, candidate.attribution, now,
        ),
    )
    row = conn.execute(
        """SELECT id FROM passage_anchors
           WHERE item_code=? AND transcript_kind=? AND transcript_language=?
             AND passage_seq=? AND text_sha256=?""",
        (
            candidate.item_code, candidate.transcript_kind,
            candidate.transcript_language, candidate.passage_seq,
            candidate.text_sha256,
        ),
    ).fetchone()
    assert row is not None
    return int(row[0])


def export_rows(path: Path, sampled: list[tuple[Candidate, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candidate, weight in sampled:
            row = {
                "item_code": candidate.item_code,
                "transcript_kind": candidate.transcript_kind,
                "transcript_language": candidate.transcript_language,
                "passage_seq": candidate.passage_seq,
                "text_sha256": candidate.text_sha256,
                "stratum": candidate.stratum_key,
                "sample_weight": weight,
            }
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="unique eval set name")
    ap.add_argument("--size", type=int, default=500)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--db", type=Path, default=CORPUS_DB_PATH,
                    help="corpus DB (default: corpus/krishnamurti-corpus.db)")
    ap.add_argument("--catalog", type=Path, default=CATALOG_DB_PATH,
                    help="catalog DB attached read-only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--export", type=Path,
                    help="JSONL path (default: concepts/eval/<name>.jsonl)")
    args = ap.parse_args()
    export_path = args.export or ROOT / "concepts" / "eval" / f"{args.name}.jsonl"

    if not args.db.is_file():
        sys.exit(f"corpus database not found: {args.db}")
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if not args.dry_run:
            ensure_concept_schema(conn)
        attach_catalog_readonly(conn, args.catalog)
        if not args.dry_run and conn.execute(
            "SELECT 1 FROM eval_sets WHERE name=?", (args.name,)
        ).fetchone():
            sys.exit(f"eval set already exists: {args.name}")
        frame = load_frame(conn)
        if not frame:
            sys.exit("eligible passage frame is empty")
        sampled, strata_summary = sample_frame(frame, args.size, args.seed)
        sampling = {
            "seed": args.seed,
            "frame_query": FRAME_QUERY,
            "frame_size": len(frame),
            "requested_size": args.size,
            "sample_size": len(sampled),
            "dimensions": ["decade", "event_type", "corpus_tier", "timestamps_synthetic"],
            "strata": strata_summary,
        }
        if args.dry_run:
            conn.rollback()
            print(
                f"dry run: frame={len(frame)} sampled={len(sampled)} "
                f"strata={len(strata_summary)}; no database or export writes"
            )
            return

        now = utc_now()
        cursor = conn.execute(
            "INSERT INTO eval_sets(name,description,sampling_json,created_at) VALUES(?,?,?,?)",
            (
                args.name,
                "Reproducible stratified sample of manual K passages; sampling details in sampling_json.",
                json.dumps(sampling, sort_keys=True),
                now,
            ),
        )
        eval_set_id = int(cursor.lastrowid)
        for candidate, weight in sampled:
            anchor_id = upsert_anchor(conn, candidate, now)
            conn.execute(
                """INSERT INTO eval_set_passages(
                       eval_set_id,anchor_id,stratum_json,sample_weight
                   ) VALUES(?,?,?,?)""",
                (
                    eval_set_id, anchor_id,
                    json.dumps(candidate.stratum_json, sort_keys=True), weight,
                ),
            )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"foreign key violations: {violations}")
        conn.commit()
        export_rows(export_path, sampled)
        print(
            f"created eval set {args.name!r}: frame={len(frame)} "
            f"sampled={len(sampled)} strata={len(strata_summary)} export={export_path}"
        )
    except (sqlite3.Error, OSError, ValueError, RuntimeError) as exc:
        conn.rollback()
        sys.exit(str(exc))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
