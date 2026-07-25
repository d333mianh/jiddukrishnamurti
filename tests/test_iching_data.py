from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import iching_data as ich  # noqa: E402

CONCEPTS_JSONL = ROOT / "concepts" / "concepts.jsonl"


def live_roots() -> set[str]:
    rows = [json.loads(line) for line in
            CONCEPTS_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["slug"] for r in rows if r["status"] != "deprecated"}


class TestKingWen(unittest.TestCase):
    def test_table_is_a_bijection_onto_1_to_64(self):
        self.assertEqual(sorted(ich.KING_WEN.values()), list(range(1, 65)))
        self.assertEqual(len(ich.KING_WEN), 64)

    def test_anchor_hexagrams(self):
        # Spot-checks against the standard arrangement, including the two
        # hexagrams Allan W. Anderson actually cites in the archive: 25
        # (Innocence / The Unexpected, SD72CA1) and 10 (Treading / conduct,
        # SD74CA5).
        anchors = {
            ("qian", "qian"): 1, ("kun", "kun"): 2, ("qian", "kun"): 11,
            ("kun", "qian"): 12, ("kan", "kan"): 29, ("li", "li"): 30,
            ("zhen", "zhen"): 51, ("gen", "gen"): 52, ("xun", "xun"): 57,
            ("dui", "dui"): 58, ("zhen", "qian"): 25, ("dui", "qian"): 10,
            ("li", "kan"): 63, ("kan", "li"): 64, ("qian", "dui"): 43,
        }
        for (lower, upper), number in anchors.items():
            self.assertEqual(ich.hexagram_number(lower, upper), number,
                             f"{lower} under {upper}")

    def test_unknown_gate_pair_raises(self):
        with self.assertRaises(KeyError):
            ich.hexagram_number("qian", "not-a-gate")

    def test_glyph_indexes_the_unicode_block(self):
        self.assertEqual(ich.glyph(1), "䷀")
        self.assertEqual(ich.glyph(64), "䷿")
        self.assertEqual(ich.hexagram_glyph("qian", "kun"), ich.glyph(11))
        for bad in (0, 65, -1):
            with self.assertRaises(ValueError):
                ich.glyph(bad)

    def test_every_glyph_is_distinct(self):
        glyphs = {ich.glyph(n) for n in range(1, 65)}
        self.assertEqual(len(glyphs), 64)


class TestGates(unittest.TestCase):
    def test_eight_distinct_gates(self):
        self.assertEqual(len(ich.GATES), 8)
        for field in ("key", "symbol", "lines", "name"):
            self.assertEqual(len({g[field] for g in ich.GATES}), 8, field)

    def test_line_patterns_cover_all_three_bit_values(self):
        self.assertEqual(sorted(g["lines"] for g in ich.GATES),
                         [f"{n:03b}" for n in range(8)])

    def test_bridge_key_is_order_independent_and_canonical(self):
        self.assertEqual(ich.bridge_key("kun", "qian"), ("qian", "kun"))
        self.assertEqual(ich.bridge_key("qian", "kun"), ("qian", "kun"))
        self.assertEqual(ich.bridge_key("dui", "dui"), ("dui", "dui"))
        with self.assertRaises(KeyError):
            ich.bridge_key("qian", "nope")

    def test_thirty_six_bridges_split_8_self_and_28_pairs(self):
        keys = ich.all_bridge_keys()
        self.assertEqual(len(keys), 36)
        self.assertEqual(len(set(keys)), 36)
        self.assertEqual(sum(1 for a, b in keys if a == b), 8)
        self.assertEqual(sum(1 for a, b in keys if a != b), 28)

    def test_all_64_ordered_figures_resolve_to_a_bridge(self):
        bridges = set(ich.all_bridge_keys())
        seen = set()
        for lower in ich.GATE_ORDER:
            for upper in ich.GATE_ORDER:
                key = ich.bridge_key(lower, upper)
                self.assertIn(key, bridges)
                seen.add(key)
        self.assertEqual(seen, bridges)


class TestLinesToGates(unittest.TestCase):
    def test_odd_is_solid_even_is_broken(self):
        self.assertEqual(ich.lines_to_gates([7, 7, 7, 7, 7, 7]), ("qian", "qian"))
        self.assertEqual(ich.lines_to_gates([8, 8, 8, 8, 8, 8]), ("kun", "kun"))
        # Moving lines (6 = old yin, 9 = old yang) read by parity like the rest.
        self.assertEqual(ich.lines_to_gates([9, 9, 9, 6, 6, 6]), ("qian", "kun"))

    def test_lower_gate_is_lines_1_to_3(self):
        # 100 = zhen (lower), 010 = kan (upper).
        self.assertEqual(ich.lines_to_gates([7, 8, 8, 8, 7, 8]), ("zhen", "kan"))

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            ich.lines_to_gates([7, 7, 7])
        with self.assertRaises(ValueError):
            ich.lines_to_gates([7, 7, 7, 7, 7, 5])


class TestNavigation(unittest.TestCase):
    def setUp(self):
        self.data = ich.load_navigation()

    def test_shipped_navigation_matches_the_live_registry(self):
        ich.validate_navigation(self.data, known_roots=live_roots())

    def test_every_root_has_exactly_one_bridge_and_vice_versa(self):
        by_root = ich.bridges_by_root(self.data)
        by_pair = ich.bridges_by_pair(self.data)
        self.assertEqual(len(by_root), 36)
        self.assertEqual(len(by_pair), 36)
        self.assertEqual(set(by_pair), set(ich.all_bridge_keys()))
        self.assertEqual(set(by_root), live_roots())
        for root, pair in by_root.items():
            self.assertEqual(by_pair[pair], root)

    def test_every_bridge_carries_a_note(self):
        for bridge in self.data["bridges"]:
            self.assertTrue(bridge.get("note", "").strip(), bridge)

    def test_layer_is_marked_navigation_only(self):
        self.assertEqual(self.data["status"], "provisional")

    def _broken(self, mutate):
        data = copy.deepcopy(self.data)
        mutate(data)
        with self.assertRaises(ValueError):
            ich.validate_navigation(data, known_roots=live_roots())

    def test_validation_rejects_broken_invariants(self):
        self._broken(lambda d: d["gates"].pop())
        self._broken(lambda d: d["bridges"].pop())
        self._broken(lambda d: d["gates"][0].__setitem__("lines", "000"))
        self._broken(lambda d: d["gates"][0].__setitem__("key", "invented"))
        # duplicate root across two bridges
        self._broken(lambda d: d["bridges"][1].__setitem__(
            "root", d["bridges"][0]["root"]))
        # gate pair written in non-canonical order
        self._broken(lambda d: d["bridges"][1].__setitem__(
            "gates", list(reversed(d["bridges"][1]["gates"]))))
        # a root the registry does not know
        self._broken(lambda d: d["bridges"][0].__setitem__("root", "ghost-root"))
        self._broken(lambda d: d["bridges"][0].pop("root"))

    def test_reversed_self_pair_is_not_rejected(self):
        # A self-pair reversed is still canonical — guard against an
        # over-eager ordering check.
        data = copy.deepcopy(self.data)
        for bridge in data["bridges"]:
            if bridge["gates"][0] == bridge["gates"][1]:
                bridge["gates"] = list(reversed(bridge["gates"]))
        ich.validate_navigation(data, known_roots=live_roots())


if __name__ == "__main__":
    unittest.main()
