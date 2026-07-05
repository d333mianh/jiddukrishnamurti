from __future__ import annotations

import contextlib
import io
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from segment_schema import (  # noqa: E402
    corpus_tier_for_event_type,
    ensure_corpus_schema,
    ensure_corpus_tiers,
)


class SegmentSchemaTests(unittest.TestCase):
    def test_event_type_mapping(self) -> None:
        tier_a = ("T", "TS", "TSS", "TYP", "TR", "Q", "S", "SBR",
                  "D", "DT", "DS", "DSS")
        tier_b = ("C", "CCT", "I", "IFV", "DSG", "DYP", "DCO", "DTV",
                  "WOL", "HF")
        tier_c = ("F", "FQA", "FTPL")
        for tier, event_types in (("A", tier_a), ("B", tier_b), ("C", tier_c)):
            for event_type in event_types:
                with self.subTest(event_type=event_type):
                    self.assertEqual(tier, corpus_tier_for_event_type(event_type))
        self.assertEqual("X", corpus_tier_for_event_type("EBM"))
        self.assertEqual("B", corpus_tier_for_event_type("NEW"))

    def test_tier_population_warns_for_default_b_and_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE items (id INTEGER PRIMARY KEY, event_type TEXT)"
        )
        conn.executemany(
            "INSERT INTO items(event_type) VALUES(?)",
            [("T",), ("FQA",), ("EBM",), ("NEW",)],
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ensure_corpus_tiers(conn)
            ensure_corpus_tiers(conn)
        self.assertIn("NEW", output.getvalue())
        self.assertEqual(
            [("T", "A", 1), ("FQA", "C", 1), ("EBM", "X", 0),
             ("NEW", "B", 1)],
            conn.execute(
                "SELECT event_type,corpus_tier,corpus_include FROM items ORDER BY id"
            ).fetchall(),
        )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(items)")]
        self.assertEqual(1, columns.count("corpus_tier"))
        self.assertEqual(1, columns.count("corpus_include"))
        conn.close()

    def test_corpus_tier_column_add_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        ensure_corpus_schema(conn)
        ensure_corpus_schema(conn)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(transcripts)")]
        self.assertEqual(1, columns.count("corpus_tier"))
        conn.close()


if __name__ == "__main__":
    unittest.main()
