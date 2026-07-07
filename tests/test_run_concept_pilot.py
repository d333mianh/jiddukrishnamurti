from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from concept_schema import ensure_concept_schema  # noqa: E402
import run_concept_pilot  # noqa: E402
from run_concept_pilot import (  # noqa: E402
    assemble_requests, import_results, load_concepts, main, validate_payload,
)
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
        for slug, status in (
            ("fear", "active"), ("thought", "pilot"),
            ("freedom", "active"), ("deprecated-one", "deprecated"),
        ):
            cursor = self.conn.execute(
                "INSERT INTO concepts(slug,name,status,created_at) VALUES(?,?,?,?)",
                (slug, slug.title(), status, now))
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
        self.assertEqual(8000, params["max_tokens"])
        self.assertEqual({"type": "disabled"}, params["thinking"])
        schema = params["output_config"]["format"]["schema"]
        self.assertEqual({"fear", "thought", "freedom"}, set(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])
        judgment = schema["properties"]["fear"]
        self.assertEqual(
            ["substantive", "mention_only", "not_relevant"],
            judgment["properties"]["relevance"]["enum"],
        )
        self.assertEqual(
            {"type": "string", "enum": ["yes", "no", "unsure", "not_applicable"]},
            judgment["properties"]["definition_like"])
        self.assertEqual(
            {"relevance", "confidence", "definition_like", "rationale"},
            set(judgment["required"]),
        )
        self.assertEqual({"type": "ephemeral"}, params["system"][-1]["cache_control"])
        for slug in ("fear", "thought", "freedom"):
            self.assertIn(f"Definition of {slug}", prompt)

        self.assertIn("mention_only", prompt)
        self.assertIn("crisp definition", prompt)

    def test_default_and_explicit_concept_sets(self) -> None:
        self.assertEqual(
            ["fear", "thought", "freedom"],
            [concept.slug for concept in load_concepts(self.conn)],
        )
        self.assertEqual(
            ["freedom", "fear"],
            [concept.slug for concept in load_concepts(
                self.conn, ["freedom", "fear"]
            )],
        )
        with self.assertRaisesRegex(ValueError, "missing concepts"):
            load_concepts(self.conn, ["missing"])

    def test_model_flag_and_explicit_concepts(self) -> None:
        with patch.object(run_concept_pilot, "RUNS_DIR", Path(self.temp.name)):
            result = main([
                "--build", "--run-name", "custom", "--db", str(self.db),
                "--model", "custom-model", "--concepts", "freedom,fear",
                "--dry-run",
            ])
        self.assertEqual(0, result)
        request = json.loads(
            (Path(self.temp.name) / "custom" / "requests.jsonl")
            .read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual("custom-model", request["params"]["model"])
        schema = request["params"]["output_config"]["format"]["schema"]
        self.assertEqual(["freedom", "fear"], schema["required"])

    def result(
        self, relevance: str = "substantive", definition_like: str = "yes"
    ) -> Mock:
        payload = {slug: {"relevance": relevance, "confidence": "high",
                          "definition_like": definition_like, "rationale": slug}
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
        self.assertTrue(all(row == ("substantive", 1.0, "yes") for row in rows))
        confidence = self.conn.execute(
            "SELECT definition_confidence FROM concept_predictions LIMIT 1"
        ).fetchone()[0]
        self.assertEqual(1.0, confidence)
        import_results(self.conn, "test-run", "batch-1",
                       [self.result("mention_only", "not_applicable")])
        rows = self.conn.execute(
            "SELECT relevance_label,definition_like,definition_confidence "
            "FROM concept_predictions"
        ).fetchall()
        self.assertEqual(3, len(rows))
        self.assertTrue(all(row == ("mention_only", "not_applicable", None) for row in rows))

    def test_validation_rejects_old_and_invalid_shapes(self) -> None:
        concepts = load_concepts(self.conn)
        old = {concept.slug: {"applies": True, "confidence": "high",
                              "rationale": "old"} for concept in concepts}
        with self.assertRaisesRegex(ValueError, "invalid judgment shape"):
            validate_payload(old, concepts)
        invalid = {concept.slug: {
            "relevance": "maybe", "confidence": "high",
            "definition_like": "no", "rationale": "invalid",
        } for concept in concepts}
        with self.assertRaisesRegex(ValueError, "invalid relevance"):
            validate_payload(invalid, concepts)

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
