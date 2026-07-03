export const meta = {
  name: 'quick-finish-review',
  description: 'Finish the cut-off pre-push review: lean correctness pass over the two changed scripts (final pushed state)',
  phases: [
    { title: 'Find', detail: '3 finders over b503574..HEAD for the two scripts' },
    { title: 'Verify', detail: 'one adversarial verifier per candidate' },
  ],
}

const REPO = '/Users/kryzh/Library/Mobile Documents/com~apple~CloudDocs/00-cod3/jiddu-krishnamurti'
const DIFF = `cd ${REPO} && git diff b503574..HEAD -- scripts/parse_vtt.py scripts/build_catalog.py`

const CAND_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    candidates: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          file: { type: 'string' },
          line: { type: 'number' },
          summary: { type: 'string' },
          why: { type: 'string', description: 'concrete trigger + wrong behavior' },
        },
        required: ['file', 'line', 'summary', 'why'],
      },
    },
  },
  required: ['candidates'],
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['CONFIRMED', 'PLAUSIBLE', 'REFUTED'] },
    evidence: { type: 'string' },
  },
  required: ['verdict', 'evidence'],
}

const base = `You are reviewing a small, already-landed diff. Working dir: ${REPO}.
Get the diff with:\n  ${DIFF}\nRead the two files (scripts/parse_vtt.py, scripts/build_catalog.py) for context around the changed lines. These are a Krishnamurti catalog/teachings-corpus project: items.year is derived from event_date; parse_vtt turns manual VTTs into speaker-attributed segments/passages; build_catalog rebuilds the catalog + Obsidian vault from a PDF.
Report ONLY high-confidence defects with a concrete trigger and a concrete wrong result — this is a QUICK review, so at most ~5 candidates, no style nits, no speculative "could be cleaner". If you find nothing real, return an empty list.`

const ANGLES = [
  { key: 'correctness', extra: 'Hunt for real correctness bugs in the changed lines: year-from-event-date and normalize_code_year fallback, the LABEL_RE / split_embedded / _is_sentence_end parser changes, materialize()/resolve_vtt, and render_md_table. Wrong output, crash, or data corruption only.' },
  { key: 'fix-regressions', extra: 'These changes were themselves made to FIX an earlier review. Check specifically whether any fix introduced a NEW bug or silently changed behavior for a real input: did tightening the no-space label rule now REJECT a legit speaker label? does normalize_code_year mishandle any real KFT code? does the materialize early-out skip a file that genuinely needs downloading? does render_md_table mis-align or corrupt a real cell (e.g. wikilink pipes, unicode)?' },
  { key: 'edge-cases', extra: 'Probe boundary inputs against the changed code: odd/empty/3-digit code year segments, en-GB vs en, multi-speaker cues, cues with no label, unicode in titles/place names, event_date with no 4-digit year or a date range, a K monologue with many ellipses/abbreviations.' },
]

phase('Find')
const found = (await parallel(ANGLES.map(a => () =>
  agent(`${base}\n\nYOUR ANGLE — ${a.key}: ${a.extra}`,
    { label: `find:${a.key}`, phase: 'Find', schema: CAND_SCHEMA })
))).filter(Boolean).flatMap(r => r.candidates || [])

const seen = new Set()
const uniq = found.filter(c => {
  const k = `${c.file}:${c.line}:${(c.summary || '').slice(0, 40)}`
  if (seen.has(k)) return false
  seen.add(k); return true
})
log(`${found.length} raw candidates -> ${uniq.length} unique`)

if (uniq.length === 0) {
  return { candidates: 0, kept: [], note: 'No candidates raised — the landed changes look clean.' }
}

phase('Verify')
const verified = (await parallel(uniq.map(c => () =>
  agent(`${base}\n\nVERIFY this candidate adversarially — DEFAULT TO REFUTED unless you can construct the exact failing input and show the wrong result from the actual code. Quote the relevant lines.\n\nCandidate: ${JSON.stringify(c)}`,
    { label: `verify:${c.file.split('/').pop()}:${c.line}`, phase: 'Verify', schema: VERDICT_SCHEMA })
    .then(v => v ? { ...c, verdict: v.verdict, evidence: v.evidence } : null)
))).filter(Boolean)

const kept = verified
  .filter(c => c.verdict === 'CONFIRMED' || c.verdict === 'PLAUSIBLE')
  .sort((a, b) => (a.verdict === 'CONFIRMED' ? 0 : 1) - (b.verdict === 'CONFIRMED' ? 0 : 1))

return { candidates: uniq.length, refuted: verified.length - kept.length, kept }
