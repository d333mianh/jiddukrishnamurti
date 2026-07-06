#!/usr/bin/env python3
"""Build a reproducible stratified K-passage evaluation set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import tempfile
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


def metadata_row(
    name: str, seed: int, created_at: str, description: str | None,
    params: dict[str, object],
) -> dict[str, object]:
    return {
        "kind": "eval_set",
        "format": 1,
        "name": name,
        "seed": seed,
        "created_at": created_at,
        "description": description,
        "params": params,
    }


def sampled_export_rows(
    sampled: list[tuple[Candidate, float]],
) -> list[dict[str, object]]:
    rows = []
    for candidate, weight in sampled:
        rows.append({
            "item_code": candidate.item_code,
            "transcript_kind": candidate.transcript_kind,
            "transcript_language": candidate.transcript_language,
            "passage_seq": candidate.passage_seq,
            "text_sha256": candidate.text_sha256,
            "stratum": candidate.stratum_key,
            "sample_weight": weight,
        })
    return rows


def export_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def stratum_from_export(row: dict[str, object]) -> dict[str, object] | None:
    exported = row.get("stratum_json")
    if isinstance(exported, dict):
        return exported
    key = row.get("stratum")
    if not isinstance(key, str):
        return None
    values: dict[str, object] = {"stratum": key}
    names = {
        "decade": "decade", "type": "event_type", "tier": "corpus_tier",
        "synth": "timestamps_synthetic",
    }
    for part in key.split("|"):
        source, separator, value = part.partition(":")
        if separator and source in names:
            values[names[source]] = int(value) if source == "synth" else value
    return values


def load_export(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    with path.open(encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle if line.strip()]
    if not lines or not isinstance(lines[0], dict):
        raise ValueError(f"empty or invalid eval-set export: {path}")
    metadata = lines[0]
    if metadata.get("kind") != "eval_set" or metadata.get("format") != 1:
        raise ValueError("eval-set export must begin with kind='eval_set', format=1 metadata")
    required = ("name", "seed", "created_at", "params")
    missing = [key for key in required if key not in metadata]
    if missing:
        raise ValueError(f"eval-set metadata missing: {', '.join(missing)}")
    rows = lines[1:]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("eval-set anchor lines must be JSON objects")
    return metadata, rows


def anchor_key(row: dict[str, object]) -> tuple[object, ...]:
    keys = (
        "item_code", "transcript_kind", "transcript_language", "passage_seq",
        "text_sha256",
    )
    missing = [key for key in keys if key not in row]
    if missing:
        raise ValueError(f"eval-set anchor missing: {', '.join(missing)}")
    return tuple(row[key] for key in keys)


def find_live_snapshot(
    conn: sqlite3.Connection, row: dict[str, object]
) -> tuple[object, ...] | None:
    candidates = conn.execute(
        """SELECT p.id,t.parser_version,p.text,p.speaker_code,p.t_start,p.t_end,
                  p.timestamps_synthetic,p.attribution
           FROM passages AS p
           JOIN transcripts AS t ON t.id=p.transcript_id
           WHERE p.item_code=? AND t.kind=? AND t.language=? AND p.seq=?""",
        anchor_key(row)[:4],
    ).fetchall()
    matches = [candidate for candidate in candidates
               if hashlib.sha256(candidate[2].encode("utf-8")).hexdigest()
               == row["text_sha256"]]
    return matches[0] if len(matches) == 1 else None


def import_anchor(
    conn: sqlite3.Connection, row: dict[str, object], created_at: str
) -> tuple[int, bool]:
    key = anchor_key(row)
    snapshot = find_live_snapshot(conn, row)
    existing = conn.execute(
        """SELECT id FROM passage_anchors
           WHERE item_code=? AND transcript_kind=? AND transcript_language=?
             AND passage_seq=? AND text_sha256=?""",
        key,
    ).fetchone()
    if snapshot is not None:
        values = (
            snapshot[0], *key, snapshot[1], snapshot[2], snapshot[3], snapshot[4],
            snapshot[5], snapshot[6], snapshot[7], "live", created_at,
        )
        conn.execute(
            """INSERT INTO passage_anchors(
                   passage_id,item_code,transcript_kind,transcript_language,
                   passage_seq,text_sha256,parser_version,text,speaker_code,t_start,
                   t_end,timestamps_synthetic,attribution,anchor_status,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(item_code,transcript_kind,transcript_language,passage_seq,text_sha256)
               DO UPDATE SET passage_id=excluded.passage_id,
                             parser_version=excluded.parser_version,text=excluded.text,
                             speaker_code=excluded.speaker_code,t_start=excluded.t_start,
                             t_end=excluded.t_end,
                             timestamps_synthetic=excluded.timestamps_synthetic,
                             attribution=excluded.attribution,anchor_status='live'""",
            values,
        )
    elif existing is None:
        # The tracked format intentionally omits transcript text. These are the
        # strongest schema-valid placeholders available until re-ingest restores it.
        conn.execute(
            """INSERT INTO passage_anchors(
                   passage_id,item_code,transcript_kind,transcript_language,
                   passage_seq,text_sha256,parser_version,text,speaker_code,t_start,
                   t_end,timestamps_synthetic,attribution,anchor_status,created_at
               ) VALUES(NULL,?,?,?,?,?,'unavailable','','UNK',0,0,1,'inherit','stale',?)""",
            (*key, created_at),
        )
    else:
        conn.execute(
            "UPDATE passage_anchors SET passage_id=NULL,anchor_status='stale' WHERE id=?",
            (existing[0],),
        )
    anchor = conn.execute(
        """SELECT id FROM passage_anchors
           WHERE item_code=? AND transcript_kind=? AND transcript_language=?
             AND passage_seq=? AND text_sha256=?""",
        key,
    ).fetchone()
    assert anchor is not None
    return int(anchor[0]), snapshot is None


def export_set(conn: sqlite3.Connection, name: str) -> list[dict[str, object]]:
    eval_set = conn.execute(
        "SELECT id,description,sampling_json,created_at FROM eval_sets WHERE name=?",
        (name,),
    ).fetchone()
    if eval_set is None:
        raise ValueError(f"eval set not found: {name}")
    params = json.loads(eval_set[2]) if eval_set[2] else {}
    seed = int(params.get("seed", DEFAULT_SEED))
    rows = [metadata_row(name, seed, eval_set[3], eval_set[1], params)]
    members = conn.execute(
        """SELECT a.item_code,a.transcript_kind,a.transcript_language,a.passage_seq,
                  a.text_sha256,ep.stratum_json,ep.sample_weight
           FROM eval_set_passages AS ep
           JOIN passage_anchors AS a ON a.id=ep.anchor_id
           WHERE ep.eval_set_id=?
           ORDER BY a.item_code,a.transcript_kind,a.transcript_language,
                    a.passage_seq,a.text_sha256""",
        (eval_set[0],),
    ).fetchall()
    for member in members:
        stratum_json = json.loads(member[5]) if member[5] else None
        rows.append({
            "item_code": member[0], "transcript_kind": member[1],
            "transcript_language": member[2], "passage_seq": member[3],
            "text_sha256": member[4],
            "stratum": stratum_json.get("stratum") if stratum_json else None,
            "sample_weight": member[6],
        })
    return rows


def verify_existing_set(
    conn: sqlite3.Connection, eval_set_id: int, rows: list[dict[str, object]]
) -> None:
    existing = conn.execute(
        """SELECT a.item_code,a.transcript_kind,a.transcript_language,a.passage_seq,
                  a.text_sha256,ep.stratum_json,ep.sample_weight
           FROM eval_set_passages AS ep
           JOIN passage_anchors AS a ON a.id=ep.anchor_id
           WHERE ep.eval_set_id=?""",
        (eval_set_id,),
    ).fetchall()
    if len(existing) != len(rows):
        raise ValueError(
            f"existing eval set row count differs: {len(existing)} != {len(rows)}"
        )
    actual = {
        tuple(member[:5]): (json.loads(member[5]) if member[5] else None, member[6])
        for member in existing
    }
    expected = {
        anchor_key(row): (stratum_from_export(row), float(row.get("sample_weight", 1.0)))
        for row in rows
    }
    if actual != expected:
        raise ValueError("existing eval set membership, strata, or weights differ")


def import_set(
    conn: sqlite3.Connection, metadata: dict[str, object],
    rows: list[dict[str, object]],
) -> tuple[int, int, bool]:
    name = str(metadata["name"])
    existing = conn.execute("SELECT id FROM eval_sets WHERE name=?", (name,)).fetchone()
    if existing is not None:
        verify_existing_set(conn, int(existing[0]), rows)
        return len(rows), 0, True
    if len({anchor_key(row) for row in rows}) != len(rows):
        raise ValueError("eval-set export contains duplicate anchors")
    params = metadata["params"]
    if not isinstance(params, dict):
        raise ValueError("eval-set metadata params must be an object")
    cursor = conn.execute(
        "INSERT INTO eval_sets(name,description,sampling_json,created_at) VALUES(?,?,?,?)",
        (
            name, metadata.get("description"), json.dumps(params, sort_keys=True),
            str(metadata["created_at"]),
        ),
    )
    eval_set_id = int(cursor.lastrowid)
    stale = 0
    for row in rows:
        anchor_id, is_stale = import_anchor(conn, row, str(metadata["created_at"]))
        stale += int(is_stale)
        conn.execute(
            """INSERT INTO eval_set_passages(
                   eval_set_id,anchor_id,stratum_json,sample_weight
               ) VALUES(?,?,?,?)""",
            (
                eval_set_id, anchor_id,
                json.dumps(stratum_from_export(row), sort_keys=True)
                if stratum_from_export(row) is not None else None,
                float(row.get("sample_weight", 1.0)),
            ),
        )
    return len(rows), stale, False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="unique eval set name (build mode)")
    ap.add_argument("--size", type=int, default=500)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--db", type=Path, default=CORPUS_DB_PATH,
                    help="corpus DB (default: corpus/krishnamurti-corpus.db)")
    ap.add_argument("--catalog", type=Path, default=CATALOG_DB_PATH,
                    help="catalog DB attached read-only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--export", type=Path,
                    help="JSONL path (default: concepts/eval/<name>.jsonl)")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--import", dest="import_path", type=Path, metavar="PATH",
                       help="restore an eval set from format-1 JSONL")
    modes.add_argument("--export-only", metavar="NAME",
                       help="regenerate an eval-set JSONL from the database")
    args = ap.parse_args()

    if not args.import_path and not args.export_only and not args.name:
        ap.error("--name is required in build mode")
    if args.import_path and args.name:
        ap.error("--name cannot be combined with --import")
    selected_name = args.export_only or args.name
    export_path = args.export or (
        ROOT / "concepts" / "eval" / f"{selected_name}.jsonl"
        if selected_name else None
    )

    if not args.db.is_file():
        sys.exit(f"corpus database not found: {args.db}")
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if args.import_path:
            if args.dry_run:
                raise ValueError("--dry-run is not supported with --import")
            ensure_concept_schema(conn)
            conn.commit()
            metadata, rows = load_export(args.import_path)
            conn.execute("BEGIN")
            count, stale, no_op = import_set(conn, metadata, rows)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"foreign key violations: {violations}")
            conn.commit()
            action = "verified existing" if no_op else "imported"
            warning = f" warnings_stale={stale}" if stale else ""
            print(f"{action} eval set {metadata['name']!r}: rows={count}{warning}")
            return

        if not args.dry_run:
            ensure_concept_schema(conn)
            conn.commit()
        if args.export_only:
            assert export_path is not None
            rows = export_set(conn, args.export_only)
            export_rows(export_path, rows)
            print(f"exported eval set {args.export_only!r}: rows={len(rows) - 1} export={export_path}")
            return

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
        description = (
            "Reproducible stratified sample of manual K passages; "
            "sampling details in sampling_json."
        )
        conn.execute("BEGIN")
        cursor = conn.execute(
            "INSERT INTO eval_sets(name,description,sampling_json,created_at) VALUES(?,?,?,?)",
            (
                args.name,
                description,
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
        assert export_path is not None
        export = [metadata_row(args.name, args.seed, now, description, sampling)]
        export.extend(sampled_export_rows(sampled))
        export_rows(export_path, export)
        conn.commit()
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
