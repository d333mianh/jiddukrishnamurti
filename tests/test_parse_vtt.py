from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from parse_vtt import (  # noqa: E402
    build_registry, ingest, parse_cues, read_vtt, resolve_vtt,
)
from segment_schema import ensure_corpus_schema  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ParseVttTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        ensure_corpus_schema(self.conn, "/tmp/test-catalog.db")

    def tearDown(self) -> None:
        self.conn.close()

    def cues(self, name: str):
        return parse_cues(read_vtt(FIXTURES / name))

    def ingest_fixture(self, name: str, code: str, event_type: str):
        return ingest(
            self.conn,
            item_code=code,
            event_type=event_type,
            corpus_tier="C" if event_type.startswith("F") else "A",
            kind="manual",
            language="en",
            source_path=str(FIXTURES / name),
            resolved_via="override",
            cues=self.cues(name),
        )

    def test_no_space_after_colon_labels_do_not_collapse_dialogue(self) -> None:
        result = self.ingest_fixture("no_space_labels.vtt", "TESTQ1", "Q")
        self.assertEqual({"K", "Q"}, set(result["speakers"]))
        self.assertGreater(result["k_passages"], 0)
        self.assertEqual("pass", result["qa"]["status"])

    def test_trusted_mid_cue_label_is_split_and_timestamp_is_synthetic(self) -> None:
        result = self.ingest_fixture("embedded_label.vtt", "TESTD1", "D")
        self.assertIn("K", result["speakers"])
        synthetic = self.conn.execute(
            "SELECT COUNT(*) FROM segments WHERE timestamps_synthetic=1"
        ).fetchone()[0]
        synthetic_passages = self.conn.execute(
            "SELECT COUNT(*) FROM passages WHERE timestamps_synthetic=1"
        ).fetchone()[0]
        self.assertGreater(synthetic, 0)
        self.assertGreater(synthetic_passages, 0)

    def test_recurring_prose_colon_is_not_admitted_as_speaker(self) -> None:
        cues = self.cues("prose_colon.vtt")
        registry = build_registry(cues)
        self.assertNotIn("So we are asking", registry)
        result = self.ingest_fixture("prose_colon.vtt", "TESTT1", "T")
        self.assertEqual(["K"], result["speakers"])

    def test_entirely_unlabeled_talk_defaults_to_k_with_provenance(self) -> None:
        result = self.ingest_fixture("unlabeled_talk.vtt", "TESTT2", "T")
        self.assertTrue(result["assumed_k"])
        self.assertGreater(result["k_passages"], 0)
        assumed = self.conn.execute(
            "SELECT assumed_k FROM transcripts WHERE item_code='TESTT2'"
        ).fetchone()[0]
        self.assertEqual(1, assumed)
        self.assertEqual({"ANN", "K"}, set(result["speakers"]))

    def test_reingest_is_idempotent(self) -> None:
        self.ingest_fixture("no_space_labels.vtt", "TESTQ2", "Q")
        before = self._row_counts()
        self.ingest_fixture("no_space_labels.vtt", "TESTQ2", "Q")
        self.assertEqual(before, self._row_counts())

    def test_zero_cue_guard_raises_without_deleting_prior_data(self) -> None:
        self.ingest_fixture("unlabeled_talk.vtt", "TESTT3", "T")
        before = self._row_counts()
        with self.assertRaises(ValueError):
            ingest(
                self.conn,
                item_code="TESTT3",
                event_type="T",
                corpus_tier="A",
                kind="manual",
                language="en",
                source_path=str(FIXTURES / "empty.vtt"),
                resolved_via="override",
                cues=self.cues("empty.vtt"),
            )
        self.assertEqual(before, self._row_counts())

    def test_corpus_database_records_provenance(self) -> None:
        meta = dict(self.conn.execute("SELECT key,value FROM corpus_meta"))
        self.assertIn("created_at", meta)
        self.assertEqual("l2-parser-v3", meta["parser_version"])
        self.assertEqual(
            str(Path("/tmp/test-catalog.db").resolve()), meta["source_catalog_db"]
        )

    def test_prose_question_talk_returns_to_assumed_k(self) -> None:
        result = self.ingest_fixture("prose_question_talk.vtt", "TESTT4", "T")
        self.assertTrue(result["assumed_k"])
        self.assertGreater(result["k_passages"], 0)
        attributions = dict(self.conn.execute(
            "SELECT attribution,COUNT(*) FROM segments GROUP BY attribution"
        ))
        self.assertIn("assumed_k", attributions)
        self.assertIn("q_boundary_heuristic", attributions)

    def test_question_boundary_marks_unlabeled_answer_as_k(self) -> None:
        result = self.ingest_fixture("unlabeled_qa_answer.vtt", "TESTQ3", "Q")
        self.assertGreater(result["k_passages"], 0)
        row = self.conn.execute(
            "SELECT speaker_code,attribution FROM segments "
            "WHERE attribution='q_boundary_heuristic'"
        ).fetchone()
        self.assertEqual(("K", "q_boundary_heuristic"), row)
        self.assertGreater(self.conn.execute(
            "SELECT COUNT(*) FROM passages WHERE attribution='q_boundary_heuristic'"
        ).fetchone()[0], 0)

    def test_labeled_turn_keeps_unlabeled_continuations_atomic(self) -> None:
        self.ingest_fixture("labeled_turn_continuation.vtt", "TESTQ5", "Q")
        rows = self.conn.execute(
            "SELECT speaker_code,attribution,text FROM segments ORDER BY seq"
        ).fetchall()
        self.assertEqual(2, len(rows))
        self.assertEqual(("K", "label"), rows[0][:2])
        self.assertIn("third continuation", rows[0][2])
        self.assertEqual(("Q", "label"), rows[1][:2])

    def test_long_labeled_k_turn_produces_full_sized_passages(self) -> None:
        self.ingest_fixture("long_labeled_monologue.vtt", "TESTT5", "T")
        segments = self.conn.execute(
            "SELECT speaker_code,attribution FROM segments ORDER BY seq"
        ).fetchall()
        self.assertEqual([("K", "label")], segments)
        word_counts = [row[0] for row in self.conn.execute(
            "SELECT word_count FROM passages ORDER BY seq"
        )]
        self.assertGreater(len(word_counts), 1)
        self.assertGreater(sum(word_counts) / len(word_counts), 100)
        self.assertLessEqual(sum(count < 20 for count in word_counts), 1)

    def test_k_presence_warns_for_uncovered_event_type(self) -> None:
        result = self.ingest_fixture("zero_k_film.vtt", "TESTF1", "FOF")
        self.assertEqual("warn", result["qa"]["status"])
        self.assertEqual("k_presence", result["qa"]["rule"])
        self.assertIn("zero_k_passages", result["qa"]["failure_codes"])

    def test_tier_c_is_ingested_but_excluded_from_fts(self) -> None:
        result = self.ingest_fixture("unlabeled_talk.vtt", "TESTF2", "FTPL")
        self.assertGreater(result["k_passages"], 0)
        self.assertGreater(self.conn.execute(
            "SELECT COUNT(*) FROM passages WHERE item_code='TESTF2'"
        ).fetchone()[0], 0)
        self.assertEqual(0, self.conn.execute(
            "SELECT COUNT(*) FROM passages_fts"
        ).fetchone()[0])
        self.assertEqual("C", self.conn.execute(
            "SELECT corpus_tier FROM transcripts WHERE item_code='TESTF2'"
        ).fetchone()[0])

    def test_single_speaker_dialogue_is_a_pass_with_source_signal(self) -> None:
        result = self.ingest_fixture("single_speaker_qa.vtt", "TESTQ4", "Q")
        self.assertEqual("pass", result["qa"]["status"])
        self.assertIn("single_speaker_source", result["qa"]["signals"])

    def test_sibling_vtt_is_refused_when_its_length_contradicts_the_recording(self) -> None:
        """A bare BASE.en.vtt is one part's transcript, not the whole series.

        Handing it to every part is what put part 1's words — and part 1's
        timestamps — under parts 2..N, which makes every citation drawn from
        them point at the wrong recording at the wrong offset."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        library = Path(tmp.name) / "library" / "sec" / "series"
        library.mkdir(parents=True)
        (library / "BASE1.en.vtt").write_text(
            "WEBVTT\n\n00:00:00.000 --> 01:00:00.000\nK: Fear is time.\n",
            encoding="utf-8",
        )
        media_root = Path(tmp.name)
        future = "library/sec/series/BASE1.2 - part two.en.vtt"

        # part 2 runs 90 minutes; the 60-minute file cannot be its transcript
        path, via = resolve_vtt("BASE1.2", future, media_root, duration_minutes=90)
        self.assertIsNone(path)
        self.assertEqual("missing", via)

        # a 62-minute recording is within tolerance, so the same file resolves
        path, via = resolve_vtt("BASE1.2", future, media_root, duration_minutes=62)
        self.assertEqual("BASE1.en.vtt", path.name if path else None)
        self.assertEqual("sibling-vtt", via)

        # no catalog runtime at all is not evidence of a match
        self.assertEqual(
            (None, "missing"), resolve_vtt("BASE1.2", future, media_root, None))

    def _row_counts(self) -> tuple[int, ...]:
        tables = (
            "transcripts", "speaker_labels", "segments", "passages",
            "passages_fts", "transcript_qa",
        )
        return tuple(
            self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        )


if __name__ == "__main__":
    unittest.main()
