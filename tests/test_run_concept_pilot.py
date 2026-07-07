from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from concept_schema import ensure_concept_schema  # noqa: E402
from run_concept_pilot import assemble_requests, import_results  # noqa: E402
from segment_schema import ensure_corpus_schema, utc_now  # noqa: E402


class ConceptPilotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "corpus.db"
        self.conn = sqlite3.connect(self.db)
        self.conn.execute("PRAGMA foreign_keys = ON")
        ensure_corpus_schema(self.conn)
        ensure_concept_schema(self.conn)
        now = utc_now()
        self.conn.execute(
            """INSERT INTO transcripts(item_code,event_type,corpus_tier,kind,language,
                      source_path,resolved_via,parser_version,parsed_at)
               VALUES('AB70T1','T','A','manual','en','x','test','v1',?)""", (now,))
        for slug in ("fear", "thought", "freedom"):
            cursor = self.conn.execute(
                "INSERT INTO concepts(slug,name,created_at) VALUES(?,?,?)",
                (slug, slug.title(), now))
            self.conn.execute(
                """INSERT INTO concept_versions(concept_id,version,definition,
                           include_criteria,exclude_criteria,created_at)
                   VALUES(?,1,?,?,?,?)""",
                (cursor.lastrowid, f"Definition of {slug}", f"Include {slug}",
                 f"Exclude {slug}", now))
        anchor = self.conn.execute(
            """INSERT INTO passage_anchors(item_code,transcript_kind,
                   transcript_language,passage_seq,text_sha256,parser_version,text,
                   speaker_code,t_start,t_end,timestamps_synthetic,attribution,created_at)
               VALUES('AB70T1','manual','en',1,'hash','v1','Fear and freedom.',
                      'K',0,10,0,'label',?)""", (now,))
        eval_set = self.conn.execute(
            "INSERT INTO eval_sets(name,created_at) VALUES('pilot-2026-07',?)", (now,))
        self.conn.execute(
            """INSERT INTO eval_set_passages(eval_set_id,anchor_id,stratum_json)
               VALUES(?,?,?)""", (eval_set.lastrowid, anchor.lastrowid,
                                    json.dumps({"decade": "1970s"})))
        self.anchor_id = int(anchor.lastrowid)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.temp.cleanup()

    def test_request_assembly(self) -> None:
        requests, _, prompt = assemble_requests(self.conn)
        self.assertEqual(str(self.anchor_id), requests[0]["custom_id"])
        params = requests[0]["params"]
        self.assertEqual("claude-sonnet-5", params["model"])
        self.assertEqual({"type": "disabled"}, params["thinking"])
        schema = params["output_config"]["format"]["schema"]
        self.assertEqual({"fear", "thought", "freedom"}, set(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual({"type": "ephemeral"}, params["system"][-1]["cache_control"])
        for slug in ("fear", "thought", "freedom"):
            self.assertIn(f"Definition of {slug}", prompt)

    def result(self, applies: bool = True) -> Mock:
        payload = {slug: {"applies": applies, "confidence": "high", "rationale": slug}
                   for slug in ("fear", "thought", "freedom")}
        value = {"custom_id": str(self.anchor_id), "result": {"type": "succeeded",
                 "message": {"content": [{"type": "text", "text": json.dumps(payload)}]}}}
        return Mock(model_dump=Mock(return_value=value))

    def test_result_write_and_idempotency(self) -> None:
        counts = import_results(self.conn, "test-run", "batch-1", [self.result()])
        self.assertEqual(1, counts["completed"])
        rows = self.conn.execute(
            "SELECT relevance_label,relevance_confidence,definition_like FROM concept_predictions"
        ).fetchall()
        self.assertEqual(3, len(rows))
        self.assertTrue(all(row == ("substantive", 1.0, "not_applicable") for row in rows))
        import_results(self.conn, "test-run", "batch-1", [self.result(False)])
        rows = self.conn.execute(
            "SELECT relevance_label FROM concept_predictions"
        ).fetchall()
        self.assertEqual(3, len(rows))
        self.assertTrue(all(row[0] == "not_relevant" for row in rows))

    def test_api_error_is_recorded(self) -> None:
        result = {"custom_id": str(self.anchor_id),
                  "result": {"type": "errored", "error": {"type": "invalid_request"}}}
        counts = import_results(self.conn, "error-run", "batch-2", [result])
        self.assertEqual(1, counts["api_error"])
        self.assertEqual(3, self.conn.execute(
            "SELECT count(*) FROM concept_predictions WHERE outcome='api_error'"
        ).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
