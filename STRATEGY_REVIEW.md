# STRATEGY.md — Adversarial Review (2026-06-24)

Multi-agent review of `STRATEGY.md`, grounded in the live DB + code. 6 dimensions →
44 findings raised → adversarial verification. **24 confirmed** across 4 dimensions;
the **schema-pipeline** and **scope-relevance** verifiers were cut off by a session
limit, so those 14 are *reviewer-raised, not adversarially verified* — 4 were
hand-verified afterward (marked ✅). See "Re-run" at the bottom to finish the rest.

## Verdict

The strategy is **fundamentally sound**: the principles (transcribe-everything-tag-
later, K-only-as-a-view, manual-subs-as-gold, supersede-by-`kind`), the L0→L4
architecture, and the evidence-based STT choice all hold up. **Every headline number
checks out exactly against the DB** (1,541 items / 1,963 h / 1,000 manual / 541
no-manual / 1,484+11+46 provenance). Issues are in: (a) a few real correctness bugs
in the Phase-1 parser that *hasn't been run yet*, (b) scope-gate gaps cheap to fix now
and expensive later, (c) governance sections the doc omits, (d) a stale-number cluster.

**Key context:** the canonical DB has **zero corpus rows** — Phase 1 is *code-complete
but never run*. Right now is a clean slate and the cheapest moment to fix P1 below.

## Ground truth (verified against catalog/krishnamurti.db, 2026-06-24)

- 1,541 items / 1,963.0 h total · 1,000 manual-subbed (1,281.2 h) · 541 no-manual (681.8 h)
- Whisper backfill: **315/541** done → only **226** items have no subtitle of any kind
- Audio downloaded 1,540/1,541 · video 581 · provenance 1,484 PDF + 11 Education + 46 channel
- Corpus tables (transcripts/segments/passages/passages_fts/speaker_labels) **do not exist** yet

## Priority 1 — fix BEFORE the first Phase-1 populate (clean slate now)

- **SP-1 ✅ (critical) — speaker-label regex fails on no-space-after-colon.** `LABEL_RE`
  (`parse_vtt.py:69`) needs whitespace after the colon. Verified: `Q:No.`/`K:Right?` →
  NO MATCH; `Q: No.` → match. Dialogue VTTs using no-space labels collapse to a single
  `ANN` segment (0 K passages) **silently**. Real file `BR79Q1` → 1 ANN segment; affects
  402 manual dialogue-type items, data-dependently. Fix: allow optional space after a
  short seed label, **and** add a validation gate (Q/D items must yield ≥2 speakers +
  non-trivial K-passage count, else WARN).
- **SR-1/SR-2 ✅ (high) — no item-level scope gate.** The Tier-C/EBM *exclusion* decision
  has no enforcement: `parse_vtt` ingests every manual item, only K-gate is per-speaker,
  no tier/`corpus_include` column exists. All 12 `US97EBM` excerpts carry gold K-subs →
  duplicate passages in FTS, exactly what the EBM deferral meant to prevent. Fix: add
  `items.corpus_include` at build time; `parse_vtt` skips non-corpus items.
- **SR-3 ✅ (medium) — EBM mislabeled `media_kind='film'` (dead code).** `build_catalog.py:327`
  returns `film` for EBM before the unreachable `excerpt` branch (329-330); DB confirms
  12 EBM = `film`, 0 `excerpt`. Reorder branches so excerpts are machine-distinguishable.

## Priority 2 — validate before spending money (Phase 4 Scribe ~$130-140)

- **STT-1 (high, confirmed) — WER eval is 5/6 clean Public Talks; cohort is ~54%
  multi-speaker discussion.** Diarization never measured. Run 3-5 representative
  discussion/dialogue items (DSG, DYP, a Bohm/Jayakar dialogue, DSS) reporting WER **and**
  diarization separately before committing the spend.
- **STT-3 (medium, confirmed) — "K = dominant speaker" is wrong-by-design for the ~115
  named-interlocutor dialogues.** Define the "ambiguous → manual review" trigger (e.g.
  2nd-speaker share >15%); force registry/manual mapping for named-interlocutor items.
- **STT-4 (medium, confirmed) — keyterm leakage controlled for only 1/6 eval items.**
  Production leakage is zero (fine); eval evidence is weaker than the flat "+4-8%". Re-score
  with per-item leave-one-out.

## Priority 3 — governance sections STRATEGY.md omits (all confirmed gaps)

- **Rights & distribution (medium)** — derived corpus + verbatim L4 notes from KFT-copyright
  material; risk hinges on unstated distribution scope. Classify artifacts, state scope,
  confirm the git remote holding the 1,494-summary DB is private.
- **Backup/durability (medium)** — gold manual VTTs live only in gitignored self-evicting
  iCloud (text not in DB yet). Running `parse_vtt` lands text in the git-tracked DB; state a policy.
- **End-product faithfulness eval (medium)** — STT has rigorous WER; the semantic L3/L4 layer
  has no gold set / precision-recall / hallucination guard. The 500-passage pilot isn't a measured eval.
- **Definition-of-done & maintenance (medium)** — no success metric for the concept map; no
  ingest/re-tag cadence (the 2026-06-12 scan already added 46 items absent from all PDFs).

## Priority 4 — parser hardening (schema-pipeline; ✅ = hand-verified)

- **SP-2 ✅ (medium)** — rebuild wipes all L2 (corpus tables excluded from `PHASE2_TABLES`,
  recreated empty). Harmless now; data loss once L3 tags reference passage IDs. Add an
  end-of-build warning + `--reparse` step.
- **SP-3 ✅ (low-med)** — `PRAGMA foreign_keys` is OFF (`=0`); `ON DELETE CASCADE` is a no-op.
  Set `foreign_keys=ON` on connect or drop the cascade clauses.
- **SP-4 (medium)** — Q→K `answers_seq` linking is fragile (inherits SP-1; misses K reading
  questions aloud). Treat as best-effort; defer robust pairing to L3.
- **SP-5 (medium)** — `split_embedded()` interpolates split timestamps by word position;
  carry a `t_synthetic` flag.
- **SP-6 (medium)** — iCloud SPOF: 15s materialize budget + silent zero-cue skip = coverage
  holes that look like missing files. Pre-materialize in one batch; persist a skip/retry list.
- **SP-7 (low)** — registry "≥2× recurrence admits any token" can inject refrain phrases as
  speakers; constrain non-seed admission to short, cue-start labels.
- **SR-4 (medium)** — "filtered view via speaker tag" needs item-level QA backstop (broken
  tags → silent under-coverage), not just a query. Ship the Phase-1 %-ANN/%-UNK stats report
  as an acceptance gate before locking tier decisions.
- **SR-5 (medium)** — stale "~147h young-people" matches no grouping; `TS` "Talks to Students"
  is Tier A in prose but grouped with young-people in code. Enumerate Tier C as an explicit code set.
- **SR-6 (low)** — interim whisper transcribes Tier-C items it will exclude, and strands all
  9 films (a quiet carve-out vs "transcribe everything"). Decide the film/Tier-C question for the paid 541.

## Priority 5 — data hygiene (stale-number cluster; all confirmed, low)

One regen script kills the class (every headline already checks out; only per-bucket figures drift):

| Claim in STRATEGY.md | Stated | Actual |
|---|---|---|
| Whisper backfill | 111/541 | **315/541** (226 truly sub-less) |
| Phase 4 cohort | 519 items | **541** |
| Pipeline-order log | 975 subtitled | **1,000** |
| Public Talks T | 772 h | **783.9 h** |
| Public Discussions | 229 h | **232.0 h** (D) |
| Young-people | ~147 h | matches no grouping (DYP 81 / +TYP 91 / +DS 120) |

Plus: `TYP`/`TR` "Public Talk" items excluded by a bare-`T` filter (tier on label or an
explicit code list; resolve TYP = Tier A or C).

## Re-run / resume (finish the cut-off verification)

The workflow was paused by a session limit. To resume in the **same session** (cached
agents return instantly; only the ~20 failed verifiers + synthesize re-run):

- scriptPath: `~/.claude/projects/-Users-kryzh-claude-jiddukrishnamurti-jiddukrishnamurti/39f6c8cc-ea4c-4bb1-8b07-44ec3782e23b/workflows/scripts/strategy-review-wf_55ac5e84-6ea.js`
- resumeFromRunId: `wf_55ac5e84-6ea`

If a new session, re-run the script fresh (re-does everything, produces a complete result).
Raw findings + verifier notes: workflow output (scratchpad, ephemeral) — captured above.
