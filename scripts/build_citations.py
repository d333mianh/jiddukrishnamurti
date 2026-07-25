#!/usr/bin/env python3
"""Resolve the curated citation list in `concepts/citations.jsonl` against the corpus.

`concepts/citations.jsonl` is hand-curated data, the L4 counterpart to
`concepts/concepts.jsonl`: a human reads the candidates from
`retrieve_concept.py`, keeps the passages that actually carry the root's
argument, and records the choice as one line per citation. This script fills in
everything the choice implies — title, year, quoted text, the
`youtu.be/<id>?t=<seconds>` link — so `build_concept_vault.py` can render a
concept note without the (gitignored) corpus DB present.

Citations are keyed on **`(item_code, t_start)`**, not `passages.id`. Passage
ids are reassigned on every re-ingest, so an id-keyed citation would silently
drift onto a different passage; an item code plus an offset into that recording
is exactly what the published citation itself claims, and drifts only if the
transcript does.

Two modes:

- `--sync` re-resolves every row and rewrites the file. Run it after any
  re-ingest, and after adding a citation by hand (a new line needs only
  `slug`, `theme`, `seq`, `item_code`, `t_start`).
- `--verify` resolves without writing and exits non-zero if any citation no
  longer resolves or if the stored text no longer matches the corpus. This is
  the gate that catches a re-ingest having moved the ground under a published
  quote.

Passages whose timestamps are synthetic (word-interpolated inside a cue) are
refused unless `--allow-synthetic`: a citation asserts that the offset is a real
cue boundary in the published recording, and an interpolated one is a guess.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DB = ROOT / "corpus" / "krishnamurti-corpus.db"
CATALOG_DB = ROOT / "catalog" / "krishnamurti.db"
CITATIONS = ROOT / "concepts" / "citations.jsonl"

# How far the recorded offset may sit from the passage's true start. Curated
# offsets are copied from retrieve_concept.py output, which truncates to whole
# seconds, so a sub-second gap is expected; anything larger means the transcript
# changed and the citation needs re-reading, not silent re-pointing.
TOLERANCE_S = 2.0

# The curated key, and the order fields are written back in.
KEY_FIELDS = ("slug", "theme", "seq", "item_code", "t_start")
RESOLVED_FIELDS = (
    "title", "year", "event_type", "tier", "t_end", "timecode",
    "video_id", "url", "word_count", "text",
)

SELECT_PASSAGE = """
SELECT p.t_start, p.t_end, p.word_count, p.text, p.speaker_code,
       p.timestamps_synthetic,
       t.corpus_tier, i.title, i.year, i.event_type,
       (SELECT l.video_id FROM catalog.item_links l
         WHERE l.item_id = i.id AND l.video_id IS NOT NULL
         ORDER BY l.link_kind = 'primary' DESC LIMIT 1) AS video_id
FROM passages AS p
JOIN transcripts AS t ON t.id = p.transcript_id
JOIN catalog.items AS i ON i.code = p.item_code
WHERE p.item_code = ?
"""

# Prefer K, then proximity. Curated offsets are truncated to whole seconds, and
# in a dialogue a one-word interjection ("Yes?") often ends where K begins — so
# the *nearest* passage to the truncated offset can be that interjection rather
# than the quote being cited. Distance alone picks the wrong row; K-first fixes
# it without widening the tolerance.
IN_WINDOW = (SELECT_PASSAGE + "  AND abs(p.t_start - ?) <= ?\n"
             "ORDER BY p.speaker_code <> 'K', abs(p.t_start - ?)\nLIMIT 1\n")
NEAREST = SELECT_PASSAGE + "ORDER BY abs(p.t_start - ?)\nLIMIT 1\n"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{CORPUS_DB}?mode=ro", uri=True)
    conn.execute("ATTACH DATABASE ? AS catalog", (f"file:{CATALOG_DB}?mode=ro",))
    conn.row_factory = sqlite3.Row
    return conn


def load(path: Path = CITATIONS) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"error: {path}:{n}: {exc}") from exc
    return rows


def by_concept(rows: list[dict]) -> dict[str, list[dict]]:
    """Citations grouped by slug, each list in curated `seq` order."""
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["slug"], []).append(row)
    for cites in out.values():
        cites.sort(key=lambda c: c["seq"])
    return out


def timecode(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def resolve(conn: sqlite3.Connection, cite: dict,
            allow_synthetic: bool) -> tuple[dict | None, str | None]:
    """Return (resolved citation, error). Exactly one is None."""
    where = f"{cite['slug']} #{cite['seq']} ({cite['item_code']} @ {cite['t_start']})"
    code, t = cite["item_code"], cite["t_start"]
    row = conn.execute(IN_WINDOW, (code, t, TOLERANCE_S, t)).fetchone()
    if row is None:
        nearest = conn.execute(NEAREST, (code, t)).fetchone()
        if nearest is None:
            return None, f"{where}: no passages ingested for item {code}"
        drift = abs(nearest["t_start"] - t)
        return None, (f"{where}: nearest passage starts at {nearest['t_start']:.1f}s "
                      f"({drift:.1f}s away) — transcript changed, re-read it")
    if row["speaker_code"] != "K":
        return None, f"{where}: passage is attributed to {row['speaker_code']}, not K"
    if row["timestamps_synthetic"] and not allow_synthetic:
        return None, (f"{where}: timestamps are synthetic; the offset is "
                      f"interpolated, not a cue boundary")
    if not row["video_id"]:
        return None, f"{where}: no video link for {cite['item_code']}"

    resolved = {field: cite[field] for field in KEY_FIELDS}
    resolved["t_start"] = row["t_start"]
    resolved.update({
        "title": row["title"],
        "year": row["year"],
        "event_type": row["event_type"],
        "tier": row["corpus_tier"],
        "t_end": row["t_end"],
        "timecode": timecode(row["t_start"]),
        "video_id": row["video_id"],
        "url": f"https://youtu.be/{row['video_id']}?t={int(row['t_start'])}",
        "text": row["text"],
        "word_count": row["word_count"],
    })
    return resolved, None


def dump(rows: list[dict], path: Path) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sync", action="store_true",
                      help="re-resolve every citation and rewrite the file")
    mode.add_argument("--verify", action="store_true",
                      help="check every citation still resolves; write nothing")
    ap.add_argument("--slug", help="limit to one concept")
    ap.add_argument("--allow-synthetic", action="store_true",
                    help="permit passages with interpolated timestamps")
    args = ap.parse_args()

    if not CORPUS_DB.exists():
        print(f"error: {CORPUS_DB} not found", file=sys.stderr)
        return 1

    rows = load()
    if not rows:
        print(f"no citations in {CITATIONS}")
        return 0

    conn = connect()
    try:
        out: list[dict] = []
        errors: list[str] = []
        drifted = 0
        for cite in rows:
            if args.slug and cite["slug"] != args.slug:
                out.append(cite)
                continue
            resolved, error = resolve(conn, cite, args.allow_synthetic)
            if error:
                errors.append(error)
                out.append(cite)
                continue
            if args.verify and cite.get("text") and cite["text"] != resolved["text"]:
                errors.append(
                    f"{cite['slug']} #{cite['seq']} ({cite['item_code']}): stored "
                    f"quote no longer matches the corpus")
                drifted += 1
            out.append(resolved)
    finally:
        conn.close()

    for error in errors:
        print(f"error: {error}", file=sys.stderr)

    resolved_count = sum(1 for r in out if "url" in r)
    if args.sync:
        dump(out, CITATIONS)
        print(f"synced {resolved_count}/{len(rows)} citations → {CITATIONS}")
    else:
        print(f"verified {resolved_count}/{len(rows)} citations"
              + (f" ({drifted} with drifted text)" if drifted else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
