#!/usr/bin/env python3
"""Generate the "Roots of Knowledge" Obsidian notes from the concept registry.

This renders the L3 concept canon (``concepts/concepts.jsonl``) into browsable
Obsidian notes under ``obsidian/roots/`` so the 36 fundamental roots — their
definitions, criteria, aliases, and typed relations — can be read and navigated
as a linked graph.

The registry closed at a final 36 roots on 2026-07-25 (STRATEGY.md, "Concept
registry — current state"): every root is ``active``, and none carries
provisional or probation status. The notes are *generated*, never hand-edited —
edit ``concepts/concepts.jsonl`` and re-run.

An I Ching navigation layer once rendered a navigator note, one note per
trigram gate, and a bridge line on every concept note. It was archived on
2026-07-25 (undecided, not rejected) — see ``archive/iching/README.md`` for the
data, the removed rendering code, and how to bring it back.

Ownership: this script owns only ``obsidian/roots/Map of the 36 Roots.md`` and
everything under ``obsidian/roots/concepts/``. The curated hub and
``reference/`` notes are authored by hand and left untouched (so a regen never
clobbers them). ``build_catalog.py`` preserves the whole ``obsidian/roots/``
subtree across catalog rebuilds.

    python3 scripts/build_concept_vault.py            # regenerate
    python3 scripts/build_concept_vault.py --check     # non-zero if stale (CI-friendly)

``--check`` also fails on dead ``[[wikilinks]]`` anywhere in the vault, so a
renamed or deleted note cannot silently rot the graph.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONCEPTS_JSONL = ROOT / "concepts" / "concepts.jsonl"
OBSIDIAN = ROOT / "obsidian"
VAULT = OBSIDIAN / "roots"
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

# The registry closed on 2026-07-25: every root is `active`, so no per-root
# status badge is rendered any more. The history of each merge and promotion
# lives in the STRATEGY.md decision log, which is the right place for it — a
# badge on a closed registry only reads as unfinished business.

WIKILINK_RE = re.compile(r"\[\[([^\]|#^]+)")


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
        "**36 roots**, all active · **4 facets** (entry-points, *not* stages). "
        "The registry closed on 2026-07-25; see [[Strategy]] for the decision "
        "log. Canonical source: `concepts/concepts.jsonl`.",
        "",
        "See [[Roots of Knowledge]] for the hub.",
        "",
    ]
    n = 0
    for facet, blurb, slugs in FACETS:
        lines += [f"## {facet}", "", f"*{blurb}*", ""]
        for slug in slugs:
            c = concepts[slug]
            n += 1
            hook = first_sentence(c["definition"])
            lines.append(f"{n}. [[{slug}|{c['name']}]]  ")
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


def build() -> list[tuple[Path, str]]:
    concepts = load_concepts()
    by_slug = {c["slug"]: c for c in concepts}
    names = {c["slug"]: c["name"] for c in concepts}
    facet_of = {s: facet for facet, _, slugs in FACETS for s in slugs}

    written: list[tuple[Path, str]] = []
    n = 0
    for facet, _, slugs in FACETS:
        for slug in slugs:
            n += 1
            written.append((
                CONCEPTS_DIR / f"{slug}.md",
                render_concept(by_slug[slug], names, n, facet_of[slug])))
    written.append((MAP_NOTE, render_map(by_slug)))
    return written


def dead_wikilinks(outputs: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    """``[[targets]]`` in the vault that resolve to no note.

    Obsidian resolves a wikilink by basename anywhere in the vault, so the
    resolvable set is every ``.md`` stem under ``obsidian/`` — with the pending
    generated notes substituted in, so ``--check`` describes the vault as it
    *will* be, not a half-regenerated state.
    """
    pending = dict(outputs)
    stems = {p.stem for p in OBSIDIAN.rglob("*.md")} | {p.stem for p in pending}
    sources = {p: p.read_text(encoding="utf-8") for p in OBSIDIAN.rglob("*.md")}
    sources.update(pending)

    dead: list[tuple[Path, str]] = []
    for path, text in sorted(sources.items()):
        for target in dict.fromkeys(WIKILINK_RE.findall(text)):
            # Escaped pipes inside table cells survive the character class.
            target = target.strip().split("\\")[0].strip()
            resolved = target[:-3] if target.endswith(".md") else target
            if resolved and resolved not in stems:
                dead.append((path, target))
    return dead


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if any generated note is stale "
                             "or any wikilink in the vault is dead")
    args = parser.parse_args(argv)

    outputs = build()
    if args.check:
        failed = False
        stale = [p for p, content in outputs
                 if not p.exists() or p.read_text(encoding="utf-8") != content]
        if stale:
            failed = True
            print("stale concept-vault notes:", file=sys.stderr)
            for p in stale:
                print(f"  {p.relative_to(ROOT)}", file=sys.stderr)
        dead = dead_wikilinks(outputs)
        if dead:
            failed = True
            print("dead wikilinks:", file=sys.stderr)
            for path, target in dead:
                print(f"  {path.relative_to(ROOT)} -> [[{target}]]",
                      file=sys.stderr)
        if failed:
            return 1
        print(f"concept vault up to date ({len(outputs)} notes, no dead links)")
        return 0

    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs:
        path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(outputs)} concept-vault notes to "
          f"{VAULT.relative_to(ROOT)}/")
    dead = dead_wikilinks(outputs)
    if dead:
        print(f"warning: {len(dead)} dead wikilink(s) — run --check for detail",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
