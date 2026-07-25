---
tags: [krishnamurti, root, decisions]
---
# Open Decisions

The concept-layer calls that are still undecided, most actionable first. This is
a queue of *questions*, not a rationale store — costs, options, and the reasoning
behind a call live in the `STRATEGY.md` decision log. When a question is
answered, log it there and delete it here.

> [!info] Where we are right now
> - The **36 roots are imported** into the corpus DB (33 active + 3 pilot),
>   plus the deprecated `sacred` tombstone.
> - The pilot runner is **upgraded and committed** (`8c33e6e`): full
>   relevance/definition labels, a `--model` flag, all-36 default.
> - One **Sonnet 5 batch has already completed** — `pilot-2026-07-r1`,
>   500/500 succeeded, 2026-07-07. It predates the religious-mind/sacred merge
>   and the `responsibility` root, so its results don't cover the current
>   registry; a re-score against the current 36 is still needed.

---

## Pilot re-score — model arm + spend

> [!warning] Decision
> Re-score the 500-passage eval set against the current 36 roots with the full
> label set. **Which model arm(s), and approve the spend?**

Resolved by: your call. This is the gate everything below waits on.

---

## Merge pair — `self` ↔ `self-knowledge`

> [!question] Decision
> Are [[self|The Self]] and [[self-knowledge|Self-knowledge]] reliably
> separable per passage, or should they merge into one root?

Kept **separate on probation.** Merge only if the re-score's confusion metrics
show the judge can't tell them apart per passage.
Resolved by: the re-score above.

---

## Provisional root — `word-naming`

> [!question] Decision
> Does [[word-naming|The Word & Naming]] tag as an independent field, or fold
> into [[thought|Thought & Knowledge]]?

Kept as a **provisional root** (`status: active`). Independently supported by
the book canon — "naming" in *On Fear* and *Reflections on the Self*. If it
rarely fires independently of Thought, demote it to an alias.
Resolved by: the re-score above.

---

## Model for the full ~75k-passage tagging pass

> [!warning] Decision
> Once the re-score validates the labels, which model runs the full L3 pass?

Resolved by: the re-score, on a quality-per-dollar basis — that is the point of
running more than one arm.

---

## Relevance tiers still open

> [!note] Decision
> Confirm **Tier C** (esp. young-people discussions, ~147 h; films and
> documentaries) and decide whether the ~30 short **interviews** sit in **B**
> or **C**.

Currently: A/B in FTS, C archival-only. Independent of the concept layer —
low urgency.
Resolved by: the Phase-1 stats report's %-K-speech per event type, plus a call.

---
*Hand-authored. Not overwritten by the generator. When a decision is made,
record the rationale in `STRATEGY.md` and delete the item from this file.*
