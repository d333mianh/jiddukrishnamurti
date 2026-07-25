---
tags: [krishnamurti, root, reference]
---
# L3 Schema

How the concept layer is stored. **Canonical, full version:** `L3-SCHEMA.md` at
the repo root (reviewed by two advisors, 2026-07-06). This note is a map.

## Two-DB split

- **Authored, tracked JSONL** (`concepts/`) — concepts, definitions, aliases,
  relations, gold eval labels. Human-authored, never regenerable, no copyrighted
  passage text (anchors only). `scripts/import_concepts.py` materializes it into
  the corpus DB.
- **Corpus DB** (`corpus/krishnamurti-corpus.db`, gitignored, regenerable) —
  model predictions and derived metrics; rebuildable from archived batch outputs.

## Key tables

- **`concepts`** — slug, name, status (`pilot|active|deprecated`).
- **`concept_versions`** — definitions are **versioned**; a model run pins the
  exact version it saw (so metrics stay comparable after a wording change).
- **`concept_aliases`**, **`concept_relations`** — K's shifting vocabulary and
  the typed links you see under "Related roots" on each concept note.
- **`passage_anchors`** — durable identity for a passage. Nothing L3 cascades off
  `passages` (re-ingest makes `passages.id` unstable); anchors survive re-ingest
  and get re-attached by a re-anchoring pass.
- **`concept_predictions`** — one row per (run, concept, passage): relevance
  (`substantive|mention_only|not_relevant`), confidence, definition-like.

## Tagging pipeline

1. **Local prefilter** (free) — lexicon term-match + embeddings to shortlist
   candidate passages per concept.
2. **LLM judgment** via the **Claude Batches API** (50% discount, prompt-cached
   registry) — substantive vs mention-only, and definition-like. Run by
   `scripts/run_concept_pilot.py`. See [[Strategy]] for the model choice.

---
*Hand-authored summary. Read `L3-SCHEMA.md` for the authoritative DDL.*
