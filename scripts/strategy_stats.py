#!/usr/bin/env python3
"""Regenerate the live-numbers block in `STRATEGY.md` from the databases.

STRATEGY.md's arbitration rule is that "Where things stand" wins any
disagreement with the decision log — log entries record what was believed on
their date, the live numbers record what is true now. That only holds while the
numbers *are* current, and every one of them used to be hand-copied out of a
query. On 2026-07-26 the section was stamped one date and already carried facts
from the next, which is precisely how the section that is supposed to settle
disagreements loses the standing to settle them.

So the block is generated. Everything between

    <!-- BEGIN GENERATED: where-things-stand -->
    <!-- END GENERATED: where-things-stand -->

is rewritten from `catalog/krishnamurti.db`, `corpus/krishnamurti-corpus.db`,
`concepts/concepts.jsonl`, and `concepts/citations.jsonl`. Prose outside the
markers is left alone — backup and distribution state are facts no query knows,
so they stay hand-written.

The date stamp only advances when the numbers actually change: `--check` would
otherwise fail every day on nothing but a fresh date, and a gate that cries wolf
gets disabled.

Modes:

- default   — rewrite the block in place.
- --dry-run — print the block, write nothing.
- --check   — exit non-zero if the committed block disagrees with the
              databases. Run it with `build_concept_vault.py --check` and
              `build_citations.py --verify` before committing.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DB = ROOT / "catalog" / "krishnamurti.db"
CORPUS_DB = ROOT / "corpus" / "krishnamurti-corpus.db"
CONCEPTS = ROOT / "concepts" / "concepts.jsonl"
CITATIONS = ROOT / "concepts" / "citations.jsonl"
STRATEGY = ROOT / "STRATEGY.md"

BEGIN = "<!-- BEGIN GENERATED: where-things-stand -->"
END = "<!-- END GENERATED: where-things-stand -->"
DATE_LINE = re.compile(r"^Live numbers, generated from the databases on \*\*(.+?)\*\*.*$",
                       re.MULTILINE)

# Sections carrying items that never came from the Full-Length PDF. Keyed by
# `sections.number`; the letter is fixed ("10A", "11A") and only used for display.
OVERLAY_SECTIONS = {10: "Education Directory", 11: "@KFoundation channel"}
TOP_EVENT_TYPES = 12


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.expanduser().resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _n(value: int | float | None) -> str:
    """Thousands-separated, matching the prose style of the document."""
    if value is None:
        return "0"
    return f"{value:,.1f}" if isinstance(value, float) else f"{value:,}"


def collect_archive(conn: sqlite3.Connection) -> dict:
    items, hours = conn.execute(
        "SELECT COUNT(*), SUM(duration_minutes)/60.0 FROM items").fetchone()
    overlay = {}
    for number, label in OVERLAY_SECTIONS.items():
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM items i JOIN sections s ON s.id=i.section_id "
            "WHERE s.number=?", (number,)).fetchone()
        overlay[number] = (label, count)
    (media,) = conn.execute(
        "SELECT COUNT(*) FROM item_media WHERE status='downloaded'").fetchone()
    # `manual`/`missing` rows are probe results — the items KFT never subtitled —
    # not a transcript source, so they are not a row in a table of sources.
    subtitles = conn.execute(
        "SELECT kind, status, COUNT(DISTINCT item_id) AS items FROM item_subtitles "
        "WHERE status IN ('downloaded','planned') GROUP BY kind, status "
        "ORDER BY status<>'downloaded', items DESC, kind").fetchall()
    (covered,) = conn.execute(
        "SELECT COUNT(DISTINCT item_id) FROM item_subtitles "
        "WHERE status='downloaded'").fetchone()
    tiers = conn.execute(
        "SELECT corpus_tier, COUNT(*) AS n FROM items GROUP BY corpus_tier "
        "ORDER BY corpus_tier").fetchall()
    events = conn.execute(
        "SELECT event_type, event_type_label, COUNT(*) AS n, "
        "SUM(duration_minutes)/60.0 AS h FROM items "
        "GROUP BY event_type ORDER BY n DESC").fetchall()
    return {
        "items": items,
        "hours": hours or 0.0,
        "pdf": items - sum(count for _, count in overlay.values()),
        "overlay": overlay,
        "media": media,
        "subtitles": subtitles,
        "covered": covered,
        "tiers": tiers,
        "events": events,
    }


def collect_corpus(conn: sqlite3.Connection) -> dict:
    (transcripts,) = conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()
    tiers = conn.execute(
        "SELECT COALESCE(corpus_tier,'?') AS tier, COUNT(*) AS n FROM transcripts "
        "GROUP BY tier ORDER BY tier").fetchall()
    (segments,) = conn.execute("SELECT COUNT(*) FROM segments").fetchone()
    (passages,) = conn.execute("SELECT COUNT(*) FROM passages").fetchone()
    (k_passages,) = conn.execute(
        "SELECT COUNT(*) FROM passages WHERE speaker_code='K'").fetchone()
    (fts,) = conn.execute("SELECT COUNT(*) FROM passages_fts").fetchone()
    resolved = conn.execute(
        "SELECT COALESCE(resolved_via,'?') AS via, COUNT(*) AS n FROM transcripts "
        "GROUP BY via ORDER BY n DESC").fetchall()
    return {
        "transcripts": transcripts,
        "tiers": tiers,
        "segments": segments,
        "passages": passages,
        "k_passages": k_passages,
        "fts": fts,
        "resolved": resolved,
    }


def collect_concepts() -> dict:
    active: list[str] = []
    deprecated: list[str] = []
    for line in CONCEPTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        (active if entry.get("status") == "active" else deprecated).append(entry["slug"])
    return {"active": active, "deprecated": sorted(deprecated)}


def collect_citations() -> dict:
    """Per-root citation shape, in the order the roots were first cited."""
    by_slug: dict[str, dict] = {}
    total = 0
    for line in CITATIONS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cite = json.loads(line)
        total += 1
        root = by_slug.setdefault(
            cite["slug"], {"passages": 0, "themes": [], "years": [], "items": set()})
        root["passages"] += 1
        if cite["theme"] not in root["themes"]:
            root["themes"].append(cite["theme"])
        if cite.get("year"):
            root["years"].append(cite["year"])
        root["items"].add(cite["item_code"])
    return {"total": total, "roots": by_slug}


def render(stamp: str) -> str:
    if not CORPUS_DB.exists():
        raise SystemExit(
            f"error: {CORPUS_DB} not found — restore it first:\n"
            f"  zstd -d corpus/krishnamurti-corpus.db.zst -o corpus/krishnamurti-corpus.db")
    catalog_conn = _readonly(CATALOG_DB)
    corpus_conn = _readonly(CORPUS_DB)
    try:
        archive = collect_archive(catalog_conn)
        corpus = collect_corpus(corpus_conn)
    finally:
        catalog_conn.close()
        corpus_conn.close()
    concepts = collect_concepts()
    citations = collect_citations()

    out: list[str] = [
        f"Live numbers, generated from the databases on **{stamp}** by "
        "`scripts/strategy_stats.py`. Do not hand-edit — run the script.",
        "",
    ]

    provenance = " + ".join(
        f"{_n(count)} {label} ({number}A)"
        for number, (label, count) in sorted(archive["overlay"].items()))
    out += [
        f"**Archive (L0)** — {_n(archive['items'])} items / {_n(archive['hours'])} h. "
        f"Provenance: {_n(archive['pdf'])} Full-Length PDF + {provenance}. "
        f"{_n(archive['media'])} media files downloaded.",
        "",
    ]

    coverage = ("every item has a downloaded transcript of some kind"
                if archive["covered"] >= archive["items"]
                else f"{_n(archive['covered'])} of {_n(archive['items'])} items have "
                     "a downloaded transcript")
    out += [f"**Transcript sources** — {coverage}.", ""]
    out += ["| Kind | Status | Items |", "|---|---|---|"]
    out += [f"| `{row['kind']}` | {row['status']} | {_n(row['items'])} |"
            for row in archive["subtitles"]]
    out += [""]

    corpus_tiers = " / ".join(f"{row['tier']} {_n(row['n'])}" for row in corpus["tiers"])
    resolved = ", ".join(f"{_n(row['n'])} `{row['via']}`" for row in corpus["resolved"])
    out += [
        f"**Corpus (L1/L2)** — {_n(corpus['transcripts'])} transcripts ingested "
        f"(tier {corpus_tiers}), {_n(corpus['segments'])} segments, "
        f"{_n(corpus['passages'])} passages, of which {_n(corpus['k_passages'])} are "
        f"K-passages and {_n(corpus['fts'])} are in `passages_fts` (tiers A/B only). "
        f"Subtitle resolution: {resolved}.",
        "",
        "**Tiers** — " + " · ".join(
            f"{row['corpus_tier']} {_n(row['n'])}" for row in archive["tiers"]) + ".",
        "",
    ]

    top = archive["events"][:TOP_EVENT_TYPES]
    tail = len(archive["events"]) - len(top)
    out += [
        "**Largest event types** — " + " · ".join(
            f"{row['event_type']} {row['event_type_label']} {_n(row['n'])} / "
            f"{_n(row['h'] or 0.0)} h" for row in top)
        + (f", plus a tail of {tail} more types." if tail > 0 else "."),
        "",
    ]

    tombstones = ", ".join(f"`{slug}`" for slug in concepts["deprecated"])
    out += [
        f"**Concepts (L3)** — {_n(len(concepts['active']))} active roots + "
        f"{_n(len(concepts['deprecated']))} deprecated tombstones ({tombstones}). "
        "Tombstones stay so predictions keyed to their ids remain resolvable; "
        "consumers filter by `status`.",
        "",
    ]

    cited = citations["roots"]
    notes = len(concepts["active"]) + 1  # one note per root, plus the Map
    shape = " · ".join(
        f"`{slug}` ({_n(root['passages'])} passages, "
        f"{min(root['years'])}–{max(root['years'])}, {len(root['themes'])} themes)"
        for slug, root in cited.items())
    out += [
        f"**Vault (L4)** — {_n(notes)} generated notes "
        f"({_n(len(concepts['active']))} concepts + Map). "
        f"**{_n(len(cited))} roots of {_n(len(concepts['active']))} cited**, "
        f"{_n(citations['total'])} curated passages in all, each linking to the "
        f"second it is spoken: {shape}.",
    ]
    return "\n".join(out)


def splice(text: str, block: str) -> str:
    start, end = text.index(BEGIN), text.index(END)
    return text[:start] + BEGIN + "\n\n" + block + "\n\n" + text[end:]


def current_block(text: str) -> str:
    start = text.index(BEGIN) + len(BEGIN)
    return text[start:text.index(END)].strip()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed block is stale")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the block; write nothing")
    args = ap.parse_args()

    text = STRATEGY.read_text(encoding="utf-8")
    for marker in (BEGIN, END):
        if text.count(marker) != 1:
            print(f"error: {STRATEGY.name} must contain exactly one {marker}",
                  file=sys.stderr)
            return 1

    existing = current_block(text)
    match = DATE_LINE.search(existing)
    stamp = match.group(1) if match else ""

    # Regenerate under the *stored* stamp first: if only the date would differ,
    # the block is not stale, and re-dating it would be noise in the diff.
    if render(stamp) == existing:
        if args.check:
            print(f"where-things-stand is current (as of {stamp})")
        elif args.dry_run:
            print(existing)
        else:
            print(f"where-things-stand already matches the databases (as of {stamp})")
        return 0

    block = render(date.today().isoformat())
    if args.check:
        print("error: where-things-stand is stale — run scripts/strategy_stats.py",
              file=sys.stderr)
        return 1
    if args.dry_run:
        print(block)
        return 0
    STRATEGY.write_text(splice(text, block), encoding="utf-8")
    print(f"regenerated where-things-stand in {STRATEGY.name} ({date.today().isoformat()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
