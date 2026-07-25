# Archived: the I Ching navigation layer

**Archived 2026-07-25 — parked, not rejected.** The layer worked and its tests
passed; the decision on whether it belongs in the project is deferred. Nothing
in the catalog, corpus, or L3 registry ever depended on it: `concepts.jsonl`
was and remains canonical, and no root's definition referenced a gate.

## What it was

Eight trigram "gates" whose 36 *unordered* pairs (8 self-pairs + 28 distinct)
map one-to-one onto the 36 concept roots. The number 36 is derived from the
structure, not chosen to fit. Framing was **navigator, not oracle**: a cast
selects *what to inquire into*; no judgements, no line texts, no changing
lines. King Wen numbering was used only because the Unicode hexagram block
`U+4DC0–U+4DFF` is laid out in that order (`glyph(n) = chr(0x4DBF + n)`).

Grounding: K discusses the I Ching in three archived San Diego conversations
with Allan W. Anderson (SD72CA1, SD74CA4, SD74CA5) — see the timestamps in
`vault/I Ching Navigator.md`.

## What is here

| Path | Was |
|---|---|
| `iching_data.py` | `scripts/iching_data.py` — King Wen table, glyphs, `lines_to_gates`, `validate_navigation` |
| `iching_navigation.json` | `concepts/iching_navigation.json` — gate/pair → root mapping |
| `test_iching_data.py` | `tests/test_iching_data.py` |
| `vault/I Ching Navigator.md` | `obsidian/roots/I Ching Navigator.md` (generated) |
| `vault/gates/*.md` | `obsidian/roots/gates/*.md` (generated) |
| `build_concept_vault-iching.patch` | the diff that *removed* the rendering code from `scripts/build_concept_vault.py` |

## How to bring it back

1. Move the four source files back:
   `iching_data.py` → `scripts/`, `iching_navigation.json` → `concepts/`,
   `test_iching_data.py` → `tests/`.
2. Reverse the rendering diff:
   `git apply -R archive/iching/build_concept_vault-iching.patch`
   (if `build_concept_vault.py` has since drifted, read the patch and re-apply
   by hand — it is the whole of the removed code: `gate_label`,
   `bridge_figures`, `short_name`, `render_gate`, `render_navigator`, the
   bridge callout in `render_concept`, the "Another way in" tip in
   `render_map`, and the `GATES_DIR`/`NAVIGATOR_NOTE` outputs).
3. Restore the I Ching tests in `tests/test_build_concept_vault.py` (they were
   deleted in the same commit as this archive — recover them from git history)
   and drop `test_iching_layer_stays_archived`, which exists to keep the
   layer out of the generated vault while it is parked.
4. Re-add the vault links removed from the hand-authored notes
   `obsidian/roots/Roots of Knowledge.md`, `obsidian/roots/reference/Strategy.md`,
   and `obsidian/roots/reference/L3 Schema.md`.
5. `python3 scripts/build_concept_vault.py && python3 scripts/build_concept_vault.py --check`
   — the vault goes from 37 notes back to 46.

The generated notes under `vault/` are kept only as a record of what the layer
looked like; regeneration reproduces them.
