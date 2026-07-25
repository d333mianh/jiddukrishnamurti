from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_citations as bc  # noqa: E402
import build_concept_vault as bcv  # noqa: E402

CITE_URL = re.compile(r"^https://youtu\.be/[\w-]+\?t=\d+$")


class CitationDataTests(unittest.TestCase):
    """The shipped citation file must stand on its own.

    `corpus/krishnamurti-corpus.db` is gitignored, so a fresh clone can only
    rebuild the vault if every citation already carries its quote and link.
    These tests therefore read the tracked JSONL and never the corpus."""

    def setUp(self) -> None:
        self.cites = bc.load()

    def test_every_citation_is_resolved_and_quotable(self) -> None:
        for cite in self.cites:
            with self.subTest(slug=cite["slug"], seq=cite["seq"]):
                for field in bc.KEY_FIELDS + bc.RESOLVED_FIELDS:
                    self.assertIn(field, cite)
                self.assertTrue(cite["text"].strip())
                self.assertRegex(cite["url"], CITE_URL)

    def test_link_offset_matches_the_passage_start(self) -> None:
        """The `?t=` in the URL is the claim being published — if it drifts
        from the passage it was drawn from, the citation points somewhere the
        quoted words are not spoken."""
        for cite in self.cites:
            with self.subTest(slug=cite["slug"], seq=cite["seq"]):
                offset = int(cite["url"].rsplit("=", 1)[1])
                self.assertEqual(int(cite["t_start"]), offset)
                self.assertLess(cite["t_start"], cite["t_end"])

    def test_seq_is_unique_and_themes_stay_contiguous(self) -> None:
        """Themes render as headings in file order, so a theme that reappears
        after another would emit the same heading twice."""
        for slug, cites in bc.by_concept(self.cites).items():
            with self.subTest(slug=slug):
                seqs = [c["seq"] for c in cites]
                self.assertEqual(len(seqs), len(set(seqs)))
                order = [c["theme"] for c in cites]
                runs = [t for i, t in enumerate(order) if i == 0 or order[i - 1] != t]
                self.assertEqual(len(runs), len(set(runs)))

    def test_citations_point_at_catalogued_items(self) -> None:
        for cite in self.cites:
            self.assertRegex(cite["item_code"], r"^[A-Z0-9.]+$")


class CitationRenderTests(unittest.TestCase):
    def test_render_groups_by_theme_and_links_every_quote(self) -> None:
        cites = [
            {"slug": "x", "theme": "One", "seq": 1, "item_code": "AA70T1",
             "t_start": 10.0, "t_end": 20.0, "title": "First", "year": 1970,
             "timecode": "0:00:10", "url": "https://youtu.be/aaa?t=10",
             "text": "alpha"},
            {"slug": "x", "theme": "One", "seq": 2, "item_code": "BB71T1",
             "t_start": 30.0, "t_end": 40.0, "title": "Second", "year": 1971,
             "timecode": "0:00:30", "url": "https://youtu.be/bbb?t=30",
             "text": "beta"},
            {"slug": "x", "theme": "Two", "seq": 3, "item_code": "CC72T1",
             "t_start": 50.0, "t_end": 60.0, "title": "Third", "year": 1972,
             "timecode": "0:00:50", "url": "https://youtu.be/ccc?t=50",
             "text": "gamma"},
        ]
        out = "\n".join(bcv.render_citations(cites))
        self.assertEqual(1, out.count("### One"))
        self.assertEqual(1, out.count("### Two"))
        self.assertIn("3 passages, 1970–1972", out)
        for cite in cites:
            self.assertIn(f"> {cite['text']}", out)
            self.assertIn(cite["url"], out)

    def test_unresolved_citation_is_skipped_not_crashed_on(self) -> None:
        """A line added by hand has no quote until --sync runs; regenerating the
        vault in between must not fail."""
        self.assertEqual([], bcv.render_citations(
            [{"slug": "x", "theme": "One", "seq": 1, "item_code": "AA70T1",
              "t_start": 10}]))

    def test_no_concept_citations_render_no_section(self) -> None:
        self.assertEqual([], bcv.render_citations([]))


class CitationVaultTests(unittest.TestCase):
    def test_cited_notes_carry_their_links_and_stay_generated(self) -> None:
        outputs = dict(bcv.build())
        for slug, cites in bc.by_concept(bc.load()).items():
            note = bcv.CONCEPTS_DIR / f"{slug}.md"
            with self.subTest(slug=slug):
                self.assertIn(note, outputs)
                text = outputs[note]
                self.assertIn("## In K's words", text)
                self.assertIn("concepts/citations.jsonl", text)
                for cite in cites:
                    self.assertIn(cite["url"], text)


if __name__ == "__main__":
    unittest.main()
