# I Ching Navigator for the 36 Roots

Status: reviewed implementation plan  
Date: 2026-07-10

## Summary

Add a provisional, I Ching-inspired navigation layer to the Obsidian roots
vault. It reduces the initial choice from 36 roots to eight trigram gates while
preserving the existing roots, numbers, four facets, definitions, and L3
database model.

The key construction is:

```text
8 self-pairs + 28 distinct two-gate pairs = 36 bridges
```

Each root is assigned to one unique unordered pair of gates. A six-line cast
restores direction: the bottom three lines form the lower gate and the top
three form the upper gate. Changing lines can produce a second, relating root.

This is a newly authored discovery interface, not a claim that Krishnamurti's
roots historically correspond to the I Ching or that there is a canonical
"36-root" I Ching system. Its output opens an inquiry; it does not answer a
question or act as an oracle.

## Review conclusions

- Keep `concepts/concepts.jsonl` canonical and unchanged. The trigram mapping is
  provisional navigation metadata, not part of a root's definition.
- Do not assign roots directly to King Wen numbers 1–36. Those numbers already
  identify particular hexagrams and would create false semantic equivalences.
- Do not bundle traditional judgments, line texts, prognoses, or copyrighted
  translations. V1 uses only trigram structure and original navigation copy.
- Do not enable Obsidian's Random Note plugin or edit `.obsidian` settings.
  Random Note does not implement a six-line cast and vault settings are local
  user state.
- Do not add an L3 schema column. The corpus concept model remains independent
  of this optional interface.
- Do not use keyword search as if it produced accepted concept citations.
  Passage display must be backed by accepted `passage_tags`.

## Eight gates

The traditional symbols and broad images are retained, with a deliberately
limited inquiry phrase for rendering readings:

| Key | Symbol | Lines, bottom-to-top | Display name | Inquiry phrase |
|---|---:|---:|---|---|
| `qian` | ☰ | `111` | Creative / Heaven | unbounded energy and possibility |
| `kun` | ☷ | `000` | Receptive / Earth | receptive attention to what is |
| `zhen` | ☳ | `100` | Arousing / Thunder | disturbance, movement, and change |
| `xun` | ☴ | `011` | Penetrating / Wind | subtle influence, thought, and conditioning |
| `kan` | ☵ | `010` | Abysmal / Water | fear, insecurity, and human depth |
| `li` | ☲ | `101` | Clinging / Fire | image, consciousness, and illumination |
| `gen` | ☶ | `001` | Stillness / Mountain | ending, stillness, and order |
| `dui` | ☱ | `110` | Joyous / Lake | relationship, feeling, and communion |

The inquiry phrases are interface language, not additional definitions of the
roots or translations of I Ching texts.

## Fixed v1 bridge mapping

Every unordered gate pair appears exactly once and every current root appears
exactly once.

| First gate | Second gate(s) and assigned roots |
|---|---|
| ☰ Creative | ☰ Energy & Passion; ☷ Sacred; ☳ Transformation & Mutation; ☴ Thought & Knowledge; ☵ Freedom; ☲ Insight & Intelligence; ☶ Death & Ending; ☱ Love & Compassion |
| ☷ Receptive | ☷ Awareness & Attention; ☳ Learning & Education; ☴ Self-knowledge; ☵ Suffering; ☲ Truth & "What Is"; ☶ Nature & the Earth; ☱ Beauty |
| ☳ Arousing | ☳ Action; ☴ Psychological Time & Becoming; ☵ Conflict; ☲ Violence; ☶ Order & Disorder; ☱ Desire & Pleasure |
| ☴ Penetrating | ☴ Conditioning; ☵ Security & Attachment; ☲ The Word & Naming; ☶ Authority & Following; ☱ Comparison & Measurement |
| ☵ Abysmal | ☵ Fear; ☲ Division / Fragmentation; ☶ Loneliness & Aloneness; ☱ Belief & Ideals |
| ☲ Clinging | ☲ Consciousness & Its Content; ☶ The Observer Is the Observed; ☱ The Self |
| ☶ Stillness | ☶ Meditation & Silence; ☱ The Religious Mind |
| ☱ Joyous | ☱ Relationship & Image-making |

The mapping is labeled `provisional` wherever it is displayed. Revising it
must not change root slugs, canonical root order, concept versions, or existing
passage tags.

## Authored navigation data

Add `concepts/iching_navigation.json` as the sole source of truth for this
interface. Its top-level shape is:

```json
{
  "schema_version": 1,
  "status": "provisional",
  "gates": [
    {
      "key": "qian",
      "symbol": "☰",
      "lines": "111",
      "name": "Creative / Heaven",
      "inquiry_phrase": "unbounded energy and possibility"
    }
  ],
  "bridges": [
    {
      "gates": ["qian", "xun"],
      "root": "thought"
    }
  ]
}
```

Validation must reject the complete file before rendering if any invariant
fails:

- exactly eight unique gate keys, symbols, and three-bit patterns;
- exactly 36 unique unordered gate pairs, including all eight self-pairs;
- every possible unordered pair covered once;
- exactly 36 unique root slugs;
- every bridge root exists in `concepts/concepts.jsonl`;
- every active or pilot root in the registry is mapped once.

## Generated Obsidian navigation

Extend `scripts/build_concept_vault.py`; do not add a second generator for the
same subtree. It should read and validate both authored files and generate:

### `obsidian/roots/I Ching Navigator.md`

- Explain that the navigator is provisional, non-sequential, and non-oracular.
- Show eight linked gate cards or sections as the compact entry point.
- Show a symmetric 8×8 bridge matrix. Use only the upper triangle for the 36
  clickable root links; the lower triangle may point to the matching reflected
  cell or remain blank.
- Include concise instructions for browsing and for running the companion cast
  command.
- Ground the ethical framing in the archive's own I Ching conversations:
  `SD72CA1` around 00:03:08, `SD74CA4` around 00:08:08, and `SD74CA5`
  around 00:55:03. Link to the catalog's primary YouTube URLs with timestamps;
  paraphrase rather than reproducing long transcript excerpts.

### `obsidian/roots/gates/<key>.md`

Generate eight notes. Each contains:

- the trigram symbol, display name, line pattern, and inquiry phrase;
- the eight incident bridges, counting the self-pair once;
- links to the other gate and the assigned root for every bridge;
- a return link to the navigator.

This means a reader sees eight choices at the hub and at most eight roots after
choosing a gate.

### Existing generated notes

- Add a short navigator callout near the top of `Map of the 36 Roots.md`; keep
  its canonical four-facet list intact.
- Add `iching_gates: [qian, xun]` to generated concept-note frontmatter.
- Add a visible provisional bridge line to each concept note with links to both
  gate notes and the navigator.
- Preserve the existing generated-file warnings and `--check` behavior.
- Continue leaving the curated hub, `Open Decisions.md`, and `reference/`
  untouched.

## Companion casting command

Add `scripts/cast_roots.py` with the standard repository CLI anatomy.

```bash
python3 scripts/cast_roots.py
python3 scripts/cast_roots.py --lines 7,8,9,6,7,8
python3 scripts/cast_roots.py --stdout
python3 scripts/cast_roots.py --open
```

Behavior:

1. With no `--lines`, generate six lines bottom-to-top by tossing three virtual
   fair coins per line. Each coin contributes 2 or 3, producing values 6–9.
2. `--lines` accepts exactly six comma-separated integers in the range 6–9,
   ordered bottom-to-top. This supports physical casts and reproducible tests.
3. Even values are broken lines; odd values are solid lines. Lines 6 and 9 are
   changing and flip for the relating figure.
4. Lines 1–3 select the lower gate and lines 4–6 select the upper gate.
5. Sort the two gate keys only for bridge lookup. Preserve their original
   lower/upper order in the rendered reading.
6. Render the primary root. If any lines change, render the relating root. If
   both figures resolve to the same bridge, describe it as movement within the
   same root instead of duplicating the result.
7. Build the inquiry text mechanically:
   - different gates: `What becomes visible about <root> when <lower phrase> is
     met through <upper phrase>?`
   - self-pair: `What becomes visible about <root> when <gate phrase> is both
     the ground and the lens?`
8. By default, write a timestamped Markdown note under
   `obsidian/roots/readings/`. Add that directory to `.gitignore` because these
   readings are personal generated state. Name notes
   `YYYYMMDDTHHMMSS.ffffffZ-<12-hex-token>.md`, generate the suffix with
   `secrets.token_hex(6)`, and create the file exclusively so a cast can never
   overwrite an earlier reading.
9. `--stdout` prints the same rendering without writing a file.
10. `--open` writes the note and then uses the macOS `open` command with an
    `obsidian://open` URI. URI-encode the vault and note paths. A failure to open
    Obsidian must leave the written reading intact and return an actionable
    error. Reject `--stdout --open` as incompatible.

Use dependency-free standard-library Python. Keep casting and rendering as pure
functions where possible so tests can supply fixed line values without adding
a public random seed option.

## Reading-note content

Each saved reading records enough state to reproduce and audit it:

- UTC timestamp;
- six numeric line values, explicitly labeled bottom-to-top;
- primary and relating line diagrams;
- ordered lower and upper gates for each figure;
- root wikilinks, definitions, and generated inquiry questions;
- accepted passage and timestamped citation when one exists;
- navigation disclaimer and link back to `I Ching Navigator`.

Do not store a prediction, answer, recommendation, fortune, or generated
interpretation.

## Accepted-passage integration

For each revealed root, query only the existing accepted-tag view:

```text
passage_tags
  -> concepts
  -> passage_anchors
  -> catalog items/item_links
```

A passage is eligible only when:

- the root slug matches;
- `passage_anchors.anchor_status = 'live'`;
- `passage_anchors.passage_id IS NOT NULL`;
- `passage_anchors.speaker_code = 'K'`;
- `passage_anchors.timestamps_synthetic = 0`;
- a primary catalog link exists.

Sort eligible rows by anchor ID, select one at cast time with `secrets.choice`,
and write its snapshot text, item code,
start time, recording-note wikilink, and `youtu.be/ID?t=<seconds>` link into
the reading. Use integer seconds from `t_start` and choose `?t=` or `&t=` based
on the existing URL.

The current database has no accepted `passage_tags`. Until eligible rows exist,
render:

> No accepted citable passage is available for this root yet.

Then show the canonical definition and concept-note link. Do not fall back to
FTS or aliases. A missing gitignored corpus database, missing concept tables, or
zero eligible rows uses the same fallback with a concise reason; invalid
navigation data remains a fatal error.

## Tests

Add focused stdlib `unittest` coverage for navigation validation, generator
output, and casting.

Required cases:

- the committed mapping covers exactly 8 gates, 36 bridges, and 36 roots;
- all 64 ordered primary figures resolve to a bridge;
- the 8 self-pairs have one orientation and the 28 other bridges each receive
  two ordered orientations;
- known manual line sets produce the expected lower/upper gates and roots;
- 6 and 9 flip while 7 and 8 remain stable;
- an unchanged cast omits the relating section;
- changed figures resolving to the same bridge are not duplicated;
- malformed, short, long, or out-of-range `--lines` input fails clearly;
- reading filenames cannot collide during rapid successive casts;
- an empty `passage_tags` view produces the exact fallback message;
- an eligible accepted passage produces the expected Obsidian and timestamped
  YouTube links;
- stale, synthetic, non-K, detached, and unlinked anchors are excluded;
- generated vault files pass `scripts/build_concept_vault.py --check` after a
  normal regeneration and fail when deliberately stale in an isolated test.

Verification commands:

```bash
python3 scripts/build_concept_vault.py
python3 scripts/build_concept_vault.py --check
python3 scripts/cast_roots.py --lines 7,8,9,6,7,8 --stdout
python3 -m unittest discover tests
git status --short
```

## Files expected to change

- `concepts/iching_navigation.json` — new authored navigation mapping.
- `scripts/build_concept_vault.py` — validation and generated navigation.
- `scripts/cast_roots.py` — new companion caster.
- `tests/test_build_concept_vault.py` — mapping and rendering coverage.
- `tests/test_cast_roots.py` — casting and citation coverage.
- `.gitignore` — ignore personal reading notes.
- Generated files owned by `build_concept_vault.py` under `obsidian/roots/`.

No changes are planned for `concepts/concepts.jsonl`, `concept_schema.py`, the
corpus schema, root ordering, four facets, `.obsidian` settings, or curated root
notes.

## Acceptance criteria

- A reader can enter through eight gates and reach every root in no more than
  two clicks.
- The navigator and every concept note disclose that the mapping is
  provisional and non-canonical.
- The casting command deterministically reproduces manually supplied lines and
  correctly derives primary and relating roots.
- The tool never emits an oracle-style answer or an unaccepted passage.
- Regeneration is idempotent and `--check` detects stale output.
- All repository tests pass.

## Reference boundaries

Traditional trigram symbols and six-line mechanics may be checked against the
[Chinese Text Project's Book of Changes](https://ctext.org/book-of-changes/yi-jing).
The implementation must not imply that the 36 bridge mapping comes from that
source; it is specific to this archive.
