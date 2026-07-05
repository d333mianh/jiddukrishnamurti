# GPT 05 July Project Plan

Date: 2026-07-05

## Current State

- Transcript-source coverage is complete: 1,541/1,541 catalog items.
- The 541 formerly missing sources comprise 540 local Whisper transcripts and
  one official untimed KFT web transcript (`BR74FPL`).
- L1/L2 remains empty: zero corpus transcripts, segments, passages, or FTS rows.
- Draft PR #1 contains the completed source-coverage work.

## Review Findings

1. **The parser is not production-ready.** A read-only scan of 877/988 included
   manual transcripts found 100 items (11.4%) with zero K passages: 79 Public
   Talks and 17 Q&As. Recurring prose such as “So we are asking:” is also
   misclassified as a speaker.
2. **Whisper VTTs lack speaker attribution.** The current parser classifies
   sampled Whisper transcripts entirely as `ANN`, so they cannot safely feed a
   K-only FTS index.
3. **The corpus cannot remain in the tracked catalog DB.** A temporary parse of
   809 manual items produced a 112 MB SQLite file. The full database will be
   larger and unsuitable for normal Git/GitHub storage.
4. **The repository is public.** Full KFT transcript text and future synthesis
   quotations require an explicit rights and distribution policy.
5. **Scope enforcement is incomplete.** Only EBM excerpts are excluded in code;
   films, young-people discussions, and interviews remain included while their
   Tier C status is unresolved.

## Execution Plan

### 1. Separate Corpus Storage and Resolve Privacy

- Keep `catalog/krishnamurti.db` as the tracked catalog and pipeline-state DB.
- Create `corpus/krishnamurti-corpus.db` for generated L1/L2/FTS data.
- Gitignore the corpus DB and attach the catalog DB read-only for joins.
- Track schemas, parser versions, manifests, counts, checksums, and QA reports;
  do not track transcript text.
- Make the GitHub repository private.
- Define an encrypted/offsite backup policy for the corpus DB and source VTTs.

This split also prevents catalog rebuilds from deleting the corpus.

### 2. Harden `parse_vtt.py`

- Add regression fixtures for `BR79Q1`, unlabeled talks, embedded `K:` labels,
  no-space labels, and prose-colon false positives.
- Detect trusted speaker labels embedded inside cues.
- Reject arbitrary recurring multiword labels unless explicitly registered.
- Add event-aware handling for entirely unlabeled talks.
- Mark word-interpolated timestamps as synthetic.
- Add `corpus_stats.py` with per-item and per-event speaker/coverage metrics.

Acceptance gate:

- Zero collapsed Tier-A manual items.
- Reviewed ANN/UNK ratios for every event type.
- Representative timestamp and speaker spot checks pass.
- Re-running ingestion is idempotent.

### 3. Populate and Validate the Manual Corpus

- Ingest all 1,000 manual sources into archival L1.
- Exclude the 12 EBM compilations from searchable FTS, not from archival L1.
- Generate the complete QA report before accepting the corpus.
- Use observed speaker statistics to decide treatment of young-people/student
  discussions, films/documentaries, interviews, `TYP`, and `TR`.
- Replace the Boolean `corpus_include` model with explicit tier and provenance
  metadata.

### 4. Build the L3 Concept Pilot

- Add concept, alias, relation, passage-tag, model-run, and adjudication schemas.
- Create a stratified, human-reviewed evaluation set.
- Pilot three concepts over approximately 500 passages.
- Measure precision, recall, definition-like classification, and citation
  faithfulness before scaling.
- Select the current best model and pricing when the pilot runs. Anthropic Batch
  currently discounts input and output tokens by 50%:
  https://platform.claude.com/docs/en/about-claude/pricing

### 5. Prototype L4 Synthesis

- Generate 2–3 concept notes only after the L3 pilot passes.
- Require every substantive claim to link to a passage and recording timestamp.
- Keep generated synthesis separate from source text and label model-authored
  interpretation explicitly.
- Review quotation length and distribution policy before publishing notes.

### 6. Stage the Final Scribe Pass

- Do not spend until the manual L1/L2 pipeline is accepted.
- First test diarization on representative multi-speaker items: DSG, DYP, DSS,
  named conversations, interviews, and Q&A.
- Score transcription accuracy and speaker attribution separately.
- Current Scribe v2 capabilities include word timestamps, diarization, and up to
  1,000 keyterms:
  https://elevenlabs.io/docs/overview/capabilities/speech-to-text
- Current API pricing is approximately $0.22/hour plus $0.05/hour for keyterms:
  https://elevenlabs.io/pricing/api?price.section=speech_to_text
- Full 681-hour pass: approximately $184 before tax.
- Multi-speaker/film cohort first: 289 items, 369.5 hours, approximately $100.
- Limit concurrency to at most three long files because each long Scribe request
  may consume four concurrency slots.

## Immediate Milestone

The next implementation milestone is:

1. Split the generated corpus into a separate gitignored database.
2. Add parser regression tests and fix speaker classification.
3. Add corpus QA/statistics tooling.
4. Populate the manual corpus in the derived DB.
5. Review the QA report and settle corpus tiers before starting L3.

No paid API work is required for this milestone.
