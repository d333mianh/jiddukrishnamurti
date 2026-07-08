---
tags: [krishnamurti, root, decisions]
---
# Open Decisions

What still needs a human call on the concept layer, most actionable first. Each
item states the choice, the options, a recommendation, and what it's blocked on.
Keep this in sync with the `STRATEGY.md` decision log when a call is made.

> [!info] Where we are right now
> - The **36 roots are imported** into the corpus DB (33 active + 3 pilot).
> - The pilot runner is **upgraded and committed** (`8c33e6e`): full
>   relevance/definition labels, a `--model` flag, all-36 default.
> - The 500-passage re-score is **built and verified** end-to-end (dry run). The
>   only thing between here and results is the spend gate below.

---

## 1 · Pilot re-score — model arm + spend  ⟶ *needs your call*

> [!warning] Decision
> Re-score the 500-passage eval set against all 36 roots with the full label set.
> **Which model arm(s), and approve the spend?**

| Option | What it buys | Cost (batch, 50% off) |
|---|---|---|
| **Sonnet 5 only** | Resolves the merge pairs + word-naming; one model | **~$3–6** |
| **Sonnet 5 + Opus 4.8** *(recommended)* | Also settles which model to use for the full ~75k pass | **~$11–21** |

**Recommendation:** run **both arms.** The model choice for the *full* pass is a
$9-vs-$45 decision (see item 5); this ~$15 pilot is the cheap, correct place to
settle it while also measuring the boundary pairs.

**Blocked on:** `ANTHROPIC_API_KEY` in the environment, and your go-ahead on spend.
Set the key in-session with `! export ANTHROPIC_API_KEY='sk-ant-...'` — it is
never written to a file. Then: `--submit` → `--poll` → `--fetch`.

---

## 2 · Merge pair — `self` ↔ `self-knowledge`  ⟶ *pilot resolves*

> [!question] Decision
> Are [[self|The Self]] and [[self-knowledge|Self-knowledge]] reliably
> separable per passage, or should they merge into one root?

Kept **separate on probation.** Merge only if the pilot's confusion metrics show
the judge can't tell them apart per passage. **Blocked on:** pilot results (item 1).

---

## 3 · Merge pair — `religious-mind` ↔ `sacred`  ⟶ *pilot resolves*

> [!question] Decision
> Are [[religious-mind|The Religious Mind]] and [[sacred|The Sacred]] reliably
> separable per passage, or should they merge?

Same treatment as item 2: **separate on probation**, merge only on evidence of
unreliable separation. **Blocked on:** pilot results.

---

## 4 · Provisional root — `word-naming`  ⟶ *pilot resolves*

> [!question] Decision
> Does [[word-naming|The Word & Naming]] tag as an independent field, or fold
> into [[thought|Thought & Knowledge]]?

Kept as a **provisional root.** Independently supported by the book canon
("naming" in *On Fear* and *Reflections on the Self*). **Blocked on:** pilot
results — if it rarely fires independently of Thought, demote it to an alias.

---

## 5 · Model for the full ~75k-passage tagging pass  ⟶ *pilot informs*

> [!warning] Decision
> Once the pilot validates the labels, which model runs the full L3 tagging pass?

| Model | One-off cost (batch) |
|---|---|
| Haiku 4.5 | ~$9 |
| Sonnet 4.6 / Sonnet 5 | ~$26 |
| Opus 4.8 | ~$45 |

**Recommendation:** let the dual-arm pilot (item 1) decide on a quality-per-dollar
basis. **Blocked on:** pilot precision/recall against human labels.

---

## 6 · Relevance tiers still open  ⟶ *low urgency, needs data + a call*

> [!note] Decision
> Confirm **Tier C** (esp. young-people discussions, ~147 h; films/documentaries)
> and decide whether the ~30 short **interviews** sit in **B** or **C**.

Currently: A/B in FTS, C archival-only. The Phase-1 stats report gives the
actual %-K-speech per event type to settle this with data rather than taste.

---

## 7 · Security — rotate the pasted API key  ⟶ *do this regardless*

> [!danger] Action
> An Anthropic API key was pasted into a chat session, so it lives in the
> conversation log. **Rotate it in the Anthropic Console.** It is never written
> to any file in this repo; supply keys only as a runtime env var.

---
*Hand-authored decision log mirror. Not overwritten by the generator. When a
decision is made, record it in `STRATEGY.md` and update the status here.*
