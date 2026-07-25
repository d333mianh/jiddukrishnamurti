#!/usr/bin/env python3
"""Generate the "Roots of Knowledge" Obsidian notes from the concept registry.

This renders the L3 concept canon (``concepts/concepts.jsonl``) into browsable
Obsidian notes under ``obsidian/roots/`` so the 36 fundamental roots — their
definitions, criteria, aliases, and typed relations — can be read and navigated
as a linked graph.

The registry closed at a final 36 roots on 2026-07-25 (STRATEGY.md, "Concept
registry — current state"): no root carries provisional or probation status. The
notes are *generated*, never hand-edited — edit ``concepts/concepts.jsonl`` and
re-run.

Ownership: this script owns only ``obsidian/roots/Map of the 36 Roots.md`` and
everything under ``obsidian/roots/concepts/``. The curated hub and ``reference/``
notes are authored by hand and left untouched (so a regen never clobbers them).
``build_catalog.py`` preserves the whole ``obsidian/roots/`` subtree across
catalog rebuilds.

    python3 scripts/build_concept_vault.py            # regenerate
    python3 scripts/build_concept_vault.py --check     # non-zero if stale (CI-friendly)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONCEPTS_JSONL = ROOT / "concepts" / "concepts.jsonl"
VAULT = ROOT / "obsidian" / "roots"
CONCEPTS_DIR = VAULT / "concepts"
MAP_NOTE = VAULT / "Map of the 36 Roots.md"

# The four non-sequential facets (STRATEGY.md, 2026-07-07). Facets are
# entry-points, not stages: freedom is at the beginning of inquiry, not a reward,
# and the immeasurable is not a destination reached by working through the rest.
FACETS: list[tuple[str, str, list[str]]] = [
    (
        "I. Structures of Consciousness",
        "The machinery of the conditioned mind — how the known is built and sustained.",
        ["thought", "conditioning", "will-effort", "psychological-time",
         "relationship", "division", "belief", "consciousness"],
    ),
    (
        "II. Human Experience & Relationship",
        "The felt symptoms that machinery produces in daily life.",
        ["fear", "pleasure", "suffering", "loneliness", "conflict", "violence",
         "comparison", "attachment", "authority"],
    ),
    (
        "III. Observation, Inquiry & Action",
        "The turning — seeing without the observer, and acting from that seeing.",
        ["freedom", "observer-observed", "awareness", "listening", "insight",
         "learning", "truth", "order", "action", "responsibility",
         "self-knowledge"],
    ),
    (
        "IV. Ending, Transformation & the Sacred",
        "What is not put together by thought — the immeasurable, not a destination.",
        ["love", "death", "meditation", "beauty", "nature", "energy",
         "psychological-revolution", "religious-mind"],
    ),
]

# Curated status annotations layered on top of the JSONL status enum
# (active|pilot). These track the STRATEGY.md 2026-07-07 open questions; keep in
# sync with the decision log. slug -> (short badge, longer note or "").
STATUS_NOTES: dict[str, tuple[str, str]] = {
    "thought": ("pilot", "One of three round-1 pilot concepts."),
    "fear": ("pilot", "One of three round-1 pilot concepts."),
    "freedom": ("pilot", "One of three round-1 pilot concepts."),
    "self-knowledge": (
        "merged root",
        "Absorbed The Self (\"the me\") on 2026-07-25 — the last probation pair, "
        "decided ahead of the pilot: the knowing and the thing known are one "
        "movement.",
    ),
    "listening": (
        "new root",
        "Promoted 2026-07-25 out of [[awareness|Awareness & Attention]]'s "
        "aliases — K treats the art of listening as its own field.",
    ),
    "will-effort": (
        "new root",
        "Added 2026-07-25 to fill the slot freed by the self/self-knowledge "
        "merge. Claims `effort` from [[conflict|Conflict]] and `discipline` "
        "from [[order|Order & Disorder]], which owned them only as aliases.",
    ),
    "religious-mind": (
        "merged root",
        "Absorbed The Sacred / The Immeasurable (2026-07-16) — the closest pair "
        "in the set; the freed slot became [[responsibility|Responsibility]].",
    ),
    "responsibility": (
        "new root",
        "Added 2026-07-16 in the slot freed by the religious-mind/sacred merge. "
        "Total responsibility — 'you are the world' — spanning consciousness, "
        "relationship, and action.",
    ),
}

CALLOUT = {"pilot": "warning", "provisional root": "warning",
           "probation pair": "question", "active": "note",
           "merged root": "info", "new root": "info"}


def load_concepts() -> list[dict]:
    concepts = [json.loads(line) for line in
                CONCEPTS_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Deprecated concepts stay in the JSONL as tombstones (the importer keeps
    # their DB rows resolvable) but are not rendered into the vault.
    concepts = [c for c in concepts if c["status"] != "deprecated"]
    by_slug = {c["slug"] for c in concepts}
    mapped = {s for _, _, slugs in FACETS for s in slugs}
    missing = by_slug - mapped
    if missing:
        raise SystemExit(f"concepts not placed in any facet: {sorted(missing)} — "
                         f"update FACETS in {Path(__file__).name}")
    return concepts


def first_sentence(text: str) -> str:
    for end in (". ", "? ", "! "):
        idx = text.find(end)
        if idx != -1:
            return text[: idx + 1].strip()
    return text.strip()


def render_concept(concept: dict, names: dict[str, str], index: int,
                   facet: str) -> str:
    slug = concept["slug"]
    name = concept["name"]
    badge, note = STATUS_NOTES.get(slug, (concept["status"], ""))
    callout = CALLOUT.get(badge, "note")

    alias_forms = [a["alias"] for a in concept.get("aliases", [])]
    fm_aliases = ", ".join(json.dumps(a) for a in [name, *alias_forms])

    lines = [
        "---",
        f"tags: [krishnamurti, root, concept, status/{concept['status']}]",
        f"slug: {slug}",
        f'facet: "{facet}"',
        f"status: {concept['status']}",
        f"aliases: [{fm_aliases}]",
        "---",
        f"# {name}",
        "",
        f"> [!{callout}] {badge.title()}"
        + (f"\n> {note}" if note else ""),
        "",
        f"**Facet:** {facet} · **Root {index} of 36** · "
        f"[[Map of the 36 Roots|↩ Map]] · [[Strategy]]",
        "",
        "## Definition",
        concept["definition"],
        "",
        "## What counts as this root",
        concept.get("include_criteria", "").strip() or "_—_",
        "",
        "## What does not",
        concept.get("exclude_criteria", "").strip() or "_—_",
        "",
    ]

    aliases = concept.get("aliases", [])
    if aliases:
        lines.append("## Also called")
        for a in aliases:
            period = f" _({a['period_note']})_" if a.get("period_note") else ""
            lines.append(f"- {a['alias']}{period}")
        lines.append("")

    relations = concept.get("relations", [])
    if relations:
        lines.append("## Related roots")
        for r in relations:
            target = r["to"]
            label = names.get(target, target)
            rel_note = f" — {r['note']}" if r.get("note") else ""
            lines.append(f"- [[{target}|{label}]] · *{r['relation']}*{rel_note}")
        lines.append("")

    lines += [
        "---",
        "*Generated from `concepts/concepts.jsonl` by "
        "`scripts/build_concept_vault.py`. Edit the JSONL, then regenerate — "
        "do not hand-edit this note.*",
    ]
    return "\n".join(lines) + "\n"


def render_map(concepts: dict[str, dict]) -> str:
    active = sum(1 for c in concepts.values() if c["status"] == "active")
    pilot = sum(1 for c in concepts.values() if c["status"] == "pilot")
    lines = [
        "---",
        "tags: [krishnamurti, root, index]",
        "---",
        "# Map of the 36 Roots",
        "",
        "The most fundamental concepts of Krishnamurti's teachings, as the **L3 "
        "concept layer** of the corpus. Each root is a citation target: passages "
        "across the ~1,540-recording archive get tagged to these, so any concept "
        "can later be read back in K's own words with timestamped links.",
        "",
        f"**36 roots** · {active} active · {pilot} pilot · **4 facets** "
        "(entry-points, *not* stages).",
        "",
        "See [[Roots of Knowledge]] for the hub and [[Strategy]] for what is "
        "still open. Canonical source: `concepts/concepts.jsonl`.",
        "",
    ]
    n = 0
    for facet, blurb, slugs in FACETS:
        lines += [f"## {facet}", "", f"*{blurb}*", ""]
        for slug in slugs:
            c = concepts[slug]
            n += 1
            badge, _ = STATUS_NOTES.get(slug, (c["status"], ""))
            tag = "" if badge == "active" else f" — **{badge}**"
            hook = first_sentence(c["definition"])
            lines.append(f"{n}. [[{slug}|{c['name']}]]{tag}  ")
            # Continuation aligns to the marker width ("10. " = 4 cols) so it
            # stays inside the list item. Use native italic, not raw <small>:
            # inline HTML that wraps inside a list item makes Obsidian break the
            # text out of the list and render overflow one word per line.
            indent = " " * len(f"{n}. ")
            lines.append(f"{indent}*{hook}*")
        lines.append("")
    lines += [
        "---",
        "*Generated by `scripts/build_concept_vault.py`.*",
    ]
    return "\n".join(lines) + "\n"


def build() -> list[Path]:
    concepts = load_concepts()
    by_slug = {c["slug"]: c for c in concepts}
    names = {c["slug"]: c["name"] for c in concepts}
    facet_of = {s: facet for facet, _, slugs in FACETS for s in slugs}

    written: list[tuple[Path, str]] = []
    n = 0
    for facet, _, slugs in FACETS:
        for slug in slugs:
            n += 1
            written.append((CONCEPTS_DIR / f"{slug}.md",
                            render_concept(by_slug[slug], names, n, facet_of[slug])))
    written.append((MAP_NOTE, render_map(by_slug)))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if any generated note is stale")
    args = parser.parse_args(argv)

    outputs = build()
    if args.check:
        stale = [p for p, content in outputs
                 if not p.exists() or p.read_text(encoding="utf-8") != content]
        if stale:
            print("stale concept-vault notes:", file=sys.stderr)
            for p in stale:
                print(f"  {p.relative_to(ROOT)}", file=sys.stderr)
            return 1
        print(f"concept vault up to date ({len(outputs)} notes)")
        return 0

    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs:
        path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(outputs)} concept-vault notes to "
          f"{VAULT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
