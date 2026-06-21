# Teachings Corpus — Strategy

Goal: build the most complete structure of the meaning, ideas, and fundamentals of
J. Krishnamurti's teachings on top of the complete KFT recordings archive
(1,541 items, ~1,960 h) — every concept traceable to his own words, cited back to
the recording with a timestamp.

## Principles

1. **Transcribe everything, delete nothing.** Relevance is expressed as tags and
   filtered views, never by excluding items from transcription. Changing our mind
   later costs a query, not a re-run.
2. **The "teachings corpus" is a filtered view: K-only text.** Audience questions,
   interviewers, and announcers are stored and speaker-tagged, not removed.
3. **Questions are context metadata.** A question ("What is meditation?") is often
   the cleanest topic label for the answer that follows; each Q segment links
   forward to its answer span.
4. **Manual KFT subtitles are the gold standard** (1,000 items, ~1,280 h). The whole
   pipeline is built and validated on them first; STT fills the remaining 541
   items last, through an already-proven pipeline.

## Layer architecture

| Layer | Content | Source |
|---|---|---|
| L0 Archive | media (m4a/mp4), manual VTTs, catalog DB | done |
| L1 Transcripts | unified schema over manual subs (cue timestamps, speaker labels) and Scribe v2 JSON (word timestamps, diarization) | Phase 1 / 4 |
| L2 Segments | speaker-attributed turns + sub-chunked passages, FTS5 over K-only text | Phase 1 |
| L3 Concepts | concept registry + passage-level tagging + relations | Phase 2 |
| L4 Synthesis | Obsidian: one note per concept, K's formulations across decades, timestamped YouTube citations (`youtu.be/ID?t=SECONDS`) | Phase 3 |

### L2 — Segments

- **Speaker tags:** `K`, `Q` (anonymous audience), named interlocutors (per-item
  registry mapping VTT initials — `DB:` David Bohm, `WR:` Walpola Rahula, … —
  to people), `ANN` (announcer/housekeeping), `UNK`.
- **Granularity (decided 2026-06-11):** speaker turn is the atomic unit; K's long
  monologue turns are sub-chunked into ~150–200-word passages at sentence
  boundaries, each with its own t_start/t_end. ~60–90 s of speech ≈ one developed
  thought — right size for citation, embeddings, and timestamped links. Passages
  merge upward for display; never the reverse.
- **Sources:** for subtitled items, parse VTT speaker labels against a per-item
  known-label registry only (generic `Word:` patterns produce false positives like
  "We are asking:"); unlabeled cues inherit the previous speaker. For STT items,
  Scribe's per-word `speaker_id` with "K = dominant speaker" heuristic; ambiguous
  items flagged for manual review.
- Q segments link to the K answer span they introduce.

### L3 — Concepts

- **Registry seeding is hybrid:** top-down from K's known core vocabulary
  (thought, psychological time, fear, conditioning, observer/observed,
  image-making, attention vs concentration, intelligence vs intellect, insight,
  meditation, death, love, authority, the religious mind, …) plus KFT's own
  thematic groupings (the Education Directory 2026 maps themes → recordings);
  bottom-up from corpus mining (compare/build_keyterms.py already extracts
  candidate vocabulary). Concepts carry aliases and period notes — K's
  terminology shifts across decades.
- **Tagging is two-stage (decided 2026-06-11):**
  1. *Local, free:* lexicon term-matching + local embeddings for clustering and
     per-concept candidate retrieval.
  2. *LLM judgment via the Claude Batches API* (50% discount, prompt-cached
     concept registry): does a passage substantively address a concept vs merely
     mention it; is it definition-like. ~75k passages / ~10M input tokens ≈ $45
     one-off on Opus 4.8 (≈ $26 Sonnet 4.6, ≈ $9 Haiku 4.5). Run a ~500-passage
     pilot on Opus 4.8 vs Sonnet 4.6 first and let the pilot pick the model.

## Relevance tiers (tags, not deletions)

| Tier | Event types | Treatment |
|---|---|---|
| A (core) | Public Talks (T, 772 h), Q&A answers (Q, 91 h), Talks to Students | teachings corpus |
| A-dialogue | Conversations with named interlocutors (Bohm, Anderson, Jayakar, Rahula, …) | teachings corpus; interlocutor turns tagged, kept |
| B | Public Discussions (229 h), Small Group / Staff+Students / Teachers discussions, Seminars | teachings corpus via speaker filter |
| C (archive only — pending confirmation) | Discussions with Young People / Students (~147 h), Films/documentaries, Historical films, EBM compiled excerpts | excluded from corpus, kept in archive |
| strip always | announcer intros, housekeeping, [applause]-type events, anonymous Q turns (kept as context metadata) | never in K-only view |

Open: confirm Tier C (esp. young-people discussions); decide whether interviews
(~30 mostly short items) sit in B or C.

## STT (for the 541 no-subs items, ~680 h)

**Interim local pass (running since 2026-06-11):** budget doesn't currently
allow the Scribe backfill, so all 541 items are being transcribed locally
first with whisper.cpp **large-v3-turbo, `-mc 0`, no prompt**
(`scripts/transcribe_whisper.py`, resumable, talks first; outputs
`<stem>.whisper.{vtt,json,txt}` next to media; DB rows
`item_subtitles.kind='whisper-large-v3-turbo'`). Pilot data behind those
settings: turbo beat large-v3 on both test clips (5.05%/6.69% vs
5.50%/9.43% strong WER — large-v3 hallucinates on hard material) and runs
~8× realtime on the M1 (~3 days vs ~10); without `-mc 0` the context
feedback loop produced a 6× repeated sentence (16.1% WER); whisper's
initial prompt is silently ignored under `-mc 0` and degrades quality with
`-mc 224`, so keyterm prompting is whisper-inapplicable. These transcripts
are good enough to start L2/L3 on; Scribe supersedes them later by kind.

**Final quality pass (when budget allows):** decided 2026-06-11 after a
6-item evaluation across 1949–1984 (see project memory and compare/):
**ElevenLabs Scribe v2 + keyterm prompting**.

- Strong-normalized WER vs manual subs: 3.3–7.9% across hard cases; true
  content-error (substitution) rate 0.8–2.1% even on the 1949 tape and a Q&A with
  audience cross-talk. whisper large-v3: 9.0% on the easiest item. Grok-stt:
  ~2× Scribe's content errors ("Jayakrishna Murty").
- Keyterms: top-1000 lexicon mined from the manual-sub corpus
  (compare/build_keyterms.py); sent as one multipart field per term; also nudges
  output toward KFT/British house style. ~4–8% relative WER gain.
- Settings already match L1/L2 needs: `diarize=true`,
  `timestamps_granularity=word`, keyterms.
- Cost ≈ 400k credits ≈ $130–140 pay-as-you-go. Ops: ≤3–4 concurrent files
  (12-concurrent-request cap), materialize iCloud-evicted audio first
  (`brctl download`).

## Phases

1. **Segments** — schema + VTT parser; populate L2 for all 1,000 subtitled items;
   FTS5; stats report (actual % K-speech per event type — settles tier questions
   with data). No transcription, no API cost.
2. **Concepts** — registry seed; tagging pilot (~500 passages, Opus 4.8 vs
   Sonnet 4.6); review together before scaling.
3. **Synthesis prototype** — 2–3 concept notes end-to-end in Obsidian with
   timestamped YouTube links.
4. **STT backfill** — Scribe v2 + keyterms on the 519 items, feeding the proven
   pipeline; corpus coverage 65% → 100%. Then the full L3 tagging pass.

## Decision log

- 2026-06-11 — transcribe everything; relevance as tags/views; Q&A filtered at
  speaker-turn level, not item level; questions kept as context metadata.
- 2026-06-11 — STT provider: Scribe v2 + keyterms (over grok-stt and local
  whisper), based on 6-item WER eval.
- 2026-06-11 — citation granularity: speaker turn + ~150–200-word sub-chunks of
  K monologues.
- 2026-06-11 — concept tagging: local embeddings/lexicon prefilter + Claude
  Batches API judgment pass; model picked by pilot (Opus 4.8 vs Sonnet 4.6).
- 2026-06-11 — pipeline order: build/validate everything on the 975 subtitled
  items before spending on STT.
- 2026-06-11 — interim local transcription launched: whisper.cpp
  large-v3-turbo + `-mc 0`, no prompt (pilot: turbo > large-v3 on this
  corpus; `-mc 0` prevents repetition loops; whisper prompts don't work as
  keyterms). Scribe v2 remains the final-quality pass when budget allows,
  superseding by `item_subtitles.kind`.
- 2026-06-20 — counts refreshed from the DB. Totals above were written
  2026-06-11 (1,495 items); the 2026-06-12 @KFoundation channel scan added 46
  recordings absent from all PDFs (section 11A), so the archive is now **1,541
  items / ~1,960 h**, split **1,000 subtitled (~1,280 h) / 541 no-subs (~680 h)**.
  Provenance: 1,484 Full-Length PDF + 11 Education Directory (10A) + 46 channel
  (11A). Whisper backfill 111/541 done.
- 2026-06-21 — excerpts (section 8A, the 12 `US97EBM1-12` "Beyond Myth &
  Tradition" items) deferred, not deleted. They are KFA-made posthumous
  compilations of "relevant excerpts from K's Talks and Discussions filmed at
  different times" (per item summary), so their text duplicates full-length
  recordings already in the archive. Decision: keep the media + gold manual
  subs as a browsable topical-intro layer, but **exclude them from the
  searchable corpus** to avoid duplicate passages / ambiguous citations. Their
  12 curated themes (Conflict, Change, Freedom & authority, The sacred,
  Choiceless awareness, Meditation, Mirror of relationship, Conditioning, The
  violent self, Death, Love, The religious mind) are retained as a KFT-authored
  thematic scaffold for a future learning-pattern / topic-structure phase.
  Note: no per-excerpt provenance mapping exists yet (which source talk each is
  cut from is unrecorded); build that if/when passage-level dedup is needed.
