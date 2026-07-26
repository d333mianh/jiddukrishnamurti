from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import strategy_stats as ss  # noqa: E402

STRATEGY = ROOT / "STRATEGY.md"

# A slug is *defined* by a backticked slug followed by an em dash: the shape
# every phase and question entry uses. Anywhere else, it is a reference.
DEFINITION = re.compile(r"`([QP]-[a-z][a-z-]*)` —")
REFERENCE = re.compile(r"`([QP]-[a-z][a-z-]*)`")
POSITIONAL = re.compile(r"open questions? \d|\bphases? \d", re.IGNORECASE)
QUOTED = re.compile(r'"[^"]*"')


def sections(text: str) -> dict[str, str]:
    """Split the document on its `## ` headings."""
    found: dict[str, str] = {}
    name = "(preamble)"
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            found[name] = "\n".join(body)
            name, body = line[3:].strip(), []
        else:
            body.append(line)
    found[name] = "\n".join(body)
    return found


class StrategyDocTests(unittest.TestCase):
    """STRATEGY.md carries cross-references, and cross-references rot.

    Four of them had rotted by 2026-07-26 — questions were referenced by
    position, answering one renumbered the rest, and two different questions had
    each been "open question 4". Slugs fixed that; these tests are what keeps it
    fixed, and they cost nothing because the document is tracked text."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = STRATEGY.read_text(encoding="utf-8")
        cls.sections = sections(cls.text)

    def test_generated_block_has_exactly_one_pair_of_markers(self) -> None:
        """`strategy_stats.py` splices between these; a second pair would make
        it silently rewrite the wrong span."""
        self.assertEqual(self.text.count(ss.BEGIN), 1)
        self.assertEqual(self.text.count(ss.END), 1)
        self.assertLess(self.text.index(ss.BEGIN), self.text.index(ss.END))
        self.assertIn(ss.BEGIN, self.sections["Where things stand"])

    def test_reading_table_matches_the_actual_headings(self) -> None:
        """The 'how to read this file' table once promised four sections while
        the file had eight. If it describes the document, it must be checkable."""
        anchors = set(re.findall(r"\]\(#([a-z-]+)\)", self.sections["(preamble)"]))
        headings = {name.lower().replace(" ", "-") for name in self.sections}
        self.assertTrue(anchors)
        self.assertEqual(anchors - headings, set())

    def test_every_slug_reference_resolves(self) -> None:
        defined = set(DEFINITION.findall(self.text))
        referenced = set(REFERENCE.findall(self.text))
        self.assertTrue(defined, "no phase or question definitions found")
        self.assertEqual(
            referenced - defined, set(),
            "referenced but never defined — a deleted entry left danglers behind")

    def test_slugs_are_defined_in_the_section_that_owns_them(self) -> None:
        for slug in DEFINITION.findall(self.text):
            owner = "Open questions" if slug.startswith("Q-") else "Plan"
            with self.subTest(slug=slug):
                self.assertIn(f"`{slug}` —", self.sections[owner])

    def test_nothing_is_referenced_by_position(self) -> None:
        """Positional references are the failure this file already had. The log
        may describe history, but it may not point at a number that moves.

        Double-quoted spans are exempt: the preamble and the log both *quote*
        the old form to explain what went wrong, which is a mention, not a
        reference. Anything outside quotes is pointing at something."""
        self.assertEqual(POSITIONAL.findall(QUOTED.sub('""', self.text)), [])


if __name__ == "__main__":
    unittest.main()
