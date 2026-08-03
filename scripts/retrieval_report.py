#!/usr/bin/env python3
"""Measure retrieval against the curated citations — the only gold set there is.

Every change to how `retrieve_concept.py` builds its query is a bet that the
candidates a curator reads get better. Nothing measured that bet until now, and
the cost of not measuring it was concrete: converting multi-word aliases into
FTS5 phrase queries looks like an obvious improvement and silently drops 15 of
`observer-observed`'s 30 curated passages. The 83 passages already judged
citable are the closest thing to ground truth this project has — a human read
each one and kept it — so the question this script answers is:

    if the curator ran retrieval today, would the passages they chose last time
    still be in front of them?

It imports `retrieve_concept` rather than reimplementing it. A copy of the query
builder would drift from the real one and quietly measure the wrong thing, which
is the failure mode that put 111 VTTs on one filename.

A miss is attributed rather than merely counted, because the four causes want
different fixes:

  vocabulary  the passage does not match the query at all. The registry's name
              and aliases miss the words K actually used — the alias-coverage
              defect, and the only category that indicts the registry itself.
  rank        it matches but falls outside --limit. Ranking, or a query diluted
              by terms that match everything.
  per-item    it ranks inside --limit but the --per-item cap dropped it, because
              the same recording already contributed its quota.
  min-words   shorter than --min-words, so it never enters the candidate set.

Exit code is non-zero under --check when any citation is unreachable, which
makes this usable as a gate before a query change lands.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_citations as bc  # noqa: E402
import retrieve_concept as rc  # noqa: E402

# The CLI's own defaults. Retrieval is measured as it is actually run, not under
# settings chosen to make the numbers look better.
DEFAULT_LIMIT = 300
DEFAULT_PER_ITEM = 2
DEFAULT_MIN_WORDS = 60

MATCHES_SQL = """
SELECT p.word_count
FROM passages_fts
JOIN passages AS p ON p.id = passages_fts.rowid
WHERE passages_fts MATCH ?
  AND p.item_code = ?
  AND abs(p.t_start - ?) < 1.0
LIMIT 1
"""


def key(item_code: str, t_start: float) -> tuple[str, int]:
    """Citations are keyed on `(item_code, t_start)`; passage ids are reassigned
    on every re-ingest. Second granularity is enough — two passages of the same
    recording cannot begin within the same second."""
    return (item_code, int(t_start))


def ranks(rows: list[dict]) -> dict[tuple[str, int], int]:
    return {key(r["item_code"], r["t_start"]): i + 1 for i, r in enumerate(rows)}


def attribute(conn: sqlite3.Connection, match: str, cite: dict,
              in_uncapped: bool, min_words: int) -> str:
    """Why is this citation not in front of the curator?"""
    if cite.get("word_count", 0) < min_words:
        return "min-words"
    if in_uncapped:
        return "per-item"
    row = conn.execute(MATCHES_SQL, (match, cite["item_code"],
                                     cite["t_start"])).fetchone()
    return "rank" if row else "vocabulary"


def measure(conn: sqlite3.Connection, slug: str, cites: list[dict],
            limit: int, per_item: int, min_words: int) -> dict:
    concept = rc.load_concept(slug)
    terms = rc.fts_terms(concept, [])
    match = rc.build_query(terms)

    # What the curator actually sees, and the same ranking without the per-item
    # cap — the difference is exactly what the cap costs.
    capped = ranks(rc.retrieve(conn, match, limit, per_item, min_words))
    uncapped = ranks(rc.retrieve(conn, match, limit, 10 ** 9, min_words))

    found, missing = [], []
    for cite in cites:
        k = key(cite["item_code"], cite["t_start"])
        if k in capped:
            found.append({"seq": cite["seq"], "rank": capped[k],
                          "item_code": cite["item_code"]})
        else:
            missing.append({
                "seq": cite["seq"], "theme": cite["theme"],
                "item_code": cite["item_code"], "t_start": cite["t_start"],
                "reason": attribute(conn, match, cite, k in uncapped, min_words),
            })

    worst = max((f["rank"] for f in found), default=0)
    return {
        "slug": slug,
        "terms": terms,
        "cited": len(cites),
        "found": len(found),
        "worst_rank": worst,
        # How close the deepest keeper sits to falling out of the candidate set.
        "headroom": limit - worst if found else 0,
        "missing": missing,
    }


def as_text(results: list[dict], limit: int) -> str:
    out = [f"{'root':22} {'found':>11} {'worst':>6} {'headroom':>9}  terms",
           "-" * 78]
    for r in results:
        pct = 100 * r["found"] // r["cited"] if r["cited"] else 0
        out.append(f"{r['slug']:22} {r['found']:>4}/{r['cited']:<3} ({pct:>3}%) "
                   f"{r['worst_rank']:>6} {r['headroom']:>9}  {len(r['terms'])} terms")
    cited = sum(r["cited"] for r in results)
    found = sum(r["found"] for r in results)
    out.append("-" * 78)
    out.append(f"{'total':22} {found:>4}/{cited:<3} "
               f"({100 * found // cited if cited else 0:>3}%)")

    misses = [(r["slug"], m) for r in results for m in r["missing"]]
    if misses:
        out.append(f"\n{len(misses)} unreachable at --limit {limit}:")
        for slug, m in misses:
            out.append(f"  [{m['reason']:>10}] {slug} #{m['seq']} "
                       f"{m['item_code']}@{int(m['t_start'])} — {m['theme']}")
    else:
        out.append(f"\nEvery curated passage is reachable at --limit {limit}.")

    tight = [r for r in results if r["found"] and r["headroom"] < limit // 10]
    if tight:
        out.append("\nThin headroom — a keeper sits near the cutoff, so a query "
                   "change could drop it:")
        for r in tight:
            out.append(f"  {r['slug']}: worst keeper at rank {r['worst_rank']} "
                       f"of {limit}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", help="measure one root instead of every cited one")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--per-item", type=int, default=DEFAULT_PER_ITEM)
    ap.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any curated passage is unreachable")
    args = ap.parse_args()

    if not rc.CORPUS_DB.exists():
        print(f"error: {rc.CORPUS_DB} not found — see corpus/README.md",
              file=sys.stderr)
        return 1

    by_slug = bc.by_concept(bc.load())
    if args.slug:
        if args.slug not in by_slug:
            print(f"error: no citations for {args.slug!r}", file=sys.stderr)
            return 1
        by_slug = {args.slug: by_slug[args.slug]}

    conn = rc.connect()
    try:
        results = [measure(conn, slug, cites, args.limit, args.per_item,
                           args.min_words)
                   for slug, cites in sorted(by_slug.items())]
    finally:
        conn.close()

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(as_text(results, args.limit))

    unreachable = sum(len(r["missing"]) for r in results)
    if args.check and unreachable:
        print(f"\nFAIL: {unreachable} curated passage(s) unreachable",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
