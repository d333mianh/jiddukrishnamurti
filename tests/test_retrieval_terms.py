"""Guards on how a concept's BM25 query is built.

Query terms come from splitting the registry's `name` and aliases into words.
Until 2026-08-03 that kept the function words inside multi-word forms, so
`beauty` searched on `the` and returned 30,774 candidates against the 2,066 that
contain a word meaning beauty, and `truth` searched on `what`. Twenty of the 36
roots were retrieving essentially the whole corpus.

Dropping function words is safe; dropping *frequent* words is not, and the two
are easy to confuse. `right` appears in 21% of K-passages and `mind` in 10%, and
both discriminate. `will` appears in 12% as the auxiliary verb and is also
`will-effort`'s own name, where it means volition — so the rule is not a
frequency cut but a closed-class list, with anything the registry states as a
form in its own right protected from it.

These tests hold that distinction, since losing it silently deletes a root's
own vocabulary.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import retrieve_concept as rc  # noqa: E402

HAVE_CORPUS = rc.CORPUS_DB.exists()

# A stopword must be worth dropping. The least frequent one sits near 6% of
# K-passages; this floor is well below that and well above `fear` (5%), so it
# fails if a discriminating word is ever added to the list.
MIN_STOPWORD_SHARE = 0.04


def active_concepts() -> list[dict]:
    return [c for c in
            (json.loads(l) for l in rc.REGISTRY.read_text(encoding="utf-8").splitlines()
             if l.strip())
            if c.get("status") == "active"]


class QueryTermTests(unittest.TestCase):
    def test_function_words_inside_a_phrase_are_dropped(self) -> None:
        """`freedom from the known` must not put the corpus's two commonest
        words into an OR query."""
        terms = rc.fts_terms(rc.load_concept("freedom"), [])
        self.assertIn("freedom", terms)
        self.assertIn("known", terms)
        for stop in ("from", "the"):
            self.assertNotIn(stop, terms)

    def test_a_word_the_registry_names_on_its_own_survives(self) -> None:
        """`will` is a stopword and `will-effort`'s own name. The registry
        stating it alone is the claim that it carries the concept — stripping it
        would delete the root's subject to save a frequent token."""
        self.assertIn("will", rc.STOPWORDS)
        self.assertIn("will", rc.fts_terms(rc.load_concept("will-effort"), []))

    def test_hand_picked_terms_are_taken_at_face_value(self) -> None:
        """`--terms` exists because K's vocabulary shifts by decade. A curator
        passing a word has already made the judgment this filter automates."""
        self.assertIn("the", rc.fts_terms(rc.load_concept("freedom"), ["the"]))

    def test_every_active_root_still_has_a_query(self) -> None:
        """A root filtered down to nothing would retrieve nothing, and the recall
        gate would not notice for any root that has no citations yet."""
        for concept in active_concepts():
            with self.subTest(slug=concept["slug"]):
                self.assertTrue(rc.fts_terms(concept, []))

    def test_terms_are_unique_and_long_enough(self) -> None:
        for concept in active_concepts():
            with self.subTest(slug=concept["slug"]):
                terms = rc.fts_terms(concept, [])
                self.assertEqual(len(terms), len(set(terms)))
                self.assertTrue(all(len(t) >= 3 for t in terms))


@unittest.skipUnless(HAVE_CORPUS, "corpus DB absent — see corpus/README.md")
class StopwordListTests(unittest.TestCase):
    def test_every_stopword_is_actually_ubiquitous(self) -> None:
        """The list may only hold words too common to discriminate. This is what
        stops it becoming a place to quietly suppress inconvenient terms: a word
        that fails this bar does not belong in it, whatever it looks like."""
        conn = sqlite3.connect(f"file:{rc.CORPUS_DB}?mode=ro", uri=True)
        try:
            total = conn.execute("SELECT count(*) FROM passages_fts").fetchone()[0]
            for word in sorted(rc.STOPWORDS):
                with self.subTest(word=word):
                    n = conn.execute(
                        "SELECT count(*) FROM passages_fts WHERE passages_fts MATCH ?",
                        (f"{word}*",)).fetchone()[0]
                    self.assertGreater(
                        n / total, MIN_STOPWORD_SHARE,
                        f"{word!r} matches only {100 * n / total:.1f}% of "
                        f"K-passages — too discriminating to drop")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
