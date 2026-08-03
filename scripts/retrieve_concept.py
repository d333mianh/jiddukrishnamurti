#!/usr/bin/env python3
"""Retrieve citation-ready candidate passages for one concept root.

This is the retrieval half of the retrieval-first L3 path. The original plan
classified all ~80k K-passages against all 36 roots before any note could be
written — up to 2.9M judgments, gating every note on the last one. But a note
on `fear` needs the best ~30 passages, not all 3,623 that mention it, and the
registry already carries the lexicon (`name` + `aliases`) that finds them. So:
retrieve a few hundred candidates per concept, judge only those, write the
note. Exhaustive tagging becomes an optional enrichment rather than a
prerequisite, and concept #1 ships without waiting for concept #36.

Ranking is BM25 over `passages_fts` (K-only, tiers A/B). Two filters do most of
the quality work:

- `--per-item` caps how many passages any single talk contributes, so one
  fear-heavy series cannot crowd out thirty years of the archive.
- `--min-words` drops fragments too short to stand as a citation.

Query terms come from the concept's own registry entry — `name` plus `aliases`,
each expanded to an FTS prefix match so "fear" also catches fears/fearful.
`--terms` adds hand-picked terms (K's vocabulary shifts across decades, and the
registry's `period_note` fields exist precisely because of that).

Every row carries a `youtu.be/<id>?t=<seconds>` citation built from
`item_links.video_id` and the passage's own `t_start`, so output is directly
quotable into an L4 note. Passages with synthetic (word-interpolated)
timestamps are flagged, not silently cited.

Output is JSON (default, for downstream tooling) or Markdown (`--format md`,
for reading and judging by hand).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DB = ROOT / "corpus" / "krishnamurti-corpus.db"
CATALOG_DB = ROOT / "catalog" / "krishnamurti.db"
REGISTRY = ROOT / "concepts" / "concepts.jsonl"


def load_concept(slug: str) -> dict:
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("slug") == slug:
            return entry
    raise SystemExit(f"error: no concept with slug {slug!r} in {REGISTRY}")


# Function words that reach the query only by being split out of a multi-word
# name or alias. Measured against the corpus on 2026-08-03: `the` matches 60% of
# all K-passages, `you` 55%, `and` 42%, `what` 37%, `not` 35%, `are` 33%. An OR
# term matching a third of everything adds no ranking signal and inflates the
# candidate pool by an order of magnitude — `beauty` returned 30,774 candidates
# on the strength of `the` alone, against 2,066 for the words that mean beauty.
#
# Frequency is not the test, though, which is why this is a list and not a
# threshold: `right` matches 21% of passages and `mind` 10%, and both
# discriminate. These are closed-class function words, and that is what makes
# dropping them safe.
STOPWORDS = frozenset({
    "and", "are", "from", "its", "not", "only", "the", "what", "will",
    "without", "you",
})


def fts_terms(concept: dict, extra: list[str]) -> list[str]:
    """Registry name + aliases + any --terms, as FTS prefix matches.

    Multi-word names ("Observer & Observed") are split on non-word characters;
    fragments shorter than 3 characters are dropped, since a bare `is*` would
    match most of the corpus, and so are the function words in STOPWORDS.

    A form the registry states on its own is never dropped, whatever its
    frequency. Writing `will` as an alias is a claim that the word carries the
    concept — for `will-effort` it means volition, not the auxiliary verb that
    makes it match 12% of the corpus. The same protection covers `--terms`: a
    hand-picked term is a deliberate act and is taken at face value."""
    raw = [concept["name"]] + [a["alias"] for a in concept.get("aliases", [])] + extra
    own = {form.strip().lower() for form in raw if form.strip().isalpha()}
    terms: list[str] = []
    for item in raw:
        for token in re.split(r"[^\w']+", item.lower()):
            if len(token) < 3 or token in terms:
                continue
            if token in STOPWORDS and token not in own:
                continue
            terms.append(token)
    return terms


def build_query(terms: list[str]) -> str:
    return " OR ".join(f"{t}*" for t in terms)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{CORPUS_DB}?mode=ro", uri=True)
    conn.execute("ATTACH DATABASE ? AS catalog", (f"file:{CATALOG_DB}?mode=ro",))
    conn.row_factory = sqlite3.Row
    return conn


QUERY = """
SELECT p.id, p.item_code, p.t_start, p.t_end, p.word_count, p.text,
       p.timestamps_synthetic, p.attribution,
       t.corpus_tier, i.title, i.year, i.event_type,
       (SELECT l.video_id FROM catalog.item_links l
         WHERE l.item_id = i.id AND l.video_id IS NOT NULL
         ORDER BY l.link_kind = 'primary' DESC LIMIT 1) AS video_id,
       bm25(passages_fts) AS score
FROM passages_fts
JOIN passages   AS p ON p.id = passages_fts.rowid
JOIN transcripts AS t ON t.id = p.transcript_id
JOIN catalog.items AS i ON i.code = p.item_code
WHERE passages_fts MATCH ?
  AND p.word_count >= ?
ORDER BY score
"""


def citation(video_id: str | None, t_start: float) -> str | None:
    if not video_id:
        return None
    return f"https://youtu.be/{video_id}?t={int(t_start)}"


def timecode(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def retrieve(conn: sqlite3.Connection, match: str, limit: int,
             per_item: int, min_words: int) -> list[dict]:
    seen: dict[str, int] = {}
    # A handful of recordings are published under two codes, so the same words
    # can surface twice with two different citations. Keep the better-ranked one
    # — offering both invites citing one passage as if it were two witnesses.
    texts: set[str] = set()
    out: list[dict] = []
    for row in conn.execute(QUERY, (match, min_words)):
        code = row["item_code"]
        if seen.get(code, 0) >= per_item:
            continue
        text_key = " ".join(row["text"].split())
        if text_key in texts:
            continue
        texts.add(text_key)
        seen[code] = seen.get(code, 0) + 1
        out.append({
            "passage_id": row["id"],
            "item_code": code,
            "title": row["title"],
            "year": row["year"],
            "event_type": row["event_type"],
            "tier": row["corpus_tier"],
            "t_start": row["t_start"],
            "t_end": row["t_end"],
            "timecode": timecode(row["t_start"]),
            "synthetic_timestamps": bool(row["timestamps_synthetic"]),
            "attribution": row["attribution"],
            "word_count": row["word_count"],
            "score": row["score"],
            "citation": citation(row["video_id"], row["t_start"]),
            "text": row["text"],
        })
        if len(out) >= limit:
            break
    return out


def as_markdown(concept: dict, terms: list[str], rows: list[dict]) -> str:
    lines = [
        f"# Candidates — {concept['name']} (`{concept['slug']}`)",
        "",
        f"**Definition.** {concept['definition']}",
        "",
        f"**Include.** {concept.get('include_criteria', '—')}",
        "",
        f"**Exclude.** {concept.get('exclude_criteria', '—')}",
        "",
        f"**Query terms.** `{'`, `'.join(terms)}`  ·  **{len(rows)} candidates**",
        "",
        "---",
        "",
    ]
    for n, r in enumerate(rows, 1):
        flag = "  ⚠︎ synthetic timestamps" if r["synthetic_timestamps"] else ""
        cite = r["citation"] or "_(no video link)_"
        lines += [
            f"### {n}. {r['item_code']} — {r['title']} ({r['year']}, "
            f"{r['event_type']}, tier {r['tier']})",
            f"`{r['timecode']}` · {r['word_count']} words · {cite}{flag}",
            "",
            f"> {r['text']}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="concept slug, e.g. fear")
    ap.add_argument("--limit", type=int, default=300, help="max candidates (default 300)")
    ap.add_argument("--per-item", type=int, default=2,
                    help="max passages from one recording (default 2)")
    ap.add_argument("--min-words", type=int, default=60,
                    help="drop passages shorter than this (default 60)")
    ap.add_argument("--terms", default="",
                    help="comma-separated extra query terms")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    ap.add_argument("--out", type=Path, help="write to this file instead of stdout")
    args = ap.parse_args()

    if not CORPUS_DB.exists():
        print(f"error: {CORPUS_DB} not found", file=sys.stderr)
        return 1

    concept = load_concept(args.slug)
    extra = [t.strip() for t in args.terms.split(",") if t.strip()]
    terms = fts_terms(concept, extra)
    match = build_query(terms)

    conn = connect()
    try:
        rows = retrieve(conn, match, args.limit, args.per_item, args.min_words)
    finally:
        conn.close()

    if not rows:
        print(f"error: no passages matched {match!r}", file=sys.stderr)
        return 1

    if args.format == "md":
        payload = as_markdown(concept, terms, rows)
    else:
        payload = json.dumps({
            "slug": args.slug,
            "name": concept["name"],
            "terms": terms,
            "match": match,
            "count": len(rows),
            "candidates": rows,
        }, indent=2, ensure_ascii=False)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {len(rows)} candidates to {args.out}", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
