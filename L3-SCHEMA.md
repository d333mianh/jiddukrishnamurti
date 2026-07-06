# L3 concept-layer schema design

Status: **design accepted pending implementation** (2026-07-06). Reviewed by two
independent advisors (Codex gpt-5.5 xhigh, Opus 4.8 xhigh); this document is the
reconciled result. Implements plan step 4 ("Build the L3 Concept Pilot") of
`gpt-05JUL-plan.md`.

## Ground rules

1. **The corpus DB is regenerable and gitignored; human-authored state is not
   regenerable.** Concepts, concept definitions, aliases, relations, gold eval
   labels, and human adjudications are canonical *authored* data and live in
   tracked JSONL under `concepts/` (no full copyrighted passage text — anchors
   only). An import script materializes them into the corpus DB. Model
   predictions and derived metrics live only in the corpus DB (regenerable from
   raw batch outputs, which are archived on disk).
2. **Nothing L3 may CASCADE off `passages`.** `parse_vtt.py` re-ingest deletes
   and recreates a transcript's passages, so `passages.id` is unstable.
   L3 rows reference a durable `passage_anchors` row; the anchor's live
   `passage_id` is `ON DELETE SET NULL` and is re-attached by a re-anchoring
   pass.
3. **Passage identity** = `(item_code, transcript_kind, transcript_language,
   passage_seq, text_sha256)`. The hash alone is not identity (2,345
   within-transcript duplicate-text groups exist); seq + timestamps disambiguate.
   Re-anchoring is automatic only within the same `(item_code, kind, language)`
   and only on exact text-hash match at unambiguous position; anything else is
   flagged `stale` for human review or re-run. Annotations are **never**
   migrated across transcript kinds (whisper → manual/Scribe): the judged text
   changed.
4. Every writer sets `PRAGMA foreign_keys = ON` (connection-local in SQLite);
   smoke tests run `PRAGMA foreign_key_check`.
5. New module `scripts/concept_schema.py` mirrors `segment_schema.py`
   conventions: DDL constant, `ensure_concept_schema(conn)` with additive
   `PRAGMA table_info` migrations, importable + positional smoke-test CLI.

## Tables (corpus DB)

### Authored layer (materialized from tracked JSONL)

```sql
concepts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- e.g. 'fear'
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pilot' CHECK(status IN ('pilot','active','deprecated')),
  created_at TEXT NOT NULL                    -- UTC ISO-8601, set in code
);

-- Definitions are versioned: model runs pin the exact version they saw.
concept_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  concept_id INTEGER NOT NULL REFERENCES concepts(id),
  version INTEGER NOT NULL,
  definition TEXT NOT NULL,                   -- working definition given to the model
  include_criteria TEXT,
  exclude_criteria TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(concept_id, version)
);

concept_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  concept_id INTEGER NOT NULL REFERENCES concepts(id),
  alias TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT 'en',
  period_note TEXT,                           -- K's terminology shifts by decade
  UNIQUE(concept_id, alias COLLATE NOCASE)
);
CREATE INDEX idx_concept_aliases_alias ON concept_aliases(alias COLLATE NOCASE);

concept_relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  src_concept_id INTEGER NOT NULL REFERENCES concepts(id),
  dst_concept_id INTEGER NOT NULL REFERENCES concepts(id),
  -- 'narrower' is stored as the inverse 'broader'; symmetric relations are
  -- canonicalized src_id < dst_id (enforced by the import script).
  relation TEXT NOT NULL CHECK(relation IN ('broader','related','contrasts_with')),
  note TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(src_concept_id, dst_concept_id, relation),
  CHECK(src_concept_id != dst_concept_id)
);
```

Concepts are deprecated, never deleted (no CASCADE): historical runs reference
them.

### Durable passage anchors

```sql
passage_anchors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  passage_id INTEGER REFERENCES passages(id) ON DELETE SET NULL,  -- live join, nullable
  item_code TEXT NOT NULL,
  transcript_kind TEXT NOT NULL,
  transcript_language TEXT NOT NULL,
  passage_seq INTEGER NOT NULL,               -- diagnostic; not stable across parser versions
  text_sha256 TEXT NOT NULL,                  -- sha256 of exact passage text (utf-8, no normalization)
  parser_version TEXT NOT NULL,
  -- snapshots so the anchor stays interpretable after passage deletion:
  text TEXT NOT NULL,
  speaker_code TEXT NOT NULL,
  t_start REAL NOT NULL,
  t_end REAL NOT NULL,
  timestamps_synthetic INTEGER NOT NULL,
  attribution TEXT NOT NULL,
  anchor_status TEXT NOT NULL DEFAULT 'live' CHECK(anchor_status IN ('live','stale')),
  created_at TEXT NOT NULL,
  UNIQUE(item_code, transcript_kind, transcript_language, passage_seq, text_sha256)
);
CREATE INDEX idx_anchors_passage ON passage_anchors(passage_id);
CREATE INDEX idx_anchors_lookup ON passage_anchors(item_code, text_sha256);
```

A re-anchor script (part of the ingest workflow after any re-ingest) re-binds
`passage_id` by exact `(item_code, kind, language, text_sha256)` match — exact
seq match preferred, unique-hash match accepted, ambiguous/missing → `stale`.
Anchors snapshot text/timestamps so citations and eval rows remain auditable
even while stale. Tags on `timestamps_synthetic=1` anchors are ineligible for
timestamped citations in L4.

### Model-run layer (predictions, regenerable)

```sql
model_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_key TEXT NOT NULL UNIQUE,               -- e.g. 'pilot-2026-07-fear-v1'
  purpose TEXT NOT NULL CHECK(purpose IN ('tagging','eval','adjudication')),
  model TEXT NOT NULL,                        -- exact model id, e.g. 'claude-sonnet-5'
  prompt_sha256 TEXT NOT NULL,                -- hash of full prompt template text
  prompt_version TEXT NOT NULL,
  concept_version_id INTEGER REFERENCES concept_versions(id),
  code_git_rev TEXT,
  params_json TEXT,                           -- temperature, retrieval query version, etc.
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','complete','failed')),
  started_at TEXT, completed_at TEXT,
  input_tokens INTEGER, output_tokens INTEGER,
  notes TEXT
);

-- A run may span several API batches (retries, size limits).
model_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
  batch_id TEXT NOT NULL,                     -- Anthropic Batch API id
  submitted_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'submitted',
  raw_results_path TEXT,                      -- archived JSONL on disk
  UNIQUE(run_id, batch_id)
);

-- One row per run x concept x candidate passage, INCLUDING negatives and
-- failures — precision/recall needs an auditable outcome for every request.
concept_predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
  concept_id INTEGER NOT NULL REFERENCES concepts(id),
  anchor_id INTEGER NOT NULL REFERENCES passage_anchors(id),
  custom_id TEXT NOT NULL,                    -- Batch API request custom_id
  outcome TEXT NOT NULL CHECK(outcome IN ('completed','api_error','parse_error','skipped')),
  relevance_label TEXT CHECK(relevance_label IN ('not_relevant','mention_only','substantive','unsure')),
  relevance_confidence REAL CHECK(relevance_confidence BETWEEN 0 AND 1),
  definition_like TEXT CHECK(definition_like IN ('yes','no','unsure','not_applicable')),
  definition_confidence REAL CHECK(definition_confidence BETWEEN 0 AND 1),
  rationale TEXT,
  error_detail TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, concept_id, anchor_id)
);
CREATE INDEX idx_predictions_concept ON concept_predictions(concept_id);
CREATE INDEX idx_predictions_anchor ON concept_predictions(anchor_id);

-- Evidence spans: one-to-many, with automated extractive verification.
prediction_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prediction_id INTEGER NOT NULL REFERENCES concept_predictions(id) ON DELETE CASCADE,
  quote TEXT NOT NULL,
  char_start INTEGER, char_end INTEGER,
  quote_verified INTEGER NOT NULL DEFAULT 0   -- exact substring of anchor text
);
```

`passage_tags` — the *accepted* concept tags that L4 consumes — is a **view**
(or promotion table, decided at implementation) over `concept_predictions`
joined to adjudications: a tag exists where relevance is substantive and either
human-accepted or above the promotion threshold established by the pilot. L4
never reads raw predictions from arbitrary runs.

### Eval layer (gold labels — authored, tracked in JSONL)

```sql
eval_sets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  sampling_json TEXT,                         -- seed, frame query, per-stratum weights
  created_at TEXT NOT NULL
);

eval_set_passages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  eval_set_id INTEGER NOT NULL REFERENCES eval_sets(id) ON DELETE CASCADE,
  anchor_id INTEGER NOT NULL REFERENCES passage_anchors(id),
  stratum_json TEXT,                          -- {decade, event_type, tier, kind, attribution, ts_quality}
  sample_weight REAL NOT NULL DEFAULT 1.0,
  UNIQUE(eval_set_id, anchor_id)
);

-- Gold labels, independent of any model run (captures false negatives).
-- Individual annotations are preserved; gold is the adjudicated consensus.
eval_labels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  eval_set_id INTEGER NOT NULL REFERENCES eval_sets(id) ON DELETE CASCADE,
  concept_id INTEGER NOT NULL REFERENCES concepts(id),
  anchor_id INTEGER NOT NULL REFERENCES passage_anchors(id),
  annotator TEXT NOT NULL,                    -- 'human:roman' | 'model:<run_key>'
  is_gold INTEGER NOT NULL DEFAULT 0,         -- 1 = adjudicated consensus row
  relevance_label TEXT NOT NULL CHECK(relevance_label IN ('not_relevant','mention_only','substantive','unsure')),
  definition_like TEXT NOT NULL CHECK(definition_like IN ('yes','no','unsure','not_applicable')),
  note TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(eval_set_id, concept_id, anchor_id, annotator)
);
CREATE INDEX idx_eval_labels_lookup ON eval_labels(concept_id, anchor_id);

-- Spot adjudication of production predictions outside the eval set.
adjudications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prediction_id INTEGER NOT NULL REFERENCES concept_predictions(id) ON DELETE CASCADE,
  verdict TEXT NOT NULL CHECK(verdict IN ('accept','reject','unsure')),
  adjudicator TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(prediction_id, adjudicator)
);

-- Cached, reproducible pilot metrics per run x concept x eval set.
run_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
  concept_id INTEGER NOT NULL REFERENCES concepts(id),
  eval_set_id INTEGER NOT NULL REFERENCES eval_sets(id),
  precision REAL, recall REAL, f1 REAL,
  definition_f1 REAL,
  citation_faithfulness REAL,                 -- share of evidence quotes verified verbatim
  computed_at TEXT NOT NULL,
  UNIQUE(run_id, concept_id, eval_set_id)
);
```

## Tracked authored files (`concepts/`, in git)

- `concepts/concepts.jsonl` — concepts, versions, aliases, relations.
- `concepts/eval/<set-name>.jsonl` — eval set membership (anchors by stable
  tuple, no passage text) + human labels/adjudications.
- `scripts/import_concepts.py` (later step) syncs JSONL → corpus DB; the DB is
  a materialization, git is the source of truth for authored rows.

## Metrics (how the pilot questions map to schema)

- **Precision/recall** per concept: join `concept_predictions`
  (outcome='completed') to gold `eval_labels` rows on `(concept_id, anchor_id)`;
  weight by `sample_weight`.
- **Definition-like classification**: same join on the `definition_like` axis.
- **Citation faithfulness**: `prediction_evidence.quote_verified` rate, plus
  human semantic-support spot checks via `adjudications`.

## Deliberate exclusions

- No L4 tables yet (`claims`, `claim_citations` come with plan step 5; they
  will reference `passage_anchors`).
- No FTS over rationale/evidence.
- No automatic cross-kind tag migration (whisper→manual) — by design.
