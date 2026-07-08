---
tags: [krishnamurti, root, reference]
---
# Strategy

Executive summary of the project roadmap. **Canonical, full version:**
`STRATEGY.md` at the repo root (with the dated decision log — the source of truth
for *why* each choice was made). This note is a map, not a replacement.

## Goal

Build the most complete structure of the meaning and fundamentals of
Krishnamurti's teachings on top of the complete KFT archive (**1,541 items,
~1,960 h**) — every concept traceable to his own words, cited back to the
recording with a timestamp.

## Layers

| Layer | Content | State |
|---|---|---|
| **L0** Archive | media, manual VTTs, catalog DB | done |
| **L1** Transcripts | unified schema over manual subs + STT | in progress |
| **L2** Segments | speaker-attributed turns + ~150-word K passages, FTS5 | done (80,030 K passages) |
| **L3** Concepts | the [[Map of the 36 Roots\|36 roots]] + passage tagging + relations | **here now** |
| **L4** Synthesis | one Obsidian note per concept, K's words across decades, `youtu.be/ID?t=SECONDS` citations | next |

## Guiding principles

1. **Transcribe everything, delete nothing.** Relevance is tags and filtered
   views, never exclusion. Changing our mind costs a query, not a re-run.
2. The teachings corpus is a **filtered K-only view**; audience/interviewer/
   announcer turns are kept and speaker-tagged, not removed.
3. **Manual KFT subtitles are the gold standard** (1,000 items); the pipeline is
   built and validated on them first, STT fills the rest last.

## Phases

1. **Segments** — schema + parser + FTS. *Done.*
2. **Concepts** — registry seed + tagging pilot. *In progress — see [[Open Decisions]].*
3. **Synthesis prototype** — 2–3 concept notes end-to-end with timestamped links.
4. **STT backfill** — ElevenLabs Scribe v2 + keyterms on the no-subs items
   (~$130, budget-gated), then the full L3 tagging pass.

---
*Hand-authored summary. Read `STRATEGY.md` for the authoritative, dated log.*
