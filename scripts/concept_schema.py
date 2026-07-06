"""SQLite schema for the generated L3 teachings concept layer.

The concept layer lives in ``corpus/krishnamurti-corpus.db`` alongside the
L1/L2 corpus tables. Human-authored concept and evaluation data is materialized
from tracked JSONL; model predictions and metrics are regenerable.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from segment_schema import utc_now


CONCEPT_DDL = """
CREATE TABLE IF NOT EXISTS concepts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slug       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pilot'
                    CHECK(status IN ('pilot','active','deprecated')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS concept_versions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id       INTEGER NOT NULL REFERENCES concepts(id),
    version          INTEGER NOT NULL,
    definition       TEXT NOT NULL,
    include_criteria TEXT,
    exclude_criteria TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE(concept_id, version)
);

CREATE TABLE IF NOT EXISTS concept_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id  INTEGER NOT NULL REFERENCES concepts(id),
    alias       TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT 'en',
    period_note TEXT,
    UNIQUE(concept_id, alias COLLATE NOCASE)
);
CREATE INDEX IF NOT EXISTS idx_concept_aliases_alias
    ON concept_aliases(alias COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS concept_relations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    src_concept_id INTEGER NOT NULL REFERENCES concepts(id),
    dst_concept_id INTEGER NOT NULL REFERENCES concepts(id),
    relation       TEXT NOT NULL
                        CHECK(relation IN ('broader','related','contrasts_with')),
    note           TEXT,
    created_at     TEXT NOT NULL,
    UNIQUE(src_concept_id, dst_concept_id, relation),
    CHECK(src_concept_id != dst_concept_id)
);

CREATE TABLE IF NOT EXISTS passage_anchors (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    passage_id           INTEGER REFERENCES passages(id) ON DELETE SET NULL,
    item_code            TEXT NOT NULL,
    transcript_kind      TEXT NOT NULL,
    transcript_language  TEXT NOT NULL,
    passage_seq          INTEGER NOT NULL,
    text_sha256          TEXT NOT NULL,
    parser_version       TEXT NOT NULL,
    text                 TEXT NOT NULL,
    speaker_code         TEXT NOT NULL,
    t_start              REAL NOT NULL,
    t_end                REAL NOT NULL,
    timestamps_synthetic INTEGER NOT NULL,
    attribution          TEXT NOT NULL,
    anchor_status        TEXT NOT NULL DEFAULT 'live'
                              CHECK(anchor_status IN ('live','stale')),
    created_at           TEXT NOT NULL,
    UNIQUE(item_code, transcript_kind, transcript_language, passage_seq, text_sha256)
);
CREATE INDEX IF NOT EXISTS idx_anchors_passage ON passage_anchors(passage_id);
CREATE INDEX IF NOT EXISTS idx_anchors_lookup
    ON passage_anchors(item_code, text_sha256);

CREATE TABLE IF NOT EXISTS model_runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key            TEXT NOT NULL UNIQUE,
    purpose            TEXT NOT NULL
                            CHECK(purpose IN ('tagging','eval','adjudication')),
    model              TEXT NOT NULL,
    prompt_sha256      TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    concept_version_id INTEGER REFERENCES concept_versions(id),
    code_git_rev       TEXT,
    params_json        TEXT,
    status             TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','running','complete','failed')),
    started_at         TEXT,
    completed_at       TEXT,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    notes              TEXT
);

CREATE TABLE IF NOT EXISTS model_batches (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    batch_id         TEXT NOT NULL,
    submitted_at     TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'submitted',
    raw_results_path TEXT,
    UNIQUE(run_id, batch_id)
);

CREATE TABLE IF NOT EXISTS concept_predictions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                INTEGER NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    concept_id            INTEGER NOT NULL REFERENCES concepts(id),
    anchor_id             INTEGER NOT NULL REFERENCES passage_anchors(id),
    custom_id             TEXT NOT NULL,
    outcome               TEXT NOT NULL
                               CHECK(outcome IN ('completed','api_error','parse_error','skipped')),
    relevance_label       TEXT
                               CHECK(relevance_label IN ('not_relevant','mention_only','substantive','unsure')),
    relevance_confidence  REAL CHECK(relevance_confidence BETWEEN 0 AND 1),
    definition_like       TEXT
                               CHECK(definition_like IN ('yes','no','unsure','not_applicable')),
    definition_confidence REAL CHECK(definition_confidence BETWEEN 0 AND 1),
    rationale             TEXT,
    error_detail          TEXT,
    created_at            TEXT NOT NULL,
    UNIQUE(run_id, concept_id, anchor_id)
);
CREATE INDEX IF NOT EXISTS idx_predictions_concept
    ON concept_predictions(concept_id);
CREATE INDEX IF NOT EXISTS idx_predictions_anchor
    ON concept_predictions(anchor_id);

CREATE TABLE IF NOT EXISTS prediction_evidence (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id  INTEGER NOT NULL REFERENCES concept_predictions(id) ON DELETE CASCADE,
    quote          TEXT NOT NULL,
    char_start     INTEGER,
    char_end       INTEGER,
    quote_verified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS eval_sets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    description   TEXT,
    sampling_json TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_set_passages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_set_id   INTEGER NOT NULL REFERENCES eval_sets(id) ON DELETE CASCADE,
    anchor_id     INTEGER NOT NULL REFERENCES passage_anchors(id),
    stratum_json  TEXT,
    sample_weight REAL NOT NULL DEFAULT 1.0,
    UNIQUE(eval_set_id, anchor_id)
);

CREATE TABLE IF NOT EXISTS eval_labels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_set_id     INTEGER NOT NULL REFERENCES eval_sets(id) ON DELETE CASCADE,
    concept_id      INTEGER NOT NULL REFERENCES concepts(id),
    anchor_id       INTEGER NOT NULL REFERENCES passage_anchors(id),
    annotator       TEXT NOT NULL,
    is_gold         INTEGER NOT NULL DEFAULT 0,
    relevance_label TEXT NOT NULL
                         CHECK(relevance_label IN ('not_relevant','mention_only','substantive','unsure')),
    definition_like TEXT NOT NULL
                         CHECK(definition_like IN ('yes','no','unsure','not_applicable')),
    note            TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(eval_set_id, concept_id, anchor_id, annotator)
);
CREATE INDEX IF NOT EXISTS idx_eval_labels_lookup
    ON eval_labels(concept_id, anchor_id);

CREATE TABLE IF NOT EXISTS adjudications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER NOT NULL REFERENCES concept_predictions(id) ON DELETE CASCADE,
    verdict       TEXT NOT NULL CHECK(verdict IN ('accept','reject','unsure')),
    adjudicator   TEXT NOT NULL,
    note          TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(prediction_id, adjudicator)
);

CREATE TABLE IF NOT EXISTS run_metrics (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                INTEGER NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    concept_id            INTEGER NOT NULL REFERENCES concepts(id),
    eval_set_id           INTEGER NOT NULL REFERENCES eval_sets(id),
    precision             REAL,
    recall                REAL,
    f1                    REAL,
    definition_f1         REAL,
    citation_faithfulness REAL,
    computed_at           TEXT NOT NULL,
    UNIQUE(run_id, concept_id, eval_set_id)
);

-- The promotion threshold may later widen based on pilot results.
CREATE VIEW IF NOT EXISTS passage_tags AS
SELECT DISTINCT prediction.*
FROM concept_predictions AS prediction
JOIN adjudications AS adjudication
  ON adjudication.prediction_id = prediction.id
WHERE prediction.outcome = 'completed'
  AND prediction.relevance_label = 'substantive'
  AND adjudication.verdict = 'accept';
"""


def ensure_concept_schema(conn: sqlite3.Connection) -> None:
    """Ensure the L3 concept-layer tables, indexes, view, and migrations."""
    conn.executescript(CONCEPT_DDL)

    # Additive migrations for databases created from pre-acceptance L3 drafts.
    migrations = {
        "passage_anchors": {
            "attribution": "TEXT",
            "anchor_status": "TEXT NOT NULL DEFAULT 'live' "
                             "CHECK(anchor_status IN ('live','stale'))",
        },
        "model_runs": {
            "code_git_rev": "TEXT",
            "params_json": "TEXT",
            "notes": "TEXT",
        },
        "model_batches": {"raw_results_path": "TEXT"},
        "concept_predictions": {"error_detail": "TEXT"},
        "eval_set_passages": {"sample_weight": "REAL NOT NULL DEFAULT 1.0"},
        "eval_labels": {"is_gold": "INTEGER NOT NULL DEFAULT 0"},
        "run_metrics": {"citation_faithfulness": "REAL"},
    }
    for table, additions in migrations.items():
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, declaration in additions.items():
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
                )


if __name__ == "__main__":
    import sys

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("corpus/krishnamurti-corpus.db")
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_concept_schema(conn)
    conn.commit()
    foreign_key_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    objects = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table','view') ORDER BY name"
        )
    ]
    l3_objects = {
        "concepts", "concept_versions", "concept_aliases", "concept_relations",
        "passage_anchors", "model_runs", "model_batches", "concept_predictions",
        "prediction_evidence", "eval_sets", "eval_set_passages", "eval_labels",
        "adjudications", "run_metrics", "passage_tags",
    }
    print(f"concept schema ensured on {db}")
    print("L3 tables present:", [name for name in objects if name in l3_objects])
    print("foreign key violations:", foreign_key_violations)
