from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reanchor_passages.py"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from concept_schema import ensure_concept_schema  # noqa: E402
from segment_schema import ensure_corpus_schema, utc_now  # noqa: E402


class ReanchorPassagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "corpus.db"
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            ensure_corpus_schema(conn)
            ensure_concept_schema(conn)
            manual = self._transcript(conn, "AA61T1", "manual")
            whisper = self._transcript(conn, "AA61T1", "whisper")
            live = self._passage(conn, manual, 0, "same words")
            missing = self._passage(conn, manual, 1, "words that disappear")
            cross_kind = self._passage(conn, manual, 2, "whisper only later")
            self._anchor(conn, live, 0, "same words")
            self._anchor(conn, missing, 1, "words that disappear")
            self._anchor(conn, cross_kind, 2, "whisper only later")
            conn.execute("DELETE FROM transcripts WHERE id=?", (manual,))
            rebuilt = self._transcript(conn, "AA61T1", "manual")
            self.recreated_id = self._passage(conn, rebuilt, 7, "same words")
            self._passage(conn, whisper, 0, "whisper only later")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _transcript(self, conn: sqlite3.Connection, code: str, kind: str) -> int:
        cursor = conn.execute(
            """INSERT INTO transcripts(
                   item_code,event_type,corpus_tier,kind,language,source_path,
                   resolved_via,parser_version,parsed_at
               ) VALUES(?,'T','A',?,'en','test','test','parser',?)""",
            (code, kind, utc_now()),
        )
        return int(cursor.lastrowid)

    def _passage(
        self, conn: sqlite3.Connection, transcript_id: int, seq: int, text: str
    ) -> int:
        segment = conn.execute(
            """INSERT INTO segments(
                   transcript_id,item_code,seq,speaker_code,t_start,t_end,text,
                   word_count,attribution
               ) VALUES(?,'AA61T1',?,'K',0,10,?,2,'label')""",
            (transcript_id, seq, text),
        )
        cursor = conn.execute(
            """INSERT INTO passages(
                   transcript_id,segment_id,item_code,seq,speaker_code,t_start,t_end,
                   text,word_count,attribution
               ) VALUES(?,?,'AA61T1',?,'K',0,10,?,2,'label')""",
            (transcript_id, int(segment.lastrowid), seq, text),
        )
        return int(cursor.lastrowid)

    def _anchor(
        self, conn: sqlite3.Connection, passage_id: int, seq: int, text: str
    ) -> None:
        conn.execute(
            """INSERT INTO passage_anchors(
                   passage_id,item_code,transcript_kind,transcript_language,
                   passage_seq,text_sha256,parser_version,text,speaker_code,t_start,
                   t_end,timestamps_synthetic,attribution,created_at
               ) VALUES(?,'AA61T1','manual','en',?,?,'parser',?,'K',0,10,0,'label',?)""",
            (
                passage_id, seq, hashlib.sha256(text.encode()).hexdigest(), text,
                utc_now(),
            ),
        )

    def test_relinks_unique_match_and_marks_missing_and_cross_kind_stale(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--db", str(self.db)],
            text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("relinked=1 stale=2", result.stdout)
        with closing(sqlite3.connect(self.db)) as conn:
            rows = conn.execute(
                "SELECT passage_id,anchor_status FROM passage_anchors ORDER BY passage_seq"
            ).fetchall()
        self.assertEqual((self.recreated_id, "live"), rows[0])
        self.assertEqual((None, "stale"), rows[1])
        self.assertEqual((None, "stale"), rows[2])

    def test_duplicate_text_resolved_by_seq(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            transcript = self._transcript(conn, "AA61T1", "scribe")
            self._passage(conn, transcript, 3, "repeated words")
            wanted = self._passage(conn, transcript, 4, "repeated words")
            conn.execute(
                """INSERT INTO passage_anchors(
                       passage_id,item_code,transcript_kind,transcript_language,
                       passage_seq,text_sha256,parser_version,text,speaker_code,
                       t_start,t_end,timestamps_synthetic,attribution,created_at
                   ) VALUES(NULL,'AA61T1','scribe','en',4,?,'parser',
                            'repeated words','K',0,10,0,'label',?)""",
                (hashlib.sha256(b"repeated words").hexdigest(), utc_now()),
            )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--db", str(self.db)],
            text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        with closing(sqlite3.connect(self.db)) as conn:
            row = conn.execute(
                "SELECT passage_id,anchor_status FROM passage_anchors "
                "WHERE transcript_kind='scribe'"
            ).fetchone()
        self.assertEqual((wanted, "live"), row)

    def test_dry_run_rolls_back(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--db", str(self.db), "--dry-run"],
            text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        with closing(sqlite3.connect(self.db)) as conn:
            statuses = conn.execute(
                "SELECT DISTINCT anchor_status FROM passage_anchors"
            ).fetchall()
        self.assertEqual([("live",)], statuses)


if __name__ == "__main__":
    unittest.main()
