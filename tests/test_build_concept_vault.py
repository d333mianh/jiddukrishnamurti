from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_concept_vault as bcv  # noqa: E402
import iching_data as ich  # noqa: E402


class TestVaultBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = bcv.build()
        cls.by_path = dict(cls.outputs)
        cls.concepts = {c["slug"]: c for c in bcv.load_concepts()}

    def test_writes_36_concepts_plus_map_navigator_and_8_gates(self):
        self.assertEqual(len(self.outputs), 36 + 1 + 1 + 8)
        self.assertEqual(len(self.concepts), 36)
        self.assertIn(bcv.MAP_NOTE, self.by_path)
        self.assertIn(bcv.NAVIGATOR_NOTE, self.by_path)
        for key in ich.GATE_ORDER:
            self.assertIn(bcv.GATES_DIR / f"{key}.md", self.by_path)

    def test_registry_is_closed_so_no_status_badges_remain(self):
        self.assertTrue(all(c["status"] == "active" for c in self.concepts.values()))
        self.assertFalse(hasattr(bcv, "STATUS_NOTES"))
        map_text = self.by_path[bcv.MAP_NOTE]
        for badge in ("**pilot**", "**new root**", "**merged root**",
                      "probation"):
            self.assertNotIn(badge, map_text)

    def test_every_facet_slug_exists_and_facets_partition_the_roots(self):
        placed = [s for _, _, slugs in bcv.FACETS for s in slugs]
        self.assertEqual(len(placed), 36)
        self.assertEqual(set(placed), set(self.concepts))
        self.assertEqual(len(bcv.FACETS), 4)

    def test_concept_notes_carry_their_gate_pair(self):
        by_root = ich.bridges_by_root(ich.load_navigation())
        for slug, pair in by_root.items():
            text = self.by_path[bcv.CONCEPTS_DIR / f"{slug}.md"]
            self.assertIn(f"iching_gates: [{pair[0]}, {pair[1]}]", text)
            symbols = "".join(ich.GATE_BY_KEY[k]["symbol"] for k in pair)
            self.assertIn(f"I Ching bridge — {symbols}", text)
            self.assertIn("*(navigation only)*", text)

    def test_two_gate_bridges_show_both_figures_self_pairs_one(self):
        self.assertEqual(bcv.bridge_figures(("kan", "kan")), "䷜ 29")
        self.assertEqual(bcv.bridge_figures(("qian", "kun")), "䷊ 11 / ䷋ 12")

    def test_short_name_trims_compound_titles(self):
        self.assertEqual(bcv.short_name("Thought & Knowledge"), "Thought")
        self.assertEqual(bcv.short_name("Division / Fragmentation"), "Division")
        self.assertEqual(bcv.short_name("Suffering (Sorrow)"), "Suffering")
        self.assertEqual(bcv.short_name("Action"), "Action")

    def test_navigator_is_framed_as_navigation_not_prophecy(self):
        text = self.by_path[bcv.NAVIGATOR_NOTE]
        self.assertIn("Navigator, not oracle", text)
        self.assertIn("provisional", text)
        # The matrix is the actual lookup table: 8 data rows, 64 cells.
        rows = [ln for ln in text.splitlines() if ln.startswith("| **")]
        self.assertEqual(len(rows), 8)
        for row in rows:
            # Wikilink aliases escape their pipe, so only unescaped pipes are
            # cell separators.
            cells = re.split(r"(?<!\\)\|", row)
            self.assertEqual(len(cells) - 2, 9, row)  # row label + 8 cells
        for code, video, _title, seconds, _gloss in bcv.ARCHIVE_GROUNDING:
            self.assertIn(f"https://youtu.be/{video}?t={seconds}", text)
            self.assertIn(code, text)

    def test_generated_notes_declare_they_are_generated(self):
        for path, text in self.outputs:
            self.assertIn("build_concept_vault.py", text, path.name)

    def test_wikilink_targets_all_resolve(self):
        self.assertEqual(bcv.dead_wikilinks(self.outputs), [])

    def test_dead_wikilink_detection_actually_fires(self):
        broken = list(self.outputs)
        broken.append((bcv.VAULT / "__probe__.md", "see [[no-such-note]]\n"))
        dead = bcv.dead_wikilinks(broken)
        self.assertEqual([t for _, t in dead], ["no-such-note"])

    def test_check_mode_passes_against_the_committed_vault(self):
        self.assertEqual(bcv.main(["--check"]), 0)

    def test_notes_are_idempotent(self):
        self.assertEqual(bcv.build(), self.outputs)


class TestConceptJsonlIntegrity(unittest.TestCase):
    def test_slugs_unique_and_relations_resolve(self):
        rows = [json.loads(line) for line in
                bcv.CONCEPTS_JSONL.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        slugs = [r["slug"] for r in rows]
        self.assertEqual(len(slugs), len(set(slugs)))
        known = set(slugs)  # relations may point at deprecated tombstones
        for row in rows:
            for rel in row.get("relations", []):
                self.assertIn(rel["to"], known, f"{row['slug']} -> {rel['to']}")

    def test_exactly_36_live_roots(self):
        rows = [json.loads(line) for line in
                bcv.CONCEPTS_JSONL.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        live = [r for r in rows if r["status"] != "deprecated"]
        self.assertEqual(len(live), 36)
        self.assertTrue(all(r["status"] == "active" for r in live))


if __name__ == "__main__":
    unittest.main()
