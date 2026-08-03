# Teachings Corpus — Strategy

The single strategy document for this project. `CLAUDE.md` is the operational
contract — *how* to work in the repo; this file is *why* the work is shaped the
way it is, and what happens next.

**Goal:** build the most complete structure of the meaning, ideas, and
fundamentals of J. Krishnamurti's teachings on top of the complete KFT
recordings archive — every concept traceable to his own words, cited back to the
recording with a timestamp.

**How to read this file.** Five sections, each holding exactly one kind of fact:

| Section | Holds | Rule |
|---|---|---|
| [Plan](#plan) | what happens next | the only section describing future work |
| [Principles](#principles) · [Architecture](#layer-architecture) | how the system is built | changes rarely |
| [Where things stand](#where-things-stand) | live numbers | generated from the databases; never hand-edited |
| [Open questions](#open-questions) | undecided calls | delete when answered, log it |
| [Decision log](#decision-log) | history, oldest first | append-only, never rewritten |

Two rules hold the file together.

When the log and "Where things stand" disagree, **"Where things stand" wins** —
log entries record what was believed on their date.

And **everything is referenced by slug, never by position**: `Q-scribe-needed`,
not "open question 5". Answering a question deletes it, which renumbers every
question after it, which silently repoints every reference to it. That is not
hypothetical: by 2026-07-26 four references had rotted, and two different
questions had each been "open question 4".

## Plan

Phases carry slugs for the same reason questions do.

**Done.** `P-segments` — schema, VTT parser, L2 for every manual item, FTS5,
stats. `P-concepts` — registry seeded and closed at 36 roots.

**`P-durability` — get the recovery off this machine. Do this first; it is
minutes of work.** The 82 transcripts recovered on 2026-07-26 exist in exactly
one place: this machine's iCloud tree. The backup archive is dated 2026-07-25 and
predates them, the tracked `corpus/krishnamurti-corpus.db.zst` decompresses to
the pre-recovery 906 transcripts against 988 live, `library/` is gitignored, and
the recovery commits are unpushed — so no copy exists in git, in the archive, or
off this machine. Deliverable: `backup_corpus.py`, a refreshed snapshot (this is
the kind of milestone `corpus/README.md` reserves them for), and the branch
pushed. Two retracted claims go with it: `corpus/README.md` still says "all 111
were ingested", which the 2026-07-26 log entry corrected, and the `--verify`
count reads 25/25 there and in `CLAUDE.md` against 83 citations.

**`P-notes` — cited notes. The critical path, and the only phase that produces
the thing this project is for.** Per root: `retrieve_concept.py` → read the
candidates → file the keepers in `concepts/citations.jsonl` → `--sync` →
regenerate the note. `fear` ✅, `attachment` ✅ and `observer-observed` ✅;
**33 roots to go**. Each is a bounded session of reading, needs no model spend,
and ships independently.

**`P-retrieval` — fix what feeds every note.** Ahead of the remaining roots,
because it makes each of them cheaper and none of it needs a model. Measured
across all 36 roots on 2026-08-03, and the measurement reordered the phase: the
fix this entry used to specify turns out to be nearly a no-op, and the obvious
next idea is a regression. The order below is the order the evidence supports.

1. **A gold-set gate, first.** The 83 curated citations are the only ground
   truth this project has about what retrieval *should* return, and nothing
   measures against them. Recall@300 per cited root at the CLI's real defaults,
   as a test: it is a few dozen lines, it strengthens with every root cited, and
   without it no query change can be distinguished from a regression.
2. **Then strip stopwords — for honest numbers, not better ranking.** 21 of the
   36 roots carry stopword terms, and the pools they inflate are enormous
   (`beauty` 30,774 candidates against 2,066 stripped; `authority` 30,776
   against 4,207). But BM25's IDF was already discounting `the` to nearly
   nothing: the top 60 moves by a mean of 4.5 passages, and all three cited
   roots keep 100% recall. The defect corrupts the *reported supply*, not what a
   curator reads — which matters because the supply report below is worthless
   until it is fixed, and not at all because the reading changes. Not a blanket
   list: `will` is `will-effort`'s own name colliding with the auxiliary verb.
3. **Do not convert multi-word aliases into phrase queries.** Measured, and it
   is a regression: phrase-only retrieval drops 15 of `observer-observed`'s 30
   curated passages, and `"what is"` *raises* `truth`'s pool to 10,323 because
   it is among the commonest two-word spans in English rather than only K's term
   of art. If phrases go in at all, they go in beside the word terms or as an
   explicit per-alias match mode in the registry — never as a transform inferred
   from the prose.
4. **Then the per-root report and an ordered queue for the 33** — candidate
   supply and alias coverage, which is what this phase was originally for.

The second defect is untouched by all of that: a root can own K's idea under one
grammatical form while missing another, which is how `observer-observed` nearly
lost the whole controller/controlled theme. Alias coverage is a reading problem,
and the gold set is what makes progress on it measurable.

Optional, and deliberately behind `P-notes` — neither of these blocks a note.

**`P-stt` — the Scribe backfill.** ElevenLabs Scribe v2 + keyterm prompting over
the 541-item / ~682 h cohort that has no manual subs, ≈ $0.22/h + $0.05/h
keyterms ≈ **$130–185**, which widens retrieval from the 1,000 manual items to
all 1,541. Chosen after a 6-item evaluation spanning 1949–1984 (see `compare/`):
strong-normalized WER 3.3–7.9% against manual subs on hard material, and a true
content-error rate of 0.8–2.1% even on the 1949 tape and a Q&A with audience
cross-talk — against whisper large-v3's 9.0% on the *easiest* item, and
grok-stt's ~2× Scribe's content errors ("Jayakrishna Murty"). Keyterms are a
top-1000 lexicon mined from the manual-sub corpus (`compare/build_keyterms.py`),
sent as one multipart field per term; worth ~4–8% relative WER and a nudge
toward KFT/British house style. Settings: `diarize=true`,
`timestamps_granularity=word`, keyterms. Ops: ≤3–4 concurrent files (one long
request can consume four concurrency slots), materialize iCloud-evicted audio
first. Buy it when `P-notes` starts running out of gold-transcript material for
a root, not before; `Q-diarization`, `Q-speaker-mapping` and `Q-scribe-needed`
gate the spend.

The interim local pass over that same cohort is **complete** — whisper.cpp
large-v3-turbo, `-mc 0`, no prompt. Those settings are pilot-frozen and the
evidence for each of them is in the `scripts/transcribe_whisper.py` docstring;
do not "improve" them without reading it. Better STT supersedes weaker
transcripts by `item_subtitles.kind`, never by overwriting.

**`P-tagging` — exhaustive tagging.** Classify all ~72k K-passages against the
36 roots, in two stages: (1) local and free — lexicon term-matching plus local
embeddings for clustering and per-concept candidate retrieval; (2) LLM judgment
via the Claude Batches API (50% discount, prompt-cached registry) — does a
passage substantively address a concept, merely mention it, or define it?
≈ $10–45 one-off depending on model tier. It buys cross-root queries, per-root
coverage numbers, and time-sliced views ("what did K say about X in 1972") —
none of which `P-notes` needs. `Q-pilot-rescore` and `Q-tagging-bar` gate it.

### The `P-notes` loop

One root per session. Nothing below needs a model, a spend approval, or an
answered open question; it needs reading time.

```bash
.venv/bin/python scripts/retrieve_concept.py <slug> --format md   # ranked candidates
#   read them; keep the passages that carry the argument, not the ones that
#   merely use the word. Note (item_code, int(t_start)) for each keeper.
#   → append one line per keeper to concepts/citations.jsonl:
#     {"slug":…,"theme":…,"seq":…,"item_code":…,"t_start":…}
.venv/bin/python scripts/build_citations.py --sync --slug <slug>  # resolve quotes + links
.venv/bin/python scripts/build_concept_vault.py                   # regenerate the note
.venv/bin/python scripts/build_concept_vault.py --check           # staleness + dead links
.venv/bin/python scripts/strategy_stats.py                        # refresh the live numbers
.venv/bin/python -m unittest discover tests                       # citation invariants
git commit                                                         # one root, one commit
```

**Shape of a finished note**, taking `fear` as the reference rather than a rule:
20–30 passages, five to eight themes, a span wide enough to show the teaching is
not of one period, and themes ordered so the sequence *is* the argument — what
it is, how it works, what it does, and what ends it. Prefer the passage where K
develops the point over the one that states it.

**Order.** Retrieval serves every root from the manual transcripts alone, and
the three roots shipped so far were nowhere near exhausting their material. So
the order is about learning the process, not about supply. (The old
"10,588 (`truth`) down to 228 (`religious-mind`)" spread is **not reproducible**
with the current code and has been removed rather than restated — see the
2026-07-26 log entry on stopword dilution, and `P-retrieval` below.)

1. ~~`attachment` — nearest neighbour to `fear`; the retrieval sets overlap, so
   it tests whether curation stays distinct when the material does not.~~
   ✅ 2026-07-26, and it does: see the log.
2. ~~`observer-observed` — the least literal vocabulary of the 36. If BM25 over
   name + aliases fails anywhere, it fails here, and that is worth knowing early,
   while it is cheap to fix.~~ ✅ 2026-07-26; it half-failed, and the fix was two
   aliases: see the log.
3. **`thought`** — the largest set that is genuinely one root. Tests whether
   reading candidates scales, or whether ranking needs work first.

Then by facet, so the vault becomes coherent in blocks rather than scattered.
Facet II is already anchored by `fear` and `attachment`; finish it, then III, I,
IV.

**Re-check after any ingest.** `build_citations.py --verify` is the gate that a
published quote still says what it said; `build_concept_vault.py --check` is the
gate that the vault matches the data; `strategy_stats.py --check` is the gate
that this file's numbers match the databases. All three are cheap; run them
before committing anything else.

**Stop conditions worth honouring.** If three consecutive roots come out thin
(under ~15 passages worth keeping), that is the evidence `Q-scribe-needed` asks
for, and the Scribe spend becomes the next move rather than a deferred one. If
curation starts feeling like it needs cross-root comparison to decide what
belongs where, that is `P-tagging` asking to be scheduled.

## Principles

1. **Transcribe everything, delete nothing.** Relevance is expressed as tiers,
   tags, and filtered views — never by excluding items from transcription.
   Changing our mind later costs a query, not a re-run.
2. **The "teachings corpus" is a filtered view: K-only text.** Audience
   questions, interviewers, and announcers are stored and speaker-tagged, not
   removed.
3. **Questions are context metadata.** A question ("What is meditation?") is
   often the cleanest topic label for the answer that follows.
4. **Manual KFT subtitles are the gold standard.** The pipeline is built and
   validated on them first; better STT supersedes weaker transcripts later by
   `item_subtitles.kind`, never by overwriting.
5. **Every claim carries a citation.** A synthesis sentence with no passage and
   no timestamp behind it does not ship.
6. **A rule that isn't a gate is a wish.** Every invariant this project leans on
   has a command that fails: `--check` for vault staleness and dead wikilinks,
   `--verify` for citations that no longer resolve, `--check` for the live
   numbers below, `unittest` for the parser and for layers that are meant to
   stay archived. The two worst incidents here — 82 transcripts carrying another
   recording's words, and a concepts table silently drifted from its registry —
   both persisted precisely because nothing was checking.

## Layer architecture

| Layer | Content | Where it lives | State |
|---|---|---|---|
| L0 Archive | media (m4a/mp4), manual VTTs, catalog | `catalog/krishnamurti.db` (tracked) + `library/` (iCloud, gitignored) | done |
| L1 Transcripts | one row per ingested transcript file + provenance | `corpus/krishnamurti-corpus.db` (snapshot tracked, live DB gitignored) | done |
| L2 Segments | speaker-attributed turns → passages, FTS5 over K-only text | same corpus DB | done for manual sources |
| L3 Concepts | 36 roots + aliases/relations + passage tagging | `concepts/concepts.jsonl` (tracked) → corpus DB | registry closed; retrieval works, exhaustive tagging optional |
| L4 Synthesis | Obsidian notes, timestamped `youtu.be/ID?t=SECONDS` citations | `obsidian/` + `concepts/citations.jsonl` (tracked) | in progress, root by root |

The **two-database split** is deliberate: the catalog is small and is canonical
pipeline state; the corpus is large and generated. A catalog rebuild never
touches corpus tables — corpus rows are keyed by stable item code, so they
survive. The corpus DB ships as a compressed snapshot rather than live, for the
two reasons logged when it was tracked: it is the only surviving copy of the
gold text for 111 items, and a private remote is what makes shipping verbatim
transcript text acceptable at all.

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

### Relevance tiers

Tiers are tags, never deletions: **A** core teachings, **B** secondary
(conversations, interviews, group and young-people discussions), **C** films and
documentaries, **X** the 12 `EBM` compiled excerpts. A/B/C are fully ingested;
`passages_fts` holds K-passages from A/B only; X is excluded because its text
duplicates full-length talks already in the corpus. Assignment is centralized in
`segment_schema.corpus_tier_for_event_type()`, and unknown event types default to
B with a warning — the per-event-type mapping itself is operational and lives in
`CLAUDE.md`. C's exclusion is provisional: `Q-tier-c`.

Announcer intros, housekeeping, `[applause]` and anonymous Q turns never enter
the K-only view at any tier; Q turns are kept as context metadata (principle 3).

### L3 — the 36 roots

The registry is **closed at 36 roots** in `concepts/concepts.jsonl`, grouped into
four *non-sequential facets* of 8 / 9 / 11 / 8. Facets are entry-points, not
stages and not a taxonomy with a quota — freedom is at the beginning of inquiry,
not a reward — so no root was placed to even out a count. The set was
triangulated from four independent sources: K's core vocabulary, corpus FTS
frequencies, the published book/chapter canon, and an 18-book content-group map
(`content_groups.md`, 54 groupings).

**Retrieval, not classification, is what a note needs.** Writing about one root
means finding the few dozen passages where K develops it — not knowing the
verdict for all ~72k. `retrieve_concept.py` runs BM25 over `passages_fts` using
the root's own `name` and `aliases`, returning ranked candidates a human reads;
what survives is filed in `concepts/citations.jsonl`. This is free, immediate,
and is how every note ships. Exhaustive tagging (`P-tagging`) remains worth
doing, but only for what retrieval *cannot* give.

### The I Ching navigation layer — archived

Added and then **archived on 2026-07-25**: parked pending a decision, not
rejected. Everything lives in `archive/iching/` (data, module, tests, the
generated notes, and the patch that removed the rendering code), with restore
instructions in `archive/iching/README.md`. It was navigation only, so nothing
else depends on it — `concepts.jsonl` was and stays canonical. See `Q-iching`.

## Where things stand

<!-- BEGIN GENERATED: where-things-stand -->

Live numbers, generated from the databases on **2026-07-26** by `scripts/strategy_stats.py`. Do not hand-edit — run the script.

**Archive (L0)** — 1,541 items / 1,963.0 h. Provenance: 1,484 Full-Length PDF + 11 Education Directory (10A) + 46 @KFoundation channel (11A). 2,121 media files downloaded.

**Transcript sources** — every item has a downloaded transcript of some kind.

| Kind | Status | Items |
|---|---|---|
| `manual` | downloaded | 1,000 |
| `whisper-large-v3-turbo` | downloaded | 540 |
| `kft-web-transcript` | downloaded | 1 |
| `elevenlabs-scribe-v2` | planned | 540 |

**Corpus (L1/L2)** — 988 transcripts ingested (tier A 809 / B 164 / C 15), 141,350 segments, 154,916 passages, of which 81,103 are K-passages and 80,809 are in `passages_fts` (tiers A/B only). Subtitle resolution: 988 `direct`.

**Tiers** — A 1,197 · B 311 · C 21 · X 12.

**Largest event types** — T Public Talk 637 / 783.9 h · D Public Discussion 172 / 232.0 h · DSS Discussion with Staff and Students 123 / 172.6 h · DSG Discussion with Small Group 103 / 143.3 h · DT Discussion with Teachers 72 / 107.5 h · S Seminar 69 / 113.7 h · Q Question & Answer Meeting 66 / 91.9 h · DYP Discussion with Young People 61 / 81.1 h · DS Discussion with Students 35 / 38.5 h · CB Conversation 31 / 44.5 h · CA Conversation 20 / 19.7 h · EBM Excerpt (compiled series) 12 / 5.8 h, plus a tail of 65 more types.

**Concepts (L3)** — 36 active roots + 3 deprecated tombstones (`sacred`, `self`, `word-naming`). Tombstones stay so predictions keyed to their ids remain resolvable; consumers filter by `status`.

**Vault (L4)** — 37 generated notes (36 concepts + Map). **3 roots of 36 cited**, 83 curated passages in all, each linking to the second it is spoken: `fear` (25 passages, 1961–1985, 8 themes) · `attachment` (28 passages, 1949–1985, 7 themes) · `observer-observed` (30 passages, 1949–1985, 8 themes).

<!-- END GENERATED: where-things-stand -->

Two facts no query knows:

**Backup** — one checksummed 80 MB `.tar.zst` in `~/Backups/jiddu-krishnamurti/`
(`scripts/backup_corpus.py`): corpus DB, every manual VTT, catalog DB, registry.
Off iCloud, not yet off the machine — and dated **2026-07-25**, so it predates
the 82 recovered transcripts entirely. The tracked snapshot predates them too.
`P-durability` closes both.

**Distribution** — the GitHub remote is **private**, which is what permits
verbatim quotation in the tracked vault. Publishing anything is a separate call.

## Open questions

Undecided calls, most actionable first. Questions only — reasoning belongs in the
log once a decision is made. When a question is answered, log it and delete it
here; the slug is what other sections reference, so never reuse one.

**Open** — most of these gate `P-stt` and `P-tagging`. Nothing here blocks
`P-notes`.

- **`Q-manual-trust` — how many "manual" transcripts are actually auto-captions?**
  `RO73DSG2`, `US84FCC` and `BR95FOF` carry ASR text on YouTube's *manual* track,
  and were caught only because they parse to 0 K-passages; one that happened to
  carry speaker labels would pass silently and be quoted as gold. A punctuation-
  and casing-density pass over all 988 transcripts answers the count in one run.
  The undecided part is what to do with what it finds — demote the tier, drop
  them from FTS, or queue them for the Scribe cohort — and whether principle 4's
  "manual subs are the gold standard" needs qualifying in the principle itself.
- **`Q-pilot-rescore` — tagging pilot re-score: arms, spend, and the new roots.**
  Re-score the 500-passage eval set against the final 36 roots with the full
  `substantive` / `mention_only` / `definition_like` labels. Needs a human call
  on which arms to run and approval of the spend; the arms exist to pick the
  model for the full pass on quality-per-dollar. It is also the first evidence on
  `listening`, `will-effort` and `responsibility` (none existed at r1) and the
  first measurement of confusion among self-knowledge/consciousness,
  awareness/observer-observed/listening, truth/what-is,
  conflict/violence/will-effort, and desire/pleasure.
- **`Q-tagging-bar` — faithfulness bar for a machine tagging pass.** STT has
  rigorous WER; a semantic pass has no gold set, no precision/recall, and no
  hallucination guard, and the 500-passage pilot is a labelling run, not a
  measured eval. Curation supplies the guard for `P-notes` — a human reads every
  passage before it is quoted — so this is owed only by `P-tagging`.
- **`Q-diarization` — diarization is unmeasured before the Scribe spend.** The
  WER eval was 5/6 clean Public Talks; the paid cohort is ~54% multi-speaker
  discussion. Run 3–5 representative items (DSG, DYP, a Bohm or Jayakar dialogue,
  DSS) and report WER **and** diarization accuracy separately before committing.
- **`Q-speaker-mapping` — "K = dominant speaker" is wrong-by-design for the ~115
  named-interlocutor dialogues.** Define the ambiguous → manual-review trigger
  (e.g. second-speaker share > 15%) and force registry mapping for those items
  before ingesting any Scribe output.
- **`Q-scribe-needed` — does `P-notes` need the Scribe cohort at all?** `fear`,
  `attachment` and `observer-observed` each reached 25+ citations across wide
  spans from manual transcripts alone, and exhausted none of them. Whether any
  root is *starved* is currently unanswerable: the candidate counts this entry
  used to rest on are not reproducible, and honest ones arrive with
  `P-retrieval`'s supply report. The trigger for the ~$130–185 is in any case
  not a count but a root whose *candidates don't hold up on reading*, which only
  curation can reveal; the stop condition is in the `P-notes` loop above.
  Supersedes "transcribe everything, then tag" as the reason to spend.
- **`Q-note-done` — definition of done for a concept note.** `fear` set a first
  shape — 25 passages, eight themes, argument order — and `attachment` a second,
  but neither set a bar. What makes a note finished rather than merely written?
- **`Q-rescan-cadence` — how often to re-scan the archive for new items.** The
  2026-06-12 channel scan added 46 recordings absent from every PDF, and that
  will recur. Unset: the cadence, and what runs after each re-ingest beyond the
  three gates in the `P-notes` loop.

**Parked** — real, but nothing waits on them.

- **`Q-keyterm-leakage` — the keyterm-gain evidence is thin.** Leave-one-out was
  controlled for only 1 of 6 eval items, so the flat "+4–8%" is weaker than it
  reads. Production leakage is zero, so this affects the claim, not the plan.
  Re-score with per-item leave-one-out if the number ever needs defending.
- **`Q-tier-c` — tier C confirmation.** Films and documentaries stay
  FTS-excluded pending provenance review; the ~30 short interviews sit in B by
  default. Resolve with the corpus stats (%-K-speech per event type) plus a call.
- **`Q-ebm-provenance` — `EBM` excerpt provenance.** No mapping exists from each
  of the 12 compiled excerpts to the source talk it was cut from. Build it only
  if passage-level dedup is ever needed; their 12 curated themes are retained as
  a KFT-authored thematic scaffold.
- **`Q-iching` — the I Ching navigation layer.** Archived undecided, not
  rejected — see `archive/iching/README.md`. Revisit once enough roots carry
  citations to know whether the notes need another way in.

## Decision log

Append-only, oldest first. **Entries are never rewritten** — a dangling slug or
a broken path in an old entry may be repaired, but never a claim, a number, or a
date.

Keep new entries to about three lines: the decision, the one fact that forced it,
and the commit. The full reasoning is already in the commit message and in the
code; entries written as essays are why this section reached 200 lines in one
month.

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
  since implemented — plus the governance gaps still carried in the open
  questions above.
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
  Because it predates every registry change since, its results **do not map onto
  the current 36**.
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
  every P1 item implemented, the rest folded into the open questions above), and
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
- **2026-07-25** — **rights & distribution: the repo is private.**
  `github.com/d333mianh/jiddukrishnamurti` was made private rather than the
  alternative of drawing a publishable/unpublishable line through the material.
  That unblocks L4: verbatim KFT-copyright quotation may be committed and
  rendered into the vault, because the vault is not published. It does not
  license publishing — anything leaving this repo is a separate decision, and
  the citation format (`youtu.be/<id>?t=<s>`, quote plus link to KFT's own
  upload) was chosen to keep that door open.
- **2026-07-25** — **backup implemented.** `scripts/backup_corpus.py` writes one
  checksummed `.tar.zst` holding the corpus DB (via the sqlite3 backup API, so
  the snapshot is consistent), every manual `.en.vtt`, the catalog DB, and
  `concepts.jsonl`; iCloud-evicted members are materialized first and a member
  that never appears fails the run while still writing the archive. First run:
  80 MB to `~/Backups/jiddu-krishnamurti/`. This closes the single-copy risk but
  **not** the offsite one — the default destination is off iCloud, not off the
  machine; copying an archive to external or remote storage is still manual.
  Urgency was not theoretical: 111 manual VTTs recorded as `downloaded` are gone
  from disk, and all 111 were ingested, so for those items the corpus DB is the
  only surviving copy of the gold text.
- **2026-07-25** — **82 transcripts were carrying another recording's words and
  have been purged.** `parse_vtt.py` had resolved a subtitle path by series
  rather than by item, so one part's VTT was ingested for every part of its
  series: the text was real KFT text, the timestamps were real, and the item
  code was wrong — the failure mode that produces a citation pointing at a
  minute where those words are never spoken. The resolver now requires the
  item's own file, accepting a sibling only when duration corroborates it, and
  records which happened in `transcripts.resolved_via` (`direct` 877 /
  `sibling-vtt` 29). The corpus count fell 988 → 906 and passages 153,360 →
  136,657. That is the number getting more honest, not smaller. The 82 items are
  re-ingestable once their own VTTs are on disk; they are not lost.
- **2026-07-25** — **citations are tracked data, not prose.**
  `concepts/citations.jsonl` holds one line per quotation, keyed on
  `(item_code, t_start)` and resolved by `scripts/build_citations.py`;
  `build_concept_vault.py` renders it into the note. Two forcing constraints:
  `obsidian/roots/**` is generated and must never be hand-edited, so a curated
  quote cannot live in the note; and `corpus/krishnamurti-corpus.db` is
  gitignored, so each line stores its own resolved text and link and a fresh
  clone rebuilds the vault without it. Keying on `passages.id` was rejected —
  ids are reassigned on every re-ingest, so an id-keyed citation drifts silently
  onto different words, while an item code plus an offset is exactly what the
  published link already claims. `--verify` is the gate that catches a re-ingest
  moving the ground under a published quote; run it after every ingest.
- **2026-07-25** — **`fear` shipped, and it restructured the plan.** 25 curated
  passages spanning 1961–1985 in eight themes, each linking to the second it is
  spoken, drawn from BM25 retrieval over the root's own name and aliases plus a
  human reading the candidates. It cost no model spend and needed neither the
  tagging pass nor the Scribe cohort. So the phases were reordered: cited notes
  became the critical path, exhaustive tagging and the STT backfill dropped
  behind them as optional enrichment. The old plan gated note #1 on judgment
  #2,900,000; retrieval-first gates it on an afternoon of reading, and each root
  ships independently.
- **2026-07-26** — **the corpus DB now ships in git, compressed.** A fresh clone
  was tested: 31 MB, 69/69 tests pass, all 37 notes regenerate with no dead
  links — but `retrieve_concept.py` and `build_citations.py` both die on a
  missing corpus, so the notes loop was dead on any machine holding only the
  repo. `corpus/krishnamurti-corpus.db.zst` (195 MB → 67 MB, taken through the
  sqlite3 backup API so the snapshot is consistent) is tracked by a `!` negation
  in `.gitignore`, with its checksum beside it and four cheap tests holding it
  in place. This breaks the rule that generated artifacts stay out of git, on
  two grounds: the DB is the only surviving copy of the gold text for the 111
  items whose VTTs are gone, and the private remote is what makes shipping
  verbatim transcript text acceptable at all. Cost accepted: each refreshed
  snapshot adds ~67 MB to history permanently, so it is refreshed on milestones,
  not per ingest. Git LFS was the alternative — leaner history, but it adds a
  tool dependency at every clone and the free tier throttles at ~15 pulls a
  month. Still not in the repo and not fixable: `library/` and the cookie files,
  so downloading, transcribing, and re-ingesting remain machine-bound. Curation
  does not need them.
- **2026-07-26** — **`attachment` shipped; the overlap worry was unfounded.** 28
  passages, 1949–1985 (the widest span of any note so far, and the first to
  reach back to 1949), in seven themes: why we are attached → what we are
  attached to → what attachment breeds → detachment is attachment → attachment
  is not love → there is no security in it → the ending. This root was picked
  first precisely because its retrieval set overlaps `fear`'s, to test whether
  two adjacent notes would converge on the same passages. They did not: of 53
  citations across both roots, exactly one passage came up in both drafts
  (BR80Q2 @2596, "fear begins with attachment"), and it was swapped out for
  BR78T1 @3469, which makes the same link in attachment's own vocabulary. The
  notes now share zero passages and 28 distinct recordings. The reason is that
  the roots argue different things from adjacent material — `fear` asks what
  ends fear, `attachment` asks why security is sought at all — so theme
  structure, not vocabulary, keeps curation distinct. Second data point for
  `Q-scribe-needed`: no sign of thin supply, and no Scribe cohort needed.
- **2026-07-26** — **STRATEGY.md restructured: live numbers generated, everything
  referenced by slug, log entries capped at ~3 lines.** Four cross-references had
  already rotted — two different questions had each been "open question 4" — and
  "Where things stand" was stamped one date while carrying the next day's facts.
  `scripts/strategy_stats.py --check` is now the gate on the numbers, and
  `tests/test_strategy_doc.py` the gate on the slugs.
- **2026-07-26** — **`observer-observed` shipped, and retrieval half-failed as
  predicted.** 30 passages, 1949–1985, eight themes: the division we are educated
  into → the observer is the past → division is conflict → the thinker is the
  thought → at the moment of experiencing there is no experiencer → analysis
  cannot reach it → the controller is the controlled → what ends, and what
  remains. BM25 over name + aliases served the thinker/experiencer/analyser
  strands abundantly, but K's control vocabulary — *the controller is the
  controlled*, *the seer is the seen* — is the same identity claim in different
  words, and the registry did not own it: only one such passage reached the top
  120, and the theme had to be found with hand-picked `--terms`.
- **2026-07-26** — **the 2026-07-25 backup entry's "all 111 were ingested" is
  wrong; only 29 were.** The other 82 never reached the corpus, so for those the
  corpus DB was never a second copy of anything — the gold text existed nowhere.
  The 29 are exactly the `sibling-vtt` rows, ingested from a *neighbour's* file
  that was still on disk, so the single-copy risk that entry described was
  narrower than stated. Entries are never rewritten; this corrects it.
- **2026-07-26** — **`Path.with_suffix` silently collapsed 111 manual VTTs onto
  one filename per series, and nothing was checking.** Item codes carry a part
  number after a dot, so pathlib read `.02 - You can live without an image` as
  the suffix and `subtitle_output_path` wrote every part of `BR72DSS1` to
  `BR72DSS1.en.vtt`. Part 1 landed; parts 2–10 hit the `dest.is_file()` early
  return and recorded `downloaded` with part 1's `file_size` against their own
  empty path. The defect was two implementations of "swap the extension" —
  `subtitle_future_path` did it by string and was right, so the catalog recorded
  a path the downloader never wrote to. They now share `subtitle_name`; the
  hypothesis predicts the data exactly (all 111 missing files have dotted stems,
  none otherwise). All 111 re-downloaded, 0 failed. Commit `e80c68f`.
- **2026-07-26** — **the 82 are recovered; the corpus grew 13%.** All 111 VTTs
  re-downloaded (0 failed) and the whole corpus re-ingested: 906 → **988
  transcripts**, K-passages 71,824 → **81,103**, FTS 71,530 → **80,809**.
  `sibling-vtt` is now **0** — every transcript resolves `direct` from the item's
  own file, so the corroborate-by-duration fallback is no longer load-bearing.
  All 83 citations still verify. Only one cited item was ever `sibling-vtt`
  (`BR80DSG2.0`), a single-item series whose file was merely misnamed and is
  byte-identical to its replacement.
- **2026-07-26** — **three "manual" transcripts are actually auto-captions.**
  `RO73DSG2` (tier B), `US84FCC` and `BR95FOF` (tier C) parse to 0 K-passages
  because they have no punctuation, capitalisation, or speaker labels — ASR text
  that YouTube served on the *manual* track, so `download_subtitles.py`'s
  manual-only filter admitted it. Pre-existing, not caused by the recovery, and
  caught only because the collapse guard flags 0-K items. Principle 4 calls
  manual subs the gold standard; for at least these three it is not true. How
  many more sit undetected because they *do* carry labels is unknown.
- **2026-07-26** — **BM25 queries include stopwords, and the documented candidate
  spread is not reproducible.** Query terms come from splitting `name` + aliases
  into words, keeping `the`, `and`, `what`, so `truth` searches on `what`/`the`
  and `observer-observed` on `the`/`and`. Under the current code every root
  returns ~26k candidates rather than the logged 10,588–228 spread, so "none is
  starved" rests on numbers nobody can now reproduce; the Plan's copy of them was
  removed rather than restated. `fear` was unaffected only because its aliases
  are single words. Now `P-retrieval`.
- **2026-07-26** — **`status='downloaded'` is now gated against the filesystem.**
  `tests/test_subtitle_paths.py` fails if any manual subtitle marked downloaded
  is absent from disk, and asserts that dotted codes yield distinct filenames and
  that the download destination equals the catalog path. The false rows sat for
  seven weeks because principle 6 had no gate here. `download_subtitles.py`
  gained `--missing-files` and `--codes`, since `--section`/`--from-code` gave no
  way to re-run just the broken rows.
- **2026-07-26** — **two aliases added to `observer-observed`; the registry is
  closed at 36 roots, not frozen in vocabulary.** `the controller is the
  controlled` and `the seer is the seen` now sit beside the three existing
  identity forms, so eight controller/seer passages rank in the top 60 where one
  ranked 51st before. This is the failure the root was scheduled second to
  expose, and the fix was two lines of JSONL plus `import_concepts.py`. The
  lesson generalizes: a root whose aliases are all one grammatical form will
  under-retrieve K's other formulations of it, and that is invisible until a
  human reads the candidates.
- **2026-08-03** — **`P-retrieval` reordered on measurement: the stopword fix is
  nearly a no-op and phrase queries are a regression.** Stripping stopwords cuts
  candidate pools by an order of magnitude on 21 of 36 roots but moves the top 60
  by a mean of 4.5 passages, because BM25's IDF already discounted `the`; making
  multi-word aliases into FTS5 phrases drops 15 of `observer-observed`'s 30
  curated passages and inflates `truth`'s pool to 10,323 on `"what is"` alone. So
  the phase now leads with a recall gate over the 83 curated citations — the only
  ground truth about what retrieval should return, and until now unmeasured. The
  measurement itself is not in the repo: until step 1 lands it, these figures
  carry the same weakness as the ones they replace.
- **2026-08-03** — **`P-durability` added ahead of everything.** The 82
  transcripts recovered on 2026-07-26 have no copy in git, in the backup archive
  (dated the day before), or off this machine; the tracked snapshot is still the
  906-transcript one. The project has already lost 111 files for seven weeks to a
  gap nothing was checking, so this is not a hypothetical class of risk.
