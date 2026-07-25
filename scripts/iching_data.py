#!/usr/bin/env python3
"""Trigram/hexagram reference data for the I Ching navigation layer.

The 36 roots of the L3 concept registry are given an optional *navigation*
interface built on the eight trigrams. The construction is::

    8 self-pairs + 28 distinct two-gate pairs = 36 bridges

so every root is reachable through exactly one unordered pair of gates, and a
six-line cast (lines 1-3 = lower gate, lines 4-6 = upper gate) resolves to
exactly one root. The number 36 is *derived* here, not assigned — which is why
this mapping is navigation metadata and never touches ``concepts.jsonl``.

Nothing in this module claims that a root means what a King Wen hexagram means.
The King Wen table exists only to derive the Unicode glyph: the hexagram block
U+4DC0-U+4DFF is laid out in King Wen order, so rendering the character for a
(lower, upper) pair requires the number. Traditional judgments, line texts, and
translations are deliberately absent — see ``I Ching Navigator.md``.

Smoke test::

    python3 scripts/iching_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAVIGATION_JSON = ROOT / "concepts" / "iching_navigation.json"

# The eight gates, in the canonical order used for display and for sorting a
# gate pair into its bridge key. ``lines`` is bottom-to-top, "1" solid (yang),
# "0" broken (yin) — the order a cast produces them in.
GATES: list[dict[str, str]] = [
    {"key": "qian", "symbol": "☰", "lines": "111", "name": "Creative / Heaven",
     "inquiry_phrase": "unbounded energy and possibility"},
    {"key": "kun", "symbol": "☷", "lines": "000", "name": "Receptive / Earth",
     "inquiry_phrase": "receptive attention to what is"},
    {"key": "zhen", "symbol": "☳", "lines": "100", "name": "Arousing / Thunder",
     "inquiry_phrase": "disturbance, movement, and change"},
    {"key": "xun", "symbol": "☴", "lines": "011", "name": "Penetrating / Wind",
     "inquiry_phrase": "subtle influence, thought, and conditioning"},
    {"key": "kan", "symbol": "☵", "lines": "010", "name": "Abysmal / Water",
     "inquiry_phrase": "fear, insecurity, and human depth"},
    {"key": "li", "symbol": "☲", "lines": "101", "name": "Clinging / Fire",
     "inquiry_phrase": "image, consciousness, and illumination"},
    {"key": "gen", "symbol": "☶", "lines": "001", "name": "Stillness / Mountain",
     "inquiry_phrase": "ending, stillness, and order"},
    {"key": "dui", "symbol": "☱", "lines": "110", "name": "Joyous / Lake",
     "inquiry_phrase": "relationship, feeling, and communion"},
]

GATE_ORDER: list[str] = [g["key"] for g in GATES]
GATE_BY_KEY: dict[str, dict[str, str]] = {g["key"]: g for g in GATES}
GATE_BY_LINES: dict[str, str] = {g["lines"]: g["key"] for g in GATES}

# King Wen number for every (lower gate, upper gate) pair. Used *only* to index
# the Unicode hexagram block, which is in King Wen order. Rows are the lower
# trigram, columns the upper trigram.
KING_WEN: dict[tuple[str, str], int] = {}
_KING_WEN_ROWS: list[tuple[str, list[int]]] = [
    # lower          upper: qian zhen  kan  gen  kun  xun   li  dui
    ("qian", [1, 34, 5, 26, 11, 9, 14, 43]),
    ("zhen", [25, 51, 3, 27, 24, 42, 21, 17]),
    ("kan", [6, 40, 29, 4, 7, 59, 64, 47]),
    ("gen", [33, 62, 39, 52, 15, 53, 56, 31]),
    ("kun", [12, 16, 8, 23, 2, 20, 35, 45]),
    ("xun", [44, 32, 48, 18, 46, 57, 50, 28]),
    ("li", [13, 55, 63, 22, 36, 37, 30, 49]),
    ("dui", [10, 54, 60, 41, 19, 61, 38, 58]),
]
_KING_WEN_COLS = ["qian", "zhen", "kan", "gen", "kun", "xun", "li", "dui"]
for _lower, _numbers in _KING_WEN_ROWS:
    for _upper, _n in zip(_KING_WEN_COLS, _numbers):
        KING_WEN[(_lower, _upper)] = _n


def hexagram_number(lower: str, upper: str) -> int:
    """King Wen number for a hexagram with these lower and upper gates."""
    try:
        return KING_WEN[(lower, upper)]
    except KeyError:
        raise KeyError(f"unknown gate pair: lower={lower!r} upper={upper!r}") from None


def glyph(number: int) -> str:
    """Unicode hexagram character for a King Wen number (U+4DC0 is #1)."""
    if not 1 <= number <= 64:
        raise ValueError(f"King Wen number out of range: {number}")
    return chr(0x4DBF + number)


def hexagram_glyph(lower: str, upper: str) -> str:
    """Unicode hexagram character for a (lower, upper) gate pair."""
    return glyph(hexagram_number(lower, upper))


def bridge_key(gate_a: str, gate_b: str) -> tuple[str, str]:
    """Canonical (order-independent) key for the bridge between two gates."""
    for key in (gate_a, gate_b):
        if key not in GATE_BY_KEY:
            raise KeyError(f"unknown gate: {key!r}")
    return tuple(sorted((gate_a, gate_b), key=GATE_ORDER.index))  # type: ignore[return-value]


def all_bridge_keys() -> list[tuple[str, str]]:
    """The 36 unordered gate pairs, in canonical order."""
    return [(a, b) for i, a in enumerate(GATE_ORDER) for b in GATE_ORDER[i:]]


def lines_to_gates(lines: list[int]) -> tuple[str, str]:
    """Map six cast line values (6-9, bottom-to-top) to (lower, upper) gates."""
    if len(lines) != 6:
        raise ValueError(f"expected 6 lines, got {len(lines)}")
    bits = ""
    for value in lines:
        if value not in (6, 7, 8, 9):
            raise ValueError(f"line values must be 6-9, got {value}")
        bits += "1" if value % 2 else "0"
    return GATE_BY_LINES[bits[:3]], GATE_BY_LINES[bits[3:]]


def load_navigation(path: Path | None = None) -> dict:
    """Load and validate ``concepts/iching_navigation.json``.

    Raises ``ValueError`` on any broken invariant — the navigation layer is
    rendered from this file, so a malformed mapping is fatal rather than
    silently partial.
    """
    path = path or NAVIGATION_JSON
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_navigation(data)
    return data


def validate_navigation(data: dict, known_roots: set[str] | None = None) -> None:
    """Check every invariant the generated navigation depends on."""
    gates = data.get("gates", [])
    if len(gates) != 8:
        raise ValueError(f"expected 8 gates, got {len(gates)}")
    for field in ("key", "symbol", "lines"):
        values = [g[field] for g in gates]
        if len(set(values)) != 8:
            raise ValueError(f"gate {field} values are not unique: {values}")
    if {g["key"] for g in gates} != set(GATE_ORDER):
        raise ValueError("gate keys do not match the canonical eight")
    for gate in gates:
        canonical = GATE_BY_KEY[gate["key"]]
        for field in ("symbol", "lines"):
            if gate[field] != canonical[field]:
                raise ValueError(
                    f"gate {gate['key']} {field}={gate[field]!r} does not match "
                    f"the canonical {canonical[field]!r}")

    bridges = data.get("bridges", [])
    if len(bridges) != 36:
        raise ValueError(f"expected 36 bridges, got {len(bridges)}")

    seen_pairs: set[tuple[str, str]] = set()
    seen_roots: set[str] = set()
    for bridge in bridges:
        pair = bridge.get("gates", [])
        if len(pair) != 2:
            raise ValueError(f"bridge needs exactly 2 gates: {bridge}")
        key = bridge_key(*pair)
        if tuple(pair) != key:
            raise ValueError(
                f"bridge gates {pair} are not in canonical order {list(key)}")
        if key in seen_pairs:
            raise ValueError(f"duplicate bridge for gate pair: {key}")
        seen_pairs.add(key)
        root = bridge.get("root")
        if not root:
            raise ValueError(f"bridge missing root: {bridge}")
        if root in seen_roots:
            raise ValueError(f"root assigned to more than one bridge: {root}")
        seen_roots.add(root)

    missing_pairs = set(all_bridge_keys()) - seen_pairs
    if missing_pairs:
        raise ValueError(f"gate pairs with no bridge: {sorted(missing_pairs)}")

    if known_roots is not None:
        unknown = seen_roots - known_roots
        if unknown:
            raise ValueError(f"bridges reference unknown roots: {sorted(unknown)}")
        unmapped = known_roots - seen_roots
        if unmapped:
            raise ValueError(f"roots with no bridge: {sorted(unmapped)}")


def bridges_by_root(data: dict) -> dict[str, tuple[str, str]]:
    """root slug -> canonical gate pair."""
    return {b["root"]: bridge_key(*b["gates"]) for b in data["bridges"]}


def bridges_by_pair(data: dict) -> dict[tuple[str, str], str]:
    """canonical gate pair -> root slug."""
    return {bridge_key(*b["gates"]): b["root"] for b in data["bridges"]}


def main() -> int:
    numbers = sorted(KING_WEN.values())
    assert numbers == list(range(1, 65)), "King Wen table is not a bijection"
    data = load_navigation()
    print(f"navigation OK — {len(data['gates'])} gates, {len(data['bridges'])} bridges")
    for lower, upper in all_bridge_keys():
        n = hexagram_number(lower, upper)
        print(f"  {GATE_BY_KEY[lower]['symbol']}{GATE_BY_KEY[upper]['symbol']} "
              f"{glyph(n)} {n:>2}  {bridges_by_pair(data)[(lower, upper)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
