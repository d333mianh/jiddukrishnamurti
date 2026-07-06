from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import_concepts.py"


def concept(slug: str, **changes):
    value = {
        "slug": slug,
        "name": slug.title(),
        "status": "pilot",
        "definition": f"A working definition of {slug}.",
        "include_criteria": f"Include substantive discussion of {slug}.",
        "exclude_criteria": "Exclude incidental mentions.",
        "aliases": [],
        "relations": [],
    }
    value.update(changes)
    return value


class ImportConceptsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "corpus.db"
        self.jsonl = self.root / "concepts.jsonl"
        self.rows = [
            concept("fear", aliases=[{"alias": "fright", "language": "en", "period_note": None}],
                    relations=[{"to": "thought", "relation": "related", "note": "Fear uses thought."}]),
            concept("thought", aliases=[{"alias": "thinking", "language": "en", "period_note": None}]),
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows=None):
        rows = self.rows if rows is None else rows
        self.jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def run_import(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--jsonl", str(self.jsonl), "--db", str(self.db), *extra],
            text=True, capture_output=True,
        )

    def query(self, sql, params=()):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql, params).fetchall()

    def test_fresh_import_creates_all_authored_rows(self):
        self.write()
        result = self.run_import()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.query("SELECT slug,name,status FROM concepts ORDER BY slug"),
                         [("fear", "Fear", "pilot"), ("thought", "Thought", "pilot")])
        self.assertEqual(self.query("SELECT version FROM concept_versions ORDER BY concept_id"), [(1,), (1,)])
        self.assertEqual(self.query("SELECT alias FROM concept_aliases ORDER BY alias"), [("fright",), ("thinking",)])
        self.assertEqual(self.query("SELECT relation,note FROM concept_relations"), [("related", "Fear uses thought.")])

    def test_reimport_is_no_op(self):
        self.write()
        self.assertEqual(self.run_import().returncode, 0)
        before = {table: self.query(f"SELECT * FROM {table}") for table in
                  ("concepts", "concept_versions", "concept_aliases", "concept_relations")}
        result = self.run_import()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {table: self.query(f"SELECT * FROM {table}") for table in before}
        self.assertEqual(after, before)
        self.assertIn("versions=0", result.stdout)

    def test_changed_definition_appends_version_two(self):
        self.write()
        self.run_import()
        self.rows[0]["definition"] = "A revised definition of fear."
        self.write()
        self.assertEqual(self.run_import().returncode, 0)
        self.assertEqual(self.query(
            "SELECT version,definition FROM concept_versions v JOIN concepts c ON c.id=v.concept_id "
            "WHERE c.slug='fear' ORDER BY version"),
            [(1, "A working definition of fear."), (2, "A revised definition of fear.")])

    def test_alias_removal_deletes_alias(self):
        self.write()
        self.run_import()
        self.rows[0]["aliases"] = []
        self.write()
        self.assertEqual(self.run_import().returncode, 0)
        self.assertEqual(self.query("SELECT alias FROM concept_aliases ORDER BY alias"), [("thinking",)])

    def test_missing_concept_warns_without_deleting(self):
        self.write()
        self.run_import()
        self.write([self.rows[1]])
        result = self.run_import()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING", result.stdout)
        self.assertIn("deprecated", result.stdout)
        self.assertEqual(self.query("SELECT slug FROM concepts ORDER BY slug"), [("fear",), ("thought",)])

    def test_invalid_relation_target_aborts_without_writes(self):
        self.write()
        self.run_import()
        before = self.db.read_bytes()
        self.rows[0]["name"] = "Changed"
        self.rows[0]["relations"] = [{"to": "unknown", "relation": "related", "note": None}]
        self.write()
        result = self.run_import()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("relation target 'unknown'", result.stderr)
        self.assertEqual(self.db.read_bytes(), before)

    def test_dry_run_writes_nothing(self):
        self.write()
        result = self.run_import("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("planned changes", result.stdout)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
