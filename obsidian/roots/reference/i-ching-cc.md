# I Ching layer for the Map of the 36 Roots

*Design draft — mapping the 36 roots onto the I Ching's 36 hexagram figures.*

## Context

`obsidian/roots/` holds the L3 concept layer: **36 "roots"** of Krishnamurti's
teaching, numbered 1–36 across **4 facets × 9 roots**, generated from
`concepts/concepts.jsonl` by `scripts/build_concept_vault.py`. The Map renders
each root as a numbered list item. The user wants to (a) make the "36 number"
smaller/denser and (b) give the map an interactive **I Ching** character.

**Why this is not arbitrary.** The I Ching's 64 hexagrams collapse to **exactly
36 distinct figures** when a hexagram and its vertical mirror count as one
(8 self-symmetric + 28 flip-pairs = 36) — classically the **三十六宫, the
"thirty-six palaces,"** and the King Wen sequence is built as 36 paired units
(18 Upper Canon + 18 Lower Canon). So 36 is the I Ching's own reduced number, and
the 36 roots map one-to-one onto hexagram figures. Unicode carries all 64
hexagrams as **single characters** (䷀–䷿, U+4DC0–U+4DFF) that render in Obsidian
**with no plugin** — so a hexagram glyph can literally replace the `1.`–`36.`
marker.

## Open choices (need the user before build)

1. **Direction(s)** — 1 (glyph numbering, foundation) / 2 (in-Obsidian oracle) /
   3 (standalone web caster). They stack; 1 underlies 2 and 3.
2. **Mapping style** — *semantic* (hand-paired, recommended) vs *positional*
   (King Wen 1–36) vs decide-at-build.
3. **Glyph placement** — glyph *replaces* the number, or *precedes* it
   (`14. ䷅ [[conflict|Conflict]]`). Recommended: precede, so ordering + backlinks
   stay intact.
4. Does "make 36 smaller" mean **compact markers** (assumed) or **reduce the
   count** below 36? Reducing fights the carefully-triangulated set — flag if
   that's the intent.

---

## Recommended approach

**Direction 1 (foundation) + Direction 2 (in-Obsidian oracle), semantic mapping,
glyph precedes number.** Direction 3 (web caster) is an optional add-on I can
build as an Artifact. All generated changes flow through the JSONL + generator so
they survive every regen.

### A. Data (source of truth) — `concepts/concepts.jsonl`

Add ONE field per concept: `"hexagram": <1-64>` (King Wen number). Glyph, Chinese
name, pinyin, and English are **derived**, not stored, to keep one source.

### B. Hexagram data + glyph derivation — new `scripts/iching_data.py`

- A `HEXAGRAMS` table: `{n: (chinese, pinyin, english)}` for all 64.
- `glyph(n) -> chr(0x4DBF + n)` (U+4DC0 == King Wen #1; block is in King Wen
  order). Helper `label(n) -> "䷅ 6 · Sòng · Conflict"`.
- Imported by `build_concept_vault.py` (and reused by the web caster).

### C. Renderer — `scripts/build_concept_vault.py`

- `render_map()`: each list item becomes
  `14. ䷅ [[conflict|Conflict]] — *hook*` with the hexagram name folded into the
  facet header or a trailing ` · Sòng 6`. (The recent commits `8487b3b`/`945f7d6`
  already tune this exact renderer — extend, don't rewrite.)
- `render_concept()`: add `hexagram`, `hexagram_glyph`, `hexagram_name` to
  frontmatter; extend the metadata line to
  `**Root 14 of 36** · **䷅ Sòng · Conflict (6)** · [[Map…]]`; optional one-line
  *I Ching resonance* note from an optional `hexagram_note` JSONL field.
- Keep the "generated — edit the JSONL" footer semantics unchanged.

### D. Proposed semantic mapping (first pass — for review)

Injective (no hexagram used twice). ★ = strong/often literal, ~ = tentative,
needs a look. Two deliberate bookends: **root 1 Thought ↔ hexagram 1 乾**,
**root 36 Sacred ↔ hexagram 64 未濟** (last↔last, "before completion / never a
destination"). Wink: root 12 Suffering ↔ hexagram 36 明夷.

**I. Structures of Consciousness**
| # | Root | Hex | Name | |
|---|---|---|---|---|
| 1 | Thought & Knowledge | 1 ䷀ | 乾 Qián · The Creative | ~ emblem: the active builder; #1↔#1 |
| 2 | Conditioning | 18 ䷑ | 蠱 Gǔ · Work on the Decayed | ★ inherited spoilage to be undone |
| 3 | The Self | 29 ䷜ | 坎 Kǎn · The Abysmal | ★ the pit / entrapment |
| 4 | Psychological Time | 5 ䷄ | 需 Xū · Waiting | ★ becoming / postponement |
| 5 | Relationship | 31 ䷞ | 咸 Xián · Influence | ★ mutual influence, the mirror |
| 6 | Division | 38 ䷥ | 睽 Kuí · Opposition | ★ estrangement / fragmentation |
| 7 | Belief & Ideals | 26 ䷙ | 大畜 Dà Chù · Great Accumulation | ~ ideology stored as security |
| 8 | Consciousness | 2 ䷁ | 坤 Kūn · The Receptive | ★ the field that holds all content |
| 9 | The Word & Naming | *tbd* | 62 小過 / 50 鼎 | ~ symbol/detail over essence — finalize |

**II. Human Experience & Relationship**
| # | Root | Hex | Name | |
|---|---|---|---|---|
| 10 | Fear | 51 ䷲ | 震 Zhèn · Shock/Thunder | ★ |
| 11 | Desire & Pleasure | 58 ䷹ | 兌 Duì · The Joyous | ★ sensation/pleasure |
| 12 | Suffering | 36 ䷣ | 明夷 Míng Yí · Darkening of the Light | ★ affliction (hex #36) |
| 13 | Loneliness | 12 ䷋ | 否 Pǐ · Standstill | ~ non-communion, cut off |
| 14 | Conflict | 6 ䷅ | 訟 Sòng · Conflict | ★ literal |
| 15 | Violence | 7 ䷆ | 師 Shī · The Army | ~ organized force |
| 16 | Comparison & Measure | 60 ䷻ | 節 Jié · Limitation/Measure | ~ measurement |
| 17 | Attachment | 8 ䷇ | 比 Bǐ · Holding Together | ★ clinging / dependence |
| 18 | Authority & Following | 17 ䷐ | 隨 Suí · Following | ★ literal |

**III. Observation, Inquiry & Action**
| # | Root | Hex | Name | |
|---|---|---|---|---|
| 19 | Freedom | 40 ䷧ | 解 Xiè · Deliverance | ★ release |
| 20 | Observer Is Observed | 30 ䷝ | 離 Lí · The Clinging/Light | ~ doubling of perception |
| 21 | Awareness & Attention | 20 ䷓ | 觀 Guān · Contemplation | ★ choiceless observation |
| 22 | Insight & Intelligence | 21 ䷔ | 噬嗑 Shì Kè · Biting Through | ★ seeing through the false |
| 23 | Learning & Education | 4 ䷃ | 蒙 Méng · Youthful Folly | ★ the classic teaching hexagram |
| 24 | Truth & "What Is" | 61 ䷼ | 中孚 Zhōng Fú · Inner Truth | ★ literal name |
| 25 | Order & Disorder | 63 ䷾ | 既濟 Jì Jì · After Completion | ~ order (K warns it slides back) |
| 26 | Action | 25 ䷘ | 無妄 Wú Wàng · Innocence | ★ action without motive/from perception |
| 27 | Self-knowledge | 48 ䷯ | 井 Jǐng · The Well | ~ the inner source; echoes self=坎 (both water) |

**IV. Ending, Transformation & the Sacred**
| # | Root | Hex | Name | |
|---|---|---|---|---|
| 28 | Love & Compassion | 42 ䷩ | 益 Yì · Increase | ~ selfless benefaction |
| 29 | Death & Ending | 24 ䷗ | 復 Fù · Return | ★ ending as renewal (solstice return) |
| 30 | Meditation & Silence | 52 ䷳ | 艮 Gèn · Keeping Still | ★ literal stillness |
| 31 | Beauty | 22 ䷕ | 賁 Bì · Grace | ★ beauty/adornment |
| 32 | Nature & the Earth | *tbd* | 46 升 / 27 頤 | ~ growth / the earth nourishes — finalize |
| 33 | Energy & Passion | 34 ䷡ | 大壯 Dà Zhuàng · Great Vigor | ★ undivided strength |
| 34 | Transformation | 49 ䷰ | 革 Gé · Revolution | ★ literal: molting/revolution |
| 35 | The Religious Mind | 59 ䷺ | 渙 Huàn · Dispersion | ~ dissolving the self |
| 36 | The Sacred | 64 ䷿ | 未濟 Wèi Jì · Before Completion | ★ never a destination; #64↔root 36 |

Two cells (`word-naming`, `nature`) are deliberately left open; ~9 more are
tentative. Finalizing these 36 pairings is a short review pass with the user
before build — the mapping is the one genuinely curatorial part.

### E. Direction 2 — interactive oracle inside Obsidian

- **Cast a Root.** Enable the core Random-note plugin (`obsidian/.obsidian/
  core-plugins.json`: `"random-note": false → true`; it also supports "open from
  search results" so `path:concepts` scopes the draw). Add a *Cast a Root*
  section to the hand-authored hub `Roots of Knowledge.md` explaining the
  practice — resonant with K: *"truth is a pathless land"* — you meet what
  arises, you don't choose it.
- **Oracle Board (Canvas).** Generate `obsidian/roots/Oracle Board.canvas` (JSON:
  `type:"file"` nodes) — the 36 as a 6×6 grid (or King-Wen circle), each card
  linking to its concept note, colored by facet, labeled with its hexagram glyph.
  Canvas core plugin is already enabled. Add this path to the generator's
  ownership set so regen keeps it fresh.

### F. Direction 3 (optional add-on) — standalone web caster

Self-contained HTML **three-coin toss**: animates a hexagram line by line →
lands on the matching root with its definition, facet, and glyph. Roots +
definitions + hexagram numbers embedded inline as JSON (exported from the corpus
by a tiny script). Built as an **Artifact** (loads the `artifact-design` skill
first). Lives outside the vault — Obsidian core can't run JS.

---

## Files touched

- `concepts/concepts.jsonl` — add `hexagram` (+ optional `hexagram_note`) per root.
- `scripts/iching_data.py` — **new**: 64-hexagram table + `glyph()`/`label()`.
- `scripts/build_concept_vault.py` — extend `render_map()` / `render_concept()`;
  add `Oracle Board.canvas` generation + ownership; `--check` still passes.
- `obsidian/.obsidian/core-plugins.json` — enable `random-note` (Direction 2).
- `obsidian/roots/Roots of Knowledge.md` — hand-add "Cast a Root" (Direction 2).
- `scripts/concept_schema.py` / `L3-SCHEMA.md` — document the new `hexagram` field.
- (Direction 3) an Artifact HTML page + a small JSON export script.

## Verification

1. `python3 scripts/build_concept_vault.py` — regenerate; then
   `python3 scripts/build_concept_vault.py --check` exits 0 (no stale notes).
2. Open `Map of the 36 Roots.md` in Obsidian — glyphs render, numbers + wikilinks
   intact, one hexagram per root, none duplicated.
3. `python3 -m unittest discover tests` — parser/schema regressions green.
4. `git diff --stat` — only the files above; `obsidian/roots/` hand-authored
   notes (hub, Open Decisions, reference/) untouched by the generator.
5. Direction 2: open `Oracle Board.canvas` in Canvas; trigger Random-note scoped
   to `path:concepts`.
6. Direction 3: open the Artifact URL and cast a hexagram → lands on a root.

## Not doing (unless asked)

- Reducing below 36 roots (would fight the triangulated set).
- Community plugins (Dataview/Templater/JS) — everything above is core-plugin or
  generator-driven.
- Re-deriving or re-ordering the facets.
