from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from concept_schema import ensure_concept_schema  # noqa: E402
from segment_schema import utc_now  # noqa: E402


TABLES = {
    "concepts", "concept_versions", "concept_aliases", "concept_relations",
    "passage_anchors", "model_runs", "model_batches", "concept_predictions",
    "prediction_evidence", "eval_sets", "eval_set_passages", "eval_labels",
    "adjudications", "run_metrics",
}
INDEXES = {
    "idx_concept_aliases_alias", "idx_anchors_passage", "idx_anchors_lookup",
    "idx_predictions_concept", "idx_predictions_anchor", "idx_eval_labels_lookup",
}


class ConceptSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("CREATE TABLE passages (id INTEGER PRIMARY KEY)")
        ensure_concept_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def _concept(self, slug: str = "fear") -> int:
        cursor = self.conn.execute(
            "INSERT INTO concepts(slug,name,created_at) VALUES(?,?,?)",
            (slug, slug.title(), utc_now()),
        )
        return int(cursor.lastrowid)

    def _anchor(self, passage_id: int | None = None, seq: int = 1) -> int:
        cursor = self.conn.execute(
            """INSERT INTO passage_anchors(
                   passage_id,item_code,transcript_kind,transcript_language,
                   passage_seq,text_sha256,parser_version,text,speaker_code,
                   t_start,t_end,timestamps_synthetic,attribution,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (passage_id, "LO61T1", "manual", "en", seq, f"hash-{seq}",
             "l2-parser-v3", f"passage {seq}", "K", 0.0, 10.0, 0,
             "label", utc_now()),
        )
        return int(cursor.lastrowid)

    def _run(self, key: str = "pilot") -> int:
        cursor = self.conn.execute(
            """INSERT INTO model_runs(
                   run_key,purpose,model,prompt_sha256,prompt_version
               ) VALUES(?,?,?,?,?)""",
            (key, "tagging", "test-model", "prompt-hash", "v1"),
        )
        return int(cursor.lastrowid)

    def _prediction(
        self,
        run_id: int,
        concept_id: int,
        anchor_id: int,
        outcome: str = "completed",
        relevance: str = "substantive",
    ) -> int:
        cursor = self.conn.execute(
            """INSERT INTO concept_predictions(
                   run_id,concept_id,anchor_id,custom_id,outcome,
                   relevance_label,definition_like,created_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (run_id, concept_id, anchor_id, f"request-{anchor_id}", outcome,
             relevance, "no", utc_now()),
        )
        return int(cursor.lastrowid)

    def test_all_tables_view_and_indexes_created(self) -> None:
        objects = self.conn.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        self.assertTrue(TABLES.issubset({name for kind, name in objects if kind == "table"}))
        self.assertIn("passage_tags", {name for kind, name in objects if kind == "view"})
        self.assertTrue(INDEXES.issubset({name for kind, name in objects if kind == "index"}))

    def test_double_ensure_is_idempotent(self) -> None:
        ensure_concept_schema(self.conn)
        ensure_concept_schema(self.conn)
        counts = dict(self.conn.execute(
            "SELECT name,count(*) FROM sqlite_master "
            "WHERE name IN ({}) GROUP BY name".format(
                ",".join("?" for _ in TABLES | INDEXES | {"passage_tags"})
            ),
            tuple(TABLES | INDEXES | {"passage_tags"}),
        ))
        self.assertTrue(all(counts[name] == 1 for name in counts))

    def test_passage_delete_nulls_anchor_passage_id(self) -> None:
        self.conn.execute("INSERT INTO passages(id) VALUES(1)")
        anchor_id = self._anchor(1)
        self.conn.execute("DELETE FROM passages WHERE id=1")
        passage_id = self.conn.execute(
            "SELECT passage_id FROM passage_anchors WHERE id=?", (anchor_id,)
        ).fetchone()[0]
        self.assertIsNone(passage_id)

    def test_model_run_delete_cascades_predictions_and_evidence(self) -> None:
        concept_id = self._concept()
        anchor_id = self._anchor()
        prediction_id = self._prediction(self._run(), concept_id, anchor_id)
        self.conn.execute(
            "INSERT INTO prediction_evidence(prediction_id,quote) VALUES(?,?)",
            (prediction_id, "passage"),
        )
        self.conn.execute("DELETE FROM model_runs")
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM concept_predictions").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM prediction_evidence").fetchone()[0])

    def test_concept_with_prediction_cannot_be_deleted(self) -> None:
        concept_id = self._concept()
        self._prediction(self._run(), concept_id, self._anchor())
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM concepts WHERE id=?", (concept_id,))

    def test_prediction_checks_reject_invalid_labels(self) -> None:
        concept_id = self._concept()
        run_id = self._run()
        anchor_id = self._anchor()
        for column, value in (("relevance_label", "bad"), ("definition_like", "bad")):
            with self.subTest(column=column), self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(
                    f"""INSERT INTO concept_predictions(
                            run_id,concept_id,anchor_id,custom_id,outcome,{column},created_at
                        ) VALUES(?,?,?,?,?,?,?)""",
                    (run_id, concept_id, anchor_id, column, "completed", value, utc_now()),
                )

    def test_relation_checks_reject_invalid_and_self_relations(self) -> None:
        first = self._concept()
        second = self._concept("attention")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """INSERT INTO concept_relations(
                       src_concept_id,dst_concept_id,relation,created_at
                   ) VALUES(?,?,?,?)""",
                (first, second, "narrower", utc_now()),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """INSERT INTO concept_relations(
                       src_concept_id,dst_concept_id,relation,created_at
                   ) VALUES(?,?,?,?)""",
                (first, first, "related", utc_now()),
            )

    def test_anchor_identity_tuple_is_unique(self) -> None:
        self._anchor(seq=1)
        with self.assertRaises(sqlite3.IntegrityError):
            self._anchor(seq=1)

    def test_passage_tags_returns_only_accepted_substantive_completed(self) -> None:
        concept_id = self._concept()
        run_id = self._run()
        cases = [
            ("completed", "substantive", "accept", True),
            ("completed", "mention_only", "accept", False),
            ("api_error", "substantive", "accept", False),
            ("completed", "substantive", "reject", False),
        ]
        expected = []
        for seq, (outcome, relevance, verdict, accepted) in enumerate(cases, 1):
            prediction_id = self._prediction(
                run_id, concept_id, self._anchor(seq=seq), outcome, relevance
            )
            self.conn.execute(
                """INSERT INTO adjudications(
                       prediction_id,verdict,adjudicator,created_at
                   ) VALUES(?,?,?,?)""",
                (prediction_id, verdict, f"human:{seq}", utc_now()),
            )
            if accepted:
                expected.append(prediction_id)
        actual = [row[0] for row in self.conn.execute("SELECT id FROM passage_tags")]
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
