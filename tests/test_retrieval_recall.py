"""The gate on retrieval: a query change may not lose passages already judged.

`P-retrieval` exists because two defects were found by hand while curating, and
the fix that seemed obvious for the first — stripping stopwords out of the BM25
query — turned out to move the top 60 by a mean of 4.5 passages, while the next
idea after it, treating multi-word aliases as FTS5 phrases, would have dropped
15 of `observer-observed`'s 30 curated passages. Both facts were invisible
because nothing measured retrieval against anything.

The 83 curated citations are the gold set: a human read each passage and kept
it. So the invariant is that retrieval at the CLI's own defaults still puts
every one of them in front of the curator. It strengthens on its own — each new
cited root adds its keepers to the set that any future query change must clear.

`test_no_item_exceeds_the_per_item_cap` reads only tracked data and so runs
anywhere; the recall gate needs the gitignored corpus and skips without it (see
corpus/README.md for the restore).
"""

from __future__ import annotations

import collections
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_citations as bc  # noqa: E402
import retrieval_report as rr  # noqa: E402
import retrieve_concept as rc  # noqa: E402

HAVE_CORPUS = rc.CORPUS_DB.exists()

# Citations that retrieval genuinely cannot reach, each with the reason it is
# tolerated. Empty, and adding to it should be a deliberate act: an entry here
# says the curator found a passage the registry's own vocabulary cannot, which
# is the alias-coverage defect `P-retrieval` is about — usually the right fix is
# an alias, not an exemption.
KNOWN_UNREACHABLE: dict[tuple[str, int], str] = {}


class PerItemCapTests(unittest.TestCase):
    """A structural precondition, checkable without the corpus."""

    def test_no_item_exceeds_the_per_item_cap(self) -> None:
        """`--per-item` caps how many passages one recording contributes. Curate
        more keepers than that from a single talk and retrieval can never show
        them all again, so the note cannot be rebuilt from its own candidates."""
        counts = collections.Counter(
            (c["slug"], c["item_code"]) for c in bc.load())
        over = {k: n for k, n in counts.items() if n > rr.DEFAULT_PER_ITEM}
        self.assertEqual(
            {}, over,
            f"more than --per-item {rr.DEFAULT_PER_ITEM} citations from one "
            f"recording: {over}")


@unittest.skipUnless(HAVE_CORPUS, "corpus DB absent — see corpus/README.md")
class RetrievalRecallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        conn = rc.connect()
        try:
            cls.results = [
                rr.measure(conn, slug, cites, rr.DEFAULT_LIMIT,
                           rr.DEFAULT_PER_ITEM, rr.DEFAULT_MIN_WORDS)
                for slug, cites in sorted(bc.by_concept(bc.load()).items())
            ]
        finally:
            conn.close()

    def test_every_curated_passage_is_still_retrievable(self) -> None:
        """The gate. A miss names the root, the passage and the cause."""
        for result in self.results:
            with self.subTest(slug=result["slug"]):
                unexpected = [
                    m for m in result["missing"]
                    if (result["slug"], m["seq"]) not in KNOWN_UNREACHABLE
                ]
                self.assertEqual(
                    [], unexpected,
                    f"{result['slug']}: retrieval no longer reaches "
                    + ", ".join(f"#{m['seq']} {m['item_code']}"
                                f"@{int(m['t_start'])} ({m['reason']})"
                                for m in unexpected))

    def test_the_gold_set_is_not_empty(self) -> None:
        """A measurement over nothing passes trivially; this fails loudly if the
        citations stop loading or the roots stop resolving."""
        self.assertTrue(self.results)
        self.assertTrue(all(r["cited"] for r in self.results))

    def test_every_root_query_draws_on_the_registry(self) -> None:
        """Terms come from `name` + aliases. A query built from nothing would
        retrieve nothing and make the recall gate meaningless."""
        for result in self.results:
            with self.subTest(slug=result["slug"]):
                self.assertTrue(result["terms"])


if __name__ == "__main__":
    unittest.main()
