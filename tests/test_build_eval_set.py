from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_eval_set.py"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from concept_schema import ensure_concept_schema  # noqa: E402
from segment_schema import ensure_corpus_schema, utc_now  # noqa: E402


class BuildEvalSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "corpus.db"
        self.catalog = self.root / "catalog.db"
        self.export = self.root / "eval.jsonl"
        self._build_catalog()
        self._build_corpus()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build_catalog(self) -> None:
        with sqlite3.connect(self.catalog) as conn:
            conn.execute(
                "CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT UNIQUE, "
                "year INTEGER, event_type TEXT)"
            )
            conn.executemany(
                "INSERT INTO items(code,year,event_type) VALUES(?,?,?)",
                [
                    ("AA61T1", 1961, "T"),
                    ("BB62Q1", 1962, "Q"),
                    ("CC74D1", 1974, "D"),
                    ("DD75D1", 1975, "D"),
                    ("EE80F1", 1980, "F"),
                ],
            )

    def _build_corpus(self) -> None:
        with sqlite3.connect(self.db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            ensure_corpus_schema(conn)
            ensure_concept_schema(conn)
            now = utc_now()
            specs = [
                ("AA61T1", "T", "A", "manual", 0, 6),
                ("BB62Q1", "Q", "A", "manual", 1, 4),
                ("CC74D1", "D", "B", "manual", 0, 5),
                ("DD75D1", "D", "B", "whisper", 0, 3),
                ("EE80F1", "F", "C", "manual", 0, 3),
            ]
            for code, event_type, tier, kind, synthetic, count in specs:
                cursor = conn.execute(
                    """INSERT INTO transcripts(
                           item_code,event_type,corpus_tier,kind,language,source_path,
                           resolved_via,parser_version,parsed_at
                       ) VALUES(?,?,?,?,?,'test','test','test-parser',?)""",
                    (code, event_type, tier, kind, "en", now),
                )
                transcript_id = int(cursor.lastrowid)
                for seq in range(count):
                    segment = conn.execute(
                        """INSERT INTO segments(
                               transcript_id,item_code,seq,speaker_code,t_start,t_end,
                               timestamps_synthetic,text,word_count,attribution
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (transcript_id, code, seq, "K", seq * 10, seq * 10 + 9,
                         synthetic, f"segment {code} {seq}", 3,
                         "q_boundary_heuristic" if seq == 0 else "label"),
                    )
                    conn.execute(
                        """INSERT INTO passages(
                               transcript_id,segment_id,item_code,seq,speaker_code,
                               t_start,t_end,timestamps_synthetic,text,word_count,attribution
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (transcript_id, int(segment.lastrowid), code, seq, "K",
                         seq * 10, seq * 10 + 9, synthetic,
                         f"passage text {code} {seq}", 4,
                         "q_boundary_heuristic" if seq == 0 else "label"),
                    )

    def run_script(self, name: str, *extra: str, export: Path | None = None):
        target = export or self.export
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--name", name, "--size", "9",
             "--seed", "17", "--db", str(self.db), "--catalog", str(self.catalog),
             "--export", str(target), *extra],
            text=True, capture_output=True,
        )

    def query(self, sql: str, params=()):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql, params).fetchall()

    def test_same_seed_selects_identical_passages_and_export_has_no_text(self) -> None:
        first = self.run_script("pilot-one")
        self.assertEqual(0, first.returncode, first.stderr)
        first_rows = [json.loads(line) for line in self.export.read_text().splitlines()]
        second_export = self.root / "second.jsonl"
        second = self.run_script("pilot-two", export=second_export)
        self.assertEqual(0, second.returncode, second.stderr)
        second_rows = [json.loads(line) for line in second_export.read_text().splitlines()]
        self.assertEqual(first_rows, second_rows)
        self.assertTrue(all("text" not in row for row in first_rows))
        self.assertTrue(all(len(row["text_sha256"]) == 64 for row in first_rows))

    def test_weights_sum_to_frame_and_heuristic_attribution_is_included(self) -> None:
        result = self.run_script("weights")
        self.assertEqual(0, result.returncode, result.stderr)
        weight_sum = self.query(
            """SELECT sum(ep.sample_weight)
               FROM eval_set_passages ep JOIN eval_sets es ON es.id=ep.eval_set_id
               WHERE es.name='weights'"""
        )[0][0]
        self.assertAlmostEqual(15.0, weight_sum)
        attributions = self.query(
            "SELECT DISTINCT attribution FROM passage_anchors ORDER BY attribution"
        )
        self.assertIn(("q_boundary_heuristic",), attributions)

    def test_anchor_upsert_does_not_duplicate_for_another_set(self) -> None:
        self.assertEqual(0, self.run_script("first").returncode)
        count = self.query("SELECT count(*) FROM passage_anchors")[0][0]
        self.assertEqual(0, self.run_script("second").returncode)
        self.assertEqual(count, self.query("SELECT count(*) FROM passage_anchors")[0][0])
        self.assertEqual(18, self.query("SELECT count(*) FROM eval_set_passages")[0][0])

    def test_dry_run_writes_nothing(self) -> None:
        before = {
            table: self.query(f"SELECT * FROM {table}")
            for table in ("passage_anchors", "eval_sets", "eval_set_passages")
        }
        result = self.run_script("dry", "--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        after = {table: self.query(f"SELECT * FROM {table}") for table in before}
        self.assertEqual(before, after)
        self.assertFalse(self.export.exists())


if __name__ == "__main__":
    unittest.main()
