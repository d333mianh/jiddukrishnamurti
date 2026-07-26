from __future__ import annotations

import hashlib
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


class CorpusSnapshotTests(unittest.TestCase):
    """The tracked snapshot is what makes a clone able to run phase 3.

    It is the one generated artifact deliberately kept in git, held there by a
    `!` negation in `.gitignore` — a rule that is easy to undo by accident while
    tidying ignore patterns. These checks are cheap (a header read, not a
    decompression) and fail loudly if the snapshot stops shipping."""

    SNAPSHOT = ROOT / "corpus" / "krishnamurti-corpus.db.zst"
    ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

    def test_snapshot_ships_and_is_a_zstd_stream(self) -> None:
        self.assertTrue(self.SNAPSHOT.exists(),
                        f"{self.SNAPSHOT} is missing — see corpus/README.md")
        with self.SNAPSHOT.open("rb") as fh:
            self.assertEqual(self.ZSTD_MAGIC, fh.read(4))

    def test_snapshot_stays_under_the_github_file_limit(self) -> None:
        """GitHub hard-rejects a push containing a file over 100 MB."""
        self.assertLess(self.SNAPSHOT.stat().st_size, 100 * 1024 * 1024)

    def test_snapshot_checksum_is_recorded_and_matches(self) -> None:
        sums = self.SNAPSHOT.with_suffix(".zst.sha256")
        self.assertTrue(sums.exists(), f"{sums} is missing")
        recorded = sums.read_text(encoding="utf-8").split()[0]
        digest = hashlib.sha256()
        with self.SNAPSHOT.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        self.assertEqual(recorded, digest.hexdigest(),
                         "snapshot and checksum disagree — refresh both together")

    def test_restore_path_is_documented(self) -> None:
        for doc in (ROOT / "CLAUDE.md", ROOT / "corpus" / "README.md"):
            with self.subTest(doc=doc.name):
                self.assertIn("krishnamurti-corpus.db.zst",
                              doc.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
