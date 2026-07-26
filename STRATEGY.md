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
| L3 Concepts | 36 roots + aliases/relations + passage tagging | `concepts/concepts.jsonl` (tracked) → corpus DB | registry closed; retrieval works, exhaustive tagging optional |
| L4 Synthesis | Obsidian notes, timestamped `youtu.be/ID?t=SECONDS` citations | `obsidian/` + `concepts/citations.jsonl` (tracked) | 2 roots of 36 cited |

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

**Retrieval, not classification, is what a note needs.** Writing about one root
means finding the few dozen passages where K develops it — not knowing the
verdict for all ~72k. `retrieve_concept.py` runs BM25 over `passages_fts` using
the root's own `name` and `aliases`, returning ranked candidates a human reads;
what survives is filed in `concepts/citations.jsonl`. This is free, immediate,
and is how every note ships.

Exhaustive tagging remains worth doing, but for what retrieval *cannot* give:
cross-root queries, per-root coverage numbers, and time-sliced views. It stays
two-stage —

1. *Local, free:* lexicon term-matching + local embeddings for clustering and
   per-concept candidate retrieval.
2. *LLM judgment via the Claude Batches API* (50% discount, prompt-cached
   registry): does a passage substantively address a concept, merely mention it,
   or define it? ~72k K-passages ≈ $10–45 one-off depending on the model tier.

— and it is now phase 5, behind the notes, not in front of them.

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

**Corpus (L1/L2)** — 906 transcripts ingested (tier A 734 / B 157 / C 15),
123,874 segments, 136,657 passages, of which 71,824 are K-passages and 71,530
are in `passages_fts` (tiers A/B only). Provenance: 877 matched to their own
file (`direct`), 29 to a duration-corroborated sibling.

The count fell from 988 on 2026-07-25: 82 of those transcripts were one part's
VTT handed to every other part of its series, so they carried the wrong words at
the wrong offsets. They are gone, not lost — see the decision log.

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
Two notes now carry citations, 53 curated passages in all, each linking to the
second it is spoken: `fear` (25 passages, 1961–1985, eight themes) and
`attachment` (28 passages, 1949–1985, seven themes). 2 roots of 36 cited.

**Backup** — one checksummed 80 MB `.tar.zst` in `~/Backups/jiddu-krishnamurti/`
(`scripts/backup_corpus.py`): corpus DB, every manual VTT, catalog DB, registry.
Off iCloud, not yet off the machine.

**Distribution** — the GitHub remote is **private**, which is what permits
verbatim quotation in the tracked vault. Publishing anything is a separate call.

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

Restructured 2026-07-25, after `fear` shipped. The old plan made every note wait
on an exhaustive tagging pass — up to 2.9M judgments, with note #1 gated on
judgment #2,900,000. Retrieval-first inverts that: BM25 over the registry's own
lexicon surfaces a few hundred candidates for one root, a human keeps ~25, and
the note ships. Tagging became optional enrichment, so phase 3 no longer waits
on phase 4, and neither waits on the STT spend.

1. **Segments** — schema + VTT parser, L2 for all manual items, FTS5, stats.
   ✅ done.
2. **Concepts** — registry seeded and closed at 36 roots. ✅ done.
3. **Cited notes** — the critical path, and the only phase that produces the
   thing this project is for. Per root: `retrieve_concept.py` → read the
   candidates → file the keepers in `concepts/citations.jsonl` → `--sync` →
   regenerate. `fear` ✅ (25 passages), `attachment` ✅ (28); **34 roots to go**.
   Each is a bounded
   session of reading, needs no model spend, and ships independently.

Optional, and deliberately after phase 3 — none of it blocks a note:

4. **STT backfill** — Scribe v2 + keyterms on the 541-item cohort (~$130–185),
   which widens retrieval from the 1,000 manual items to all 1,541. Buy it when
   phase 3 starts running out of gold-transcript material for a root, not
   before. Open questions 3–5 gate the spend.
5. **Exhaustive tagging** — classify all ~72k K-passages against the 36 roots.
   Buys cross-root queries, per-root coverage numbers, and "what did K say about
   X in 1972" — none of which phase 3 needs. Open questions 1–2 gate it.

### Next steps — the phase 3 loop

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
.venv/bin/python -m unittest discover tests                       # citation invariants
git commit                                                         # one root, one commit
```

**Shape of a finished note**, taking `fear` as the reference rather than a rule:
20–30 passages, five to eight themes, a span wide enough to show the teaching is
not of one period (`fear` runs 1961–1985), and themes ordered so the sequence
*is* the argument — what it is, how it works, what it does, and what ends it.
Prefer the passage where K develops the point over the one that states it.

**Order.** Retrieval serves every root from the manual transcripts alone —
candidate counts run from 10,588 (`truth`) down to 228 (`religious-mind`), and
none is starved. So the order is about learning the process, not about supply:

1. ~~**`attachment`** (2,230) — nearest neighbour to `fear`; the retrieval set
   overlaps, so it tests whether curation stays distinct when the material does
   not.~~ ✅ 2026-07-26, and it does: see the log.
2. **`observer-observed`** (1,083) — the least literal vocabulary of the 36.
   If BM25 over name + aliases fails anywhere, it fails here, and that is worth
   knowing early, while it is cheap to fix.
3. **`thought`** (6,400) — the largest set that is genuinely one root. Tests
   whether reading candidates scales, or whether ranking needs work first.

Then by facet, so the vault becomes coherent in blocks rather than scattered.
Facet II is already anchored by `fear` and `attachment`; finish it, then III,
I, IV.

**Re-check after any ingest.** `build_citations.py --verify` is the gate that a
published quote still says what it said; `--check` is the gate that the vault
matches the data. Both are cheap; run them before committing anything else.

**Stop conditions worth honouring.** If three consecutive roots come out thin
(under ~15 passages worth keeping), that is the evidence open question 5 asks
for, and the Scribe spend becomes the next move rather than a deferred one. If
curation starts feeling like it needs cross-root comparison to decide what
belongs where, that is phase 5 asking to be scheduled.

## Open questions

Undecided calls, most actionable first. Questions only — reasoning belongs in
the log once a decision is made. When a question is answered, log it and delete
it here.

**Open** — these gate phases 4 and 5. Nothing here blocks phase 3.

1. **Tagging pilot re-score — arms, spend, and the new roots.** Re-score the
   500-passage eval set against the final 36 roots with the full
   `substantive` / `mention_only` / `definition_like` labels. Needs a human call
   on which arms to run and approval of the spend; the arms exist to pick the
   model for the full pass on quality-per-dollar. It is also the first evidence
   on `listening`, `will-effort`, and `responsibility` (none existed at r1) and
   the first measurement of confusion among self-knowledge/consciousness,
   awareness/observer-observed/listening, truth/what-is,
   conflict/violence/will-effort, and desire/pleasure.
2. **Faithfulness bar for a machine tagging pass.** STT has rigorous WER; a
   semantic pass has no gold set, no precision/recall, and no hallucination
   guard, and the 500-passage pilot is a labelling run, not a measured eval.
   Curation supplies the guard for phase 3 — a human reads every passage before
   it is quoted — so this is only owed by phase 5.
3. **Diarization is unmeasured before the Scribe spend.** The WER eval was 5/6
   clean Public Talks; the paid cohort is ~54% multi-speaker discussion. Run
   3–5 representative items (DSG, DYP, a Bohm or Jayakar dialogue, DSS) and
   report WER **and** diarization accuracy separately before committing.
4. **"K = dominant speaker" is wrong-by-design for the ~115 named-interlocutor
   dialogues.** Define the ambiguous → manual-review trigger (e.g. second-speaker
   share > 15%) and force registry mapping for those items before ingesting any
   Scribe output.
5. **Does phase 3 need the Scribe cohort at all?** `fear` reached 25 citations
   across 1961–1985 from manual transcripts alone, and did not exhaust them.
   Every one of the 36 roots has FTS candidates in the gold corpus — 10,588
   (`truth`) down to 228 (`religious-mind`) — so none is starved on paper. The
   honest trigger for the ~$130–185 is a root whose *candidates don't hold up on
   reading*, which only curation can reveal; the stop condition is in the phase 3
   loop above. Supersedes "transcribe everything, then tag" as the reason to
   spend.
6. **Definition of done for a concept note, and re-ingest cadence.** `fear` set
   a first shape — 25 passages, eight themes, argument order — but not a bar.
   Also unset: how often to re-scan for new items (the 2026-06-12 channel scan
   added 46 absent from every PDF, and that will recur) and, after each
   re-ingest, when `build_citations.py --verify` runs.

**Parked** — real, but nothing waits on them.

7. **Keyterm-leakage evidence is thin.** Leave-one-out was controlled for only
   1 of 6 eval items, so the flat "+4–8%" is weaker than it reads. Production
   leakage is zero, so this affects the claim, not the plan. Re-score with
   per-item leave-one-out if the number ever needs to be defended.
8. **Tier C confirmation.** Films and documentaries stay FTS-excluded pending
   provenance review; the ~30 short interviews sit in B by default. Resolve
   with the corpus stats (%-K-speech per event type) plus a call.
9. **`EBM` excerpt provenance.** No mapping exists from each of the 12 compiled
   excerpts to the source talk it was cut from. Build it only if passage-level
   dedup is ever needed; their 12 curated themes are retained as a KFT-authored
   thematic scaffold.
10. **The I Ching navigation layer.** Archived undecided, not rejected — see
    `archive/iching/README.md`. Revisit once enough roots carry citations to
    know whether the notes need another way in.

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
- **2026-07-25** — **rights & distribution: the repo is private** (old open
  question 4). `github.com/d333mianh/jiddukrishnamurti` was made private rather
  than the alternative of drawing a publishable/unpublishable line through the
  material. That unblocks L4: verbatim KFT-copyright quotation may be committed
  and rendered into the vault, because the vault is not published. It does not
  license publishing — anything leaving this repo is a separate decision, and
  the citation format (`youtu.be/<id>?t=<s>`, quote plus link to KFT's own
  upload) was chosen to keep that door open.
- **2026-07-25** — **backup implemented** (old open question 5).
  `scripts/backup_corpus.py` writes one checksummed `.tar.zst` holding the
  corpus DB (via the sqlite3 backup API, so the snapshot is consistent), every
  manual `.en.vtt`, the catalog DB, and `concepts.jsonl`; iCloud-evicted members
  are materialized first and a member that never appears fails the run while
  still writing the archive. First run: 80 MB to `~/Backups/jiddu-krishnamurti/`.
  This closes the single-copy risk but **not** the offsite one — the default
  destination is off iCloud, not off the machine; copying an archive to external
  or remote storage is still manual. Urgency was not theoretical: 111 manual
  VTTs recorded as `downloaded` are gone from disk, and all 111 were ingested,
  so for those items the corpus DB is the only surviving copy of the gold text.
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
  are now phase 3 and the critical path, exhaustive tagging and the STT backfill
  drop behind them as optional enrichment. The old plan gated note #1 on
  judgment #2,900,000; retrieval-first gates it on an afternoon of reading, and
  each root ships independently. 1 root of 36 cited.
- **2026-07-26** — **the corpus DB now ships in git, compressed.** A fresh clone
  was tested: 31 MB, 69/69 tests pass, all 37 notes regenerate with no dead
  links — but `retrieve_concept.py` and `build_citations.py` both die on a
  missing corpus, so the phase 3 loop was dead on any machine holding only the
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
  structure, not vocabulary, keeps curation distinct. Second data point for open
  question 5: no sign of thin supply, and no Scribe cohort needed. 2 roots of
  36 cited.
