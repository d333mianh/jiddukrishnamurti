# Teachings Corpus — Strategy

The single strategy document for this project. Everything that was once split
across `STRATEGY_REVIEW.md`, `gpt-05JUL-plan.md`, and `obsidian/roots/Open
Decisions.md` now lives here.

**Goal:** build the most complete structure of the meaning, ideas, and
fundamentals of J. Krishnamurti's teachings on top of the complete KFT
recordings archive (1,541 items, 1,963 h) — every concept traceable to his own
words, cited back to the recording with a timestamp.

**How to read this file.** Four sections, each holding exactly one kind of fact:

| Section | Holds | Rule |
|---|---|---|
| [Principles](#principles) · [Architecture](#layer-architecture) | how the system is built | changes rarely |
| [Where things stand](#where-things-stand) | live numbers and state | refreshed from the DB |
| [Open questions](#open-questions) | undecided calls | delete when answered, log it |
| [Decision log](#decision-log) | history, oldest first | append-only, never rewritten |

When the log and "Where things stand" disagree, **"Where things stand" wins** —
log entries record what was believed on their date.

## Principles

1. **Transcribe everything, delete nothing.** Relevance is expressed as tiers,
   tags, and filtered views — never by excluding items from transcription.
   Changing our mind later costs a query, not a re-run.
2. **The "teachings corpus" is a filtered view: K-only text.** Audience
   questions, interviewers, and announcers are stored and speaker-tagged, not
   removed.
3. **Questions are context metadata.** A question ("What is meditation?") is
   often the cleanest topic label for the answer that follows.
4. **Manual KFT subtitles are the gold standard** (1,000 items, 1,281 h). The
   pipeline is built and validated on them first; better STT supersedes weaker
   transcripts later by `item_subtitles.kind`, never by overwriting.
5. **Every claim carries a citation.** A synthesis sentence with no passage and
   no timestamp behind it does not ship.

## Layer architecture

| Layer | Content | Where it lives | State |
|---|---|---|---|
| L0 Archive | media (m4a/mp4), manual VTTs, catalog | `catalog/krishnamurti.db` (tracked) + `library/` (iCloud, gitignored) | done |
| L1 Transcripts | one row per ingested transcript file + provenance | `corpus/krishnamurti-corpus.db` (gitignored) | done |
| L2 Segments | speaker-attributed turns → passages, FTS5 over K-only text | same corpus DB | done for manual sources |
| L3 Concepts | 36 roots + aliases/relations + passage tagging | `concepts/concepts.jsonl` (tracked) → corpus DB | registry closed, tagging pending |
| L4 Synthesis | Obsidian notes, timestamped `youtu.be/ID?t=SECONDS` citations | `obsidian/` (tracked) | vault scaffolding generated |

The **two-database split** is deliberate: the catalog is small, tracked, and is
canonical pipeline state; the corpus is large, generated, and gitignored. A
catalog rebuild never touches corpus tables — corpus rows are keyed by stable
item code, so they survive.

### L2 — the citation unit

- **Speaker tags:** `K`, `Q` (anonymous audience), named interlocutors (per-item
  registry mapping VTT initials — `DB:` David Bohm, `WR:` Walpola Rahula, … — to
  people), `ANN` (announcer/housekeeping), `UNK`.
- **Granularity:** the speaker turn is atomic; K's long monologue turns are
  sub-chunked at sentence boundaries into ~150-word passages (260-word hard max,
  short tails merged), each with its own `t_start`/`t_end`. ~60–90 s of speech ≈
  one developed thought — the right size for citation, embeddings, and links.
  Passages merge upward for display; never the reverse.
- **Attribution provenance** is recorded per segment and passage (`label`,
  `inherit`, `assumed_k`, `q_boundary_heuristic`), and interpolated split
  timestamps are flagged synthetic. Nothing silently pretends to be certain.

### L3 — the 36 roots

The registry is **closed at 36 roots** in `concepts/concepts.jsonl`, grouped
into four *non-sequential facets* of 8 / 9 / 11 / 8. Facets are entry-points,
not stages and not a taxonomy with a quota — freedom is at the beginning of
inquiry, not a reward — so no root was placed to even out a count. The set was
triangulated from four independent sources: K's core vocabulary, corpus FTS
frequencies, the published book/chapter canon, and an 18-book content-group map
(`content_groups.md`, 54 groupings).

Tagging is two-stage:

1. *Local, free:* lexicon term-matching + local embeddings for clustering and
   per-concept candidate retrieval.
2. *LLM judgment via the Claude Batches API* (50% discount, prompt-cached
   registry): does a passage substantively address a concept, merely mention it,
   or define it? ~80k K-passages ≈ $10–45 one-off depending on the model tier.

### The I Ching navigation layer — archived

Added and then **archived on 2026-07-25**: parked pending a decision, not
rejected. Everything lives in `archive/iching/` (data, module, tests, the
generated notes, and the patch that removed the rendering code), with restore
instructions in `archive/iching/README.md`. It was navigation only, so nothing
else depends on it — `concepts.jsonl` was and stays canonical.

## Where things stand

Live numbers, refreshed from the DB on **2026-07-25**.

**Archive (L0)** — 1,541 items / 1,963.0 h. Provenance: 1,484 Full-Length PDF +
11 Education Directory (section 10A) + 46 @KFoundation channel (11A).
2,121 media files downloaded.

**Transcript sources** — **every item now has a downloaded transcript of some
kind**:

| Kind | Status | Items |
|---|---|---|
| `manual` (KFT-edited, gold) | downloaded | 1,000 |
| `whisper-large-v3-turbo` | downloaded | 540 |
| `kft-web-transcript` (untimed, `BR74FPL`) | downloaded | 1 |
| `elevenlabs-scribe-v2` | planned | 540 |

**Corpus (L1/L2)** — 988 transcripts ingested (tier A 809 / B 164 / C 15),
139,549 segments, 153,360 passages, of which 80,324 are K-passages and 80,030
are in `passages_fts` (tiers A/B only).

**Tiers** — A 1,197 · B 311 · C 21 · X 12.

**Largest event types** — T Public Talks 637 / 783.9 h · D Public Discussions
172 / 232.0 h · DSS 123 / 172.6 h · DSG 103 / 143.3 h · DT 72 / 107.5 h ·
S Seminars 69 / 113.7 h · Q Q&A 66 / 91.9 h · DYP 61 / 81.1 h · DS 35 / 38.5 h ·
CB 31 / 44.5 h · CA 20 / 19.7 h · EBM 12 / 5.8 h, plus a long tail.

**Concepts (L3)** — 36 active roots + 3 deprecated tombstones (`sacred` →
`religious-mind`, `self` → `self-knowledge`, `word-naming` → `thought`). The
tombstones stay so predictions keyed to their ids remain resolvable; they are
excluded from the vault and from pilot prompts by `status`. Only one tagging
pilot has run — `pilot-2026-07-r1`, 500/500 on Sonnet 5, 2026-07-07, binary
labels. It predates every registry change since, so its results **do not map
onto the current 36**.

**Vault (L4)** — 37 generated notes (36 concepts + Map).
`scripts/build_concept_vault.py --check` gates staleness *and* dead wikilinks.

## Relevance tiers

Tiers are tags, never deletions. Assignment is centralized in
`segment_schema.corpus_tier_for_event_type()`; unknown event types default to B
with a warning.

| Tier | Content | Treatment |
|---|---|---|
| A | Public Talks, Q&A, seminars, talks to students, named dialogues | ingested + in FTS |
| B | Conversations, interviews, group and young-people discussions | ingested + in FTS |
| C | Films and documentaries | ingested, FTS-excluded pending provenance review |
| X | The 12 `EBM` compiled excerpts | excluded (duplicate text of full-length talks) |
| strip always | announcer intros, housekeeping, `[applause]`, anonymous Q turns | never in the K-only view (Q kept as context metadata) |

## STT

**Interim local pass — complete.** All 541 items lacking manual subs were
transcribed with whisper.cpp **large-v3-turbo, `-mc 0`, no prompt**
(`scripts/transcribe_whisper.py`). Pilot evidence behind those exact settings:
turbo beat large-v3 on both test clips (5.05% / 6.69% vs 5.50% / 9.43% strong
WER — large-v3 hallucinates on hard material) and runs ~8× realtime on the M1;
without `-mc 0` the context feedback loop produced a 6× repeated sentence (16.1%
WER); whisper's initial prompt is silently ignored under `-mc 0` and degrades
quality with `-mc 224`, so keyterm prompting is whisper-inapplicable. Do not
"improve" these settings without re-reading the docstring.

**Final quality pass — chosen, not yet bought.** **ElevenLabs Scribe v2 +
keyterm prompting**, decided after a 6-item evaluation across 1949–1984 (see
`compare/`):

- Strong-normalized WER vs manual subs 3.3–7.9% across hard cases; true
  content-error rate 0.8–2.1% even on the 1949 tape and a Q&A with audience
  cross-talk. whisper large-v3: 9.0% on the *easiest* item. Grok-stt: ~2×
  Scribe's content errors ("Jayakrishna Murty").
- Keyterms: top-1000 lexicon mined from the manual-sub corpus
  (`compare/build_keyterms.py`), sent as one multipart field per term; also
  nudges output toward KFT/British house style. ~4–8% relative WER gain.
- Settings: `diarize=true`, `timestamps_granularity=word`, keyterms.
- Cost ≈ $0.22/h + $0.05/h keyterms ≈ **$130–185** for the 541-item / ~682 h
  cohort. Ops: ≤3–4 concurrent files (a long request can consume four
  concurrency slots), materialize iCloud-evicted audio first (`brctl download`).

## Phases

1. **Segments** — schema + VTT parser, L2 for all manual items, FTS5, stats.
   ✅ done.
2. **Concepts** — registry seed and closure; tagging pilot; full tagging pass.
   Registry ✅ closed; pilot re-score and the full pass are open.
3. **Synthesis prototype** — 2–3 concept notes end-to-end in Obsidian with
   timestamped YouTube links. Vault scaffolding ✅; notes pending L3 tags.
4. **STT backfill** — Scribe v2 + keyterms on the 541-item cohort, feeding the
   proven pipeline, then re-run L3 over the new passages. Pending spend.

## Open questions

Undecided calls, most actionable first. Questions only — reasoning belongs in
the log once a decision is made. When a question is answered, log it and delete
it here.

1. **Pilot re-score — model arm(s) and spend.** Re-score the 500-passage eval
   set against the final 36 roots with the full
   `substantive` / `mention_only` / `definition_like` labels. Needs a human call
   on which arms to run and approval of the spend; items 2 and 3 wait on it.
2. **Model for the full ~80k-passage tagging pass.** Resolved by the re-score on
   a quality-per-dollar basis — the reason to run more than one arm.
3. **New-root validation.** The re-score is the first evidence on `listening`,
   `will-effort`, and `responsibility`, none of which existed at r1. It also
   measures confusion among self-knowledge/consciousness,
   awareness/observer-observed/listening, truth/what-is,
   conflict/violence/will-effort, and desire/pleasure.
4. **Rights & distribution — the repo is still public.**
   `github.com/d333mianh/jiddukrishnamurti` is a public remote holding the
   catalog DB (1,494 item summaries) and, in future, verbatim L4 quotation from
   KFT-copyright material. Transcript text itself is gitignored. Decide the
   distribution scope and either make the remote private or state explicitly
   what may be published. **Blocks publishing any L4 note.**
5. **Backup & durability.** The gold manual VTTs and all media live only in
   self-evicting iCloud; the generated corpus DB is gitignored and exists in one
   copy. No offsite or encrypted backup policy exists. Cheap to fix, expensive
   to have skipped.
6. **Faithfulness evaluation for L3/L4.** STT has rigorous WER; the semantic
   layer has no gold set, no precision/recall, and no hallucination guard. The
   500-passage pilot is a labelling run, not a measured eval. Define the gold
   set and the acceptance bar before the full tagging pass.
7. **Definition of done, and maintenance cadence.** No success metric for the
   concept map, and no re-ingest/re-tag cadence — the 2026-06-12 channel scan
   already added 46 items absent from every PDF, and that will happen again.
8. **Diarization is unmeasured before the Scribe spend.** The WER eval was 5/6
   clean Public Talks; the paid cohort is ~54% multi-speaker discussion. Run
   3–5 representative items (DSG, DYP, a Bohm or Jayakar dialogue, DSS) and
   report WER **and** diarization accuracy separately before committing.
9. **"K = dominant speaker" is wrong-by-design for the ~115 named-interlocutor
   dialogues.** Define the ambiguous → manual-review trigger (e.g. second-speaker
   share > 15%) and force registry mapping for those items before ingesting any
   Scribe output.
10. **Keyterm-leakage evidence is thin.** Leave-one-out was controlled for only
    1 of 6 eval items, so the flat "+4–8%" is weaker than it reads. Production
    leakage is zero, so this affects the claim, not the plan. Re-score with
    per-item leave-one-out if the number ever needs to be defended.
11. **Tier C confirmation.** Films and documentaries stay FTS-excluded pending
    provenance review; the ~30 short interviews sit in B by default. Resolve
    with the corpus stats (%-K-speech per event type) plus a call. Low urgency.
12. **`EBM` excerpt provenance.** No mapping exists from each of the 12 compiled
    excerpts to the source talk it was cut from. Build it only if passage-level
    dedup is ever needed; their 12 curated themes are retained as a KFT-authored
    thematic scaffold.

## Decision log

Append-only, oldest first. Entries are never rewritten.

- **2026-06-11** — transcribe everything; relevance as tags and views; Q&A
  filtered at speaker-turn level, not item level; questions kept as context
  metadata.
- **2026-06-11** — STT provider: Scribe v2 + keyterms (over grok-stt and local
  whisper), based on a 6-item WER eval.
- **2026-06-11** — citation granularity: speaker turn, with K monologues
  sub-chunked at sentence boundaries.
- **2026-06-11** — concept tagging: local embeddings/lexicon prefilter + a
  Claude Batches API judgment pass; model picked by pilot.
- **2026-06-11** — pipeline order: build and validate everything on the 1,000
  subtitled items before spending on STT.
- **2026-06-11** — interim local transcription launched: whisper.cpp
  large-v3-turbo + `-mc 0`, no prompt. Scribe v2 remains the final-quality pass,
  superseding by `item_subtitles.kind`.
- **2026-06-20** — counts refreshed. The 2026-06-12 @KFoundation channel scan
  added 46 recordings absent from all PDFs (section 11A), so the archive is
  **1,541 items / 1,963 h**, split 1,000 subtitled / 541 no-subs.
- **2026-06-21** — the 12 `US97EBM` "Beyond Myth & Tradition" excerpts are
  deferred, not deleted. They are KFA-made posthumous compilations of excerpts
  from talks already in the archive, so their text duplicates full-length
  recordings. Keep the media and gold subs as a browsable topical-intro layer;
  **exclude from the searchable corpus** to avoid duplicate passages and
  ambiguous citations.
- **2026-06-24** — adversarial review of this strategy against the live DB and
  code. Verdict: fundamentally sound; every headline number checked out exactly.
  It raised the parser and scope-gate fixes that became the next month's work
  (no-space speaker labels, item-level scope gate, `excerpt` vs `film`
  media_kind, `PRAGMA foreign_keys`, synthetic split timestamps, constrained
  speaker-registry admission, the stats report as an acceptance gate) — all
  since implemented — plus the governance gaps now carried as open questions
  4–7.
- **2026-07-05** — `BR74FPL` is the sole item whose video remains private and
  undownloadable. KFT publishes the complete official prose transcript, so it is
  archived as `kind='kft-web-transcript'` (`format='txt'`) with source and
  checksum metadata. It has **no timecodes**: never manufacture VTT cues or
  timestamped citations from it, and keep it out of timed L2 passages.
- **2026-07-05** — corpus relevance recorded per item as explicit tiers A/B/C/X
  (replacing the boolean `corpus_include`, which survives as a derived column
  that is 0 only for X). Tiers A/B/C stay fully ingested; FTS holds K passages
  from A/B only. Unknown future event types default to B with a warning.
- **2026-07-05** — the generated corpus moved to its own gitignored
  `corpus/krishnamurti-corpus.db`, attaching the catalog read-only. A temporary
  parse of 809 manual items produced a 112 MB SQLite file — unsuitable for git,
  and a catalog rebuild would have wiped it. Track schemas, parser versions,
  manifests, counts, checksums, and QA reports; never transcript text.
- **2026-07-07** — L3 concept registry finalized as **36 fundamental "roots"**,
  grouped as four non-sequential facets. Reviewed by both advisors (Codex
  gpt-5.5 high + Opus 4.8 high); fixes applied: de-conflated joy from "Desire &
  Pleasure", added **Comparison & Measurement** and **The Word & Naming**,
  renamed "psychological revolution" → **Transformation & Mutation** and
  "Consciousness, the Brain & the Mind" → **Consciousness & Its Content**,
  removed the misleading `reality` alias from Truth, disjoined the
  awareness/truth criteria, de-duplicated cross-owned aliases. Each entry
  carries definition, include/exclude criteria, aliases (with period notes for
  K's shifting vocabulary), and typed relations.
- **2026-07-07** — the L3 tagging pilot (`pilot-2026-07-r1`) drifted from the
  plan in two ways, now recorded: it ran **Sonnet 5 single-arm**, not the
  written two-model comparison, and used **binary** applies/confidence labels
  rather than the full label set. Model choice for the full pass stays open.
- **2026-07-16** — book-TOC gap check: "listening" / "the art of listening" and
  "the nature of hurt" resolved as aliases (on awareness and relationship
  respectively); `responsibility` left untagged, then promoted the same day.
- **2026-07-16** — **`religious-mind` + `sacred` merged; `responsibility`
  promoted to root #36** (set stays 36). The pair was the closest in the
  registry — the religious mind is *defined* as the mind that may come upon the
  sacred — so the probation merge was decided ahead of the pilot.
  `religious-mind` absorbed sacred's aliases; `sacred` kept as a deprecated
  tombstone. The freed slot became `responsibility`, grounded in "you are the
  world".
- **2026-07-25** — **registry closed at a final 36; no root is provisional or on
  probation any more.** (a) `self` folded into **`self-knowledge`** — the
  knowing and the thing known are one movement, so a per-passage split was never
  going to be reliable. (b) `word-naming` folded into **`thought`** — naming is
  an operation of thought, not a field beside it. (c) Two roots took the freed
  slots: **`listening`**, promoted out of `awareness`'s aliases (K gives the art
  of listening sustained independent treatment, and a book chapter), and
  **`will-effort`**, which claims `effort` from `conflict` and `discipline` from
  `order` — both previously owned it only as an alias, leaving will, resistance,
  suppression, and escape with no owner. Facets are now 8/9/11/8; the old 4×9
  symmetry was tidy but never load-bearing, and was not worth moving roots into
  facets they don't belong in.
- **2026-07-25** — **I Ching navigation layer added** as an additional way into
  the 36 roots, after comparing two competing drafts. The trigram-gate
  construction won because 36 falls out of it (8 self-pairs + 28 pairs) instead
  of being asserted, and because Unicode hexagram glyphs render in Obsidian with
  no plugin. Framing is **navigator, not oracle**: no judgments, no line texts,
  no advice — a cast selects what to inquire into. The layer is marked
  `provisional` and is navigation only; `concepts.jsonl` stays canonical. The
  two source drafts (`obsidian/roots/reference/i-ching-cc.md` and
  `i-ching-gpt.md`) were deleted — the generated Navigator note plus
  `scripts/iching_data.py` supersede them, and keeping hand-written drafts
  beside generated output is exactly the drift this cleanup removed.
- **2026-07-25** — **I Ching layer archived to `archive/iching/`** the same day
  it landed: worth keeping, not yet decided on. The vault drops from 46 notes to
  37, the concept notes lose their bridge callout and `iching_gates` frontmatter,
  and `scripts/build_concept_vault.py` no longer imports anything I Ching. A
  test (`test_iching_layer_stays_archived`) keeps the layer out of the generated
  vault while it is parked. Restoring is a documented four-step reversal, not a
  rewrite.
- **2026-07-25** — **documentation consolidated into this file.**
  `obsidian/roots/Open Decisions.md`, `STRATEGY_REVIEW.md` (2026-06-24 review,
  every P1 item implemented, the rest folded into open questions 4–11), and
  `gpt-05JUL-plan.md` (2026-07-05 plan, executed) were merged here and deleted.
  Two hand-maintained lists had already drifted apart once. The rule now: each
  fact lives in exactly one section of one file — settled state in "Where things
  stand", open calls in "Open questions", history in this log. `AGENTS.md` was
  likewise merged into `CLAUDE.md`. Vault notes link to
  `reference/Strategy.md`, which is a thin pointer here.
- **2026-07-25** — the corpus `concepts` table was re-synced from
  `concepts.jsonl` (`scripts/import_concepts.py`): it had drifted to 37 rows
  against the JSONL's 39. Now 36 active + 3 deprecated. The importer is the only
  supported path from registry to DB — never hand-edit the table.
