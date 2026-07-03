#!/usr/bin/env python3
"""Parse a manual KFT VTT into L2 segments + passages (Phase 1, the Segments layer).

Pipeline per item:
  1. resolve the on-disk VTT (heals multi-part path drift; brctl-materializes iCloud)
  2. parse cues (HH:MM:SS.mmm timestamps; cue text = wrapped lines joined)
  3. build a PER-ITEM speaker-label registry by scanning the file's own labels
     (admit a label only if it is a trusted seed OR recurs >=2x — this is what
     defeats false positives like "There is extraordinary change:" which look like
     "Label:" but appear once and are not seeds)
  4. tag each cue's speaker via the registry allowlist; unlabeled cues inherit the
     previous speaker; leading unlabeled cues = ANN (announcer intro)
  5. merge contiguous same-speaker cues into atomic turn segments
  6. sub-chunk K monologues into ~150-200-word passages at sentence boundaries
     (non-K turns = one passage each); timestamps come from the bounding cues
  7. write transcripts/speaker_labels/segments/passages and the K-only FTS index

Idempotent per (item, kind, language): re-ingesting deletes the prior rows first.

Usage:
  # standalone slice / validation (no DB lookups; provide the file directly):
  parse_vtt.py --db /tmp/k_test.db --vtt "/path/to/LO61T1.en.vtt" --item LO61T1
  # batch from the catalog (resolves VTTs under the media root):
  parse_vtt.py --db catalog/krishnamurti.db --event-type T [--limit N]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
MEDIA_ROOT = (
    Path.home()
    / "Library/Mobile Documents/com~apple~CloudDocs/00-cod3/jiddu-krishnamurti"
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segment_schema import PARSER_VERSION, ensure_segment_schema  # noqa: E402

# ── passage sizing ────────────────────────────────────────────────────────────
TARGET_MIN, HARD_MAX, MIN_TAIL = 150, 260, 60

# ── speaker registry ──────────────────────────────────────────────────────────
# Trusted always-admit labels (unambiguous; admitted even on a single occurrence).
ALWAYS_SEED = {"k", "krishnamurti", "krishnaji", "q", "questioner", "question"}
# Canonical mapping for known labels (token -> (speaker_code, display_name)).
SEED_MAP = {
    "k": ("K", "Krishnamurti"), "krishnamurti": ("K", "Krishnamurti"),
    "krishnaji": ("K", "Krishnamurti"),
    "q": ("Q", "Questioner"), "questioner": ("Q", "Questioner"),
    "question": ("Q", "Questioner"), "audience": ("Q", "Audience"),
    "db": ("DB", "David Bohm"), "bohm": ("DB", "David Bohm"),
    "david bohm": ("DB", "David Bohm"),
    "a": ("AWA", "Allan W. Anderson"), "anderson": ("AWA", "Allan W. Anderson"),
    "allan anderson": ("AWA", "Allan W. Anderson"),
    "pj": ("PJ", "Pupul Jayakar"), "jayakar": ("PJ", "Pupul Jayakar"),
    "pupul jayakar": ("PJ", "Pupul Jayakar"), "pupul": ("PJ", "Pupul Jayakar"),
    "wr": ("WR", "Walpola Rahula"), "rahula": ("WR", "Walpola Rahula"),
}
# Tokens that may open a cue with NO space after the colon ("Q:No."). Restricting the
# no-space path to these (or short all-caps initials) keeps a prose colon like
# "Yes:absolutely" from being minted as a speaker.
SEED_LABELS = ALWAYS_SEED | set(SEED_MAP)

# A cue may open with a speaker label ("K: ...", "David Bohm: ..."). The space and
# the tail are captured separately so parse_cues can accept a multi-word label only
# when a space (or end-of-cue) follows the colon — leaving a prose colon like
# "We are asking: ..." to the registry's seed/recurrence gate — while STILL accepting
# a tight single-token tag with no space ("Q:No.", "K:Right?"), which some KFT
# dialogue subs use and which previously collapsed the whole file to one ANN segment.
LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 .'’\-]{0,30}?):(\s*)(.*)$", re.S)
TS_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
ABBREV = {"mr", "mrs", "ms", "dr", "st", "sr", "jr", "vs", "etc", "no", "vol"}
# Quote/bracket wrappers stripped from BOTH ends of a token before sentence-end tests.
WRAP = "\"'’‘“”()[]"


@dataclass
class Cue:
    t_start: float
    t_end: float
    text: str
    label: str | None = None  # raw label that opened the cue, if any (pre-registry)
    rest: str = ""            # cue text with the label stripped


@dataclass
class Segment:
    speaker_code: str
    raw_label: str | None
    cues: list[Cue] = field(default_factory=list)


def _ts(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_cues(text: str) -> list[Cue]:
    """Split a WEBVTT body into cues. Cue = optional id line, a timestamp line, text lines."""
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ts_idx is None:
            continue  # header (WEBVTT/Kind:/Language:/NOTE) or stray block
        m = TS_RE.search(lines[ts_idx])
        if not m:
            continue
        t_start = _ts(*m.group(1, 2, 3, 4))
        t_end = _ts(*m.group(5, 6, 7, 8))
        body = " ".join(ln.strip() for ln in lines[ts_idx + 1:]).strip()
        body = re.sub(r"<[^>]+>", "", body)  # strip any inline tags
        lm = LABEL_RE.match(body)
        label, rest = (None, body)
        if lm:
            cand, gap, tail = lm.group(1).strip(), lm.group(2), lm.group(3)
            # accept if a space follows the colon, or the label ends the cue; OR a
            # no-space tag that LOOKS like a speaker label — a known seed ("Q:No.") or
            # short all-caps initials ("DB:yes") — so a prose colon ("Yes:absolutely")
            # is not minted as a candidate (it would otherwise pass the >=2x gate).
            looks_like_label = cand.lower() in SEED_LABELS or (cand.isupper() and len(cand) <= 4)
            if gap or tail == "" or looks_like_label:
                label, rest = cand, tail.strip()
        cues.append(Cue(t_start, t_end, body, label=label, rest=rest))
    return cues


def build_registry(cues: list[Cue]) -> dict[str, tuple[str, str, int]]:
    """raw_label -> (speaker_code, display_name, cue_hits). Admit a label only if it
    is a trusted seed or recurs >=2x; everything else is a sentence-internal colon."""
    counts: dict[str, int] = {}
    for c in cues:
        if c.label is not None:
            counts[c.label] = counts.get(c.label, 0) + 1
    registry: dict[str, tuple[str, str, int]] = {}
    for raw, n in counts.items():
        token = raw.lower().strip()
        admit = token in ALWAYS_SEED or n >= 2
        if not admit:
            continue
        if token in SEED_MAP:
            code, name = SEED_MAP[token]
        else:
            code = re.sub(r"[^A-Za-z0-9]", "", raw).upper()[:8] or "UNK"
            name = raw
        registry[raw] = (code, name, n)
    return registry


def split_embedded(cues: list[Cue], registry: dict) -> list[Cue]:
    """Some manual cues pack two speakers ("Q: … K: …"). Split a cue at any
    registry label that appears mid-body, interpolating the timestamp by word
    position. Only admitted labels trigger a split, so false positives like
    "The gentleman asks:" stay attached to the current speaker."""
    if not registry:
        return cues
    alt = "|".join(re.escape(lbl) for lbl in sorted(registry, key=len, reverse=True))
    # match a registry label's colon whether or not a space follows ("Q:No." as well
    # as "Q: No.") — same no-space tolerance as LABEL_RE, so a cue that packs a speaker
    # change with no space ("Q:No. K:Right.") splits instead of collapsing to one tag.
    splitter = re.compile(r"(?:^|(?<=\s))(" + alt + r"):\s*")
    out: list[Cue] = []
    for c in cues:
        body = c.text
        matches = list(splitter.finditer(body))
        if not matches:
            out.append(Cue(c.t_start, c.t_end, body, label=None, rest=body))
            continue
        pieces: list[tuple[str | None, str]] = []
        if matches[0].start() > 0:
            lead = body[: matches[0].start()].strip()
            if lead:
                pieces.append((None, lead))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            pieces.append((m.group(1), body[m.end():end].strip()))
        total = sum(len(t.split()) for _, t in pieces) or 1
        dur = c.t_end - c.t_start
        acc = 0
        for lbl, t in pieces:
            ps = c.t_start + dur * (acc / total)
            acc += len(t.split())
            pe = c.t_start + dur * (acc / total)
            out.append(Cue(ps, pe, t, label=lbl, rest=t))
    return out


def build_segments(cues: list[Cue], registry: dict) -> list[Segment]:
    """Tag speakers via the registry allowlist, inherit across unlabeled cues
    (leading unlabeled cues = ANN), then merge contiguous same-speaker cues."""
    segments: list[Segment] = []
    current = "ANN"
    seen_speaker = False
    for c in cues:
        if c.label in registry:
            code, raw, text, seen_speaker = registry[c.label][0], c.label, c.rest, True
        else:
            code, raw, text = (current if seen_speaker else "ANN"), None, c.text
        current = code
        piece = Cue(c.t_start, c.t_end, text, label=raw, rest=text)
        if segments and segments[-1].speaker_code == code:
            segments[-1].cues.append(piece)
        else:
            segments.append(Segment(code, raw, [piece]))
    return segments


def _is_sentence_end(word: str) -> bool:
    core = word.strip(WRAP)  # strip wrappers from BOTH ends: '"Mr.' / '(Dr.' / '“U.'
    if not core or core[-1] not in ".?!":
        return False
    if core.endswith("…") or core.endswith(".."):
        return False  # trailing ellipsis ("perhaps...", "..."): a pause, not a boundary
    base = core.rstrip(".?!")
    if not base:
        return False  # punctuation-only token ("?!" / "."): a pause, not a boundary
    if base.lower() in ABBREV:
        return False
    # single/double capital initial like "J." or "K." is not a sentence end
    if core.endswith(".") and base.isalpha() and base.isupper() and len(base) <= 2:
        return False
    return True


def chunk_passages(seg: Segment) -> list[tuple[float, float, str, int]]:
    """K turns: split into ~150-200-word passages at sentence boundaries (tiny tail
    merges upward). Non-K turns: one passage. Timestamps from the bounding cues."""
    words: list[str] = []
    cue_of: list[int] = []
    is_end: list[bool] = []
    for ci, c in enumerate(seg.cues):
        for w in c.rest.split():
            words.append(w)
            cue_of.append(ci)
            is_end.append(_is_sentence_end(w))
    n = len(words)
    if n == 0:
        return []
    if seg.speaker_code != "K":
        return [(seg.cues[0].t_start, seg.cues[-1].t_end, " ".join(words), n)]

    bounds: list[tuple[int, int]] = []
    start = 0
    for i in range(n):
        count = i - start + 1
        if (is_end[i] and count >= TARGET_MIN) or count >= HARD_MAX:
            bounds.append((start, i))
            start = i + 1
    if start <= n - 1:
        bounds.append((start, n - 1))
    if len(bounds) >= 2 and (bounds[-1][1] - bounds[-1][0] + 1) < MIN_TAIL:
        ps, _ = bounds[-2]
        _, le = bounds[-1]
        bounds[-2] = (ps, le)
        bounds.pop()

    out = []
    for a, b in bounds:
        t_start = seg.cues[cue_of[a]].t_start
        t_end = seg.cues[cue_of[b]].t_end
        out.append((t_start, t_end, " ".join(words[a:b + 1]), b - a + 1))
    return out


def ingest(conn, *, item_id, kind, language, source_path, resolved_via, cues) -> dict:
    if not cues:
        raise ValueError(
            f"refusing to ingest 0 cues for item_id={item_id} ({source_path}): "
            "would delete the prior transcript and write an empty one"
        )
    registry = build_registry(cues)
    cues = split_embedded(cues, registry)  # expose two-speaker cues
    hits: dict[str, int] = {}
    for c in cues:
        if c.label in registry:
            hits[c.label] = hits.get(c.label, 0) + 1
    registry = {k: (v[0], v[1], hits.get(k, v[2])) for k, v in registry.items()}
    segments = build_segments(cues, registry)

    # idempotent: drop any prior transcript for this (item, kind, language)
    prev = conn.execute(
        "SELECT id FROM transcripts WHERE item_id=? AND kind=? AND language=?",
        (item_id, kind, language),
    ).fetchone()
    if prev:
        tid0 = prev[0]
        conn.execute(
            "DELETE FROM passages_fts WHERE rowid IN (SELECT id FROM passages WHERE transcript_id=?)",
            (tid0,),
        )
        for t in ("passages", "segments", "speaker_labels"):
            conn.execute(f"DELETE FROM {t} WHERE transcript_id=?", (tid0,))
        conn.execute("DELETE FROM transcripts WHERE id=?", (tid0,))

    now = datetime.now(timezone.utc).isoformat()
    duration = cues[-1].t_end if cues else 0.0
    tid = conn.execute(
        """INSERT INTO transcripts(item_id,kind,language,source_path,resolved_via,
             cue_count,segment_count,passage_count,word_count,duration_secs,parser_version,parsed_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (item_id, kind, language, source_path, resolved_via, len(cues), 0, 0, 0,
         duration, PARSER_VERSION, now),
    ).lastrowid
    # speaker_labels is the per-item label registry: it stores EVERY raw surface form a
    # transcript used (UNIQUE is on raw_label), so two forms of one speaker — "K:" and
    # "Krishnamurti:" — are intentionally two rows. Any distinct-speaker count must use
    # COUNT(DISTINCT speaker_code), never COUNT(*), so alias rows can't inflate it.
    for raw, (code, name, n) in registry.items():
        conn.execute(
            "INSERT INTO speaker_labels(transcript_id,raw_label,speaker_code,display_name,cue_hits) VALUES(?,?,?,?,?)",
            (tid, raw, code, name, n),
        )

    pseq = 0
    k_pass = 0
    total_words = 0
    prev_speaker = None
    prev_seq = None
    for sseq, seg in enumerate(segments):
        text = " ".join(c.rest for c in seg.cues).strip()
        wc = len(text.split())
        total_words += wc
        answers = prev_seq if (seg.speaker_code == "K" and prev_speaker == "Q") else None
        sid = conn.execute(
            """INSERT INTO segments(transcript_id,item_id,seq,speaker_code,raw_label,
                 t_start,t_end,text,word_count,answers_seq) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (tid, item_id, sseq, seg.speaker_code, seg.raw_label,
             seg.cues[0].t_start, seg.cues[-1].t_end, text, wc, answers),
        ).lastrowid
        for (t_start, t_end, ptext, pwc) in chunk_passages(seg):
            pid = conn.execute(
                """INSERT INTO passages(transcript_id,segment_id,item_id,seq,speaker_code,
                     t_start,t_end,text,word_count) VALUES(?,?,?,?,?,?,?,?,?)""",
                (tid, sid, item_id, pseq, seg.speaker_code, t_start, t_end, ptext, pwc),
            ).lastrowid
            if seg.speaker_code == "K":
                conn.execute("INSERT INTO passages_fts(rowid,text) VALUES(?,?)", (pid, ptext))
                k_pass += 1
            pseq += 1
        prev_speaker, prev_seq = seg.speaker_code, sseq

    conn.execute(
        "UPDATE transcripts SET segment_count=?, passage_count=?, word_count=? WHERE id=?",
        (len(segments), pseq, total_words, tid),
    )
    conn.commit()
    return {"transcript_id": tid, "segments": len(segments), "passages": pseq,
            "k_passages": k_pass, "speakers": sorted({s.speaker_code for s in segments}),
            "words": total_words, "registry": registry}


# ── on-disk resolution (batch mode) ───────────────────────────────────────────
def materialize(path: Path) -> bool:
    """Ensure an iCloud file is present locally; return True if real bytes are now
    available. brctl download is async, so poll briefly — but bail out immediately for
    a path that is neither on disk nor an iCloud placeholder (nothing to download), so
    a genuinely missing item doesn't burn the full ~15s poll budget on every one of
    resolve_vtt's three candidate paths (~45s of dead wait per missing item)."""
    if path.exists() and path.stat().st_size > 0:
        return True
    placeholder = path.with_name("." + path.name + ".icloud")
    if not path.exists() and not placeholder.exists():
        return False  # not downloaded and not evicted-in-cloud: nothing to wait for
    subprocess.run(["brctl", "download", str(path)], check=False)
    for _ in range(30):  # up to ~15s
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.5)
    return False


def resolve_vtt(code: str, future_path: str, root: Path) -> tuple[Path | None, str]:
    rel = future_path[len("library/"):] if future_path.startswith("library/") else future_path
    direct = root / "library" / rel
    if materialize(direct):
        return direct, "direct"
    # multi-part drift: DB has "BASE.N - title.en.vtt"; disk has combined "BASE.en.vtt"
    base = code.split(".")[0]
    d = direct.parent
    for cand in (d / f"{base}.en.vtt", d / f"{base}.en-GB.vtt"):
        if materialize(cand):
            return cand, "combined-multipart"
    hits = sorted(d.glob(f"{base}*.en*.vtt")) if d.exists() else []
    if hits:
        return hits[0], "combined-multipart"
    return None, "missing"


def read_vtt(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--vtt", type=Path, help="parse this file directly (standalone mode)")
    ap.add_argument("--item", help="item code (required with --vtt)")
    ap.add_argument("--kind", default="manual",
                    help="subtitle kind (standalone --vtt mode only; batch is manual-only)")
    ap.add_argument("--language", default="en",
                    help="language code (standalone --vtt mode only; batch uses en/en-GB)")
    ap.add_argument("--event-type", help="batch: only this event_type (e.g. T)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--media-root", type=Path, default=MEDIA_ROOT)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")  # make ON DELETE CASCADE real (SP-3)
    ensure_segment_schema(conn)

    if args.vtt:
        if not args.item:
            sys.exit("--item CODE required with --vtt")
        row = conn.execute(
            "SELECT id, corpus_include FROM items WHERE code=?", (args.item,)
        ).fetchone()
        if not row:
            sys.exit(f"item not in catalog: {args.item}")
        if not row[1]:
            print(f"WARN {args.item}: corpus_include=0 (scope-excluded item) — "
                  "ingesting anyway (explicit --vtt override)")
        cues = parse_cues(read_vtt(args.vtt))
        if not cues:
            sys.exit(f"0 cues parsed from {args.vtt} — refusing to overwrite "
                     "any existing transcript with an empty one")
        r = ingest(conn, item_id=row[0], kind=args.kind, language=args.language,
                   source_path=str(args.vtt), resolved_via="override", cues=cues)
        print(f"{args.item}: {len(cues)} cues -> {r['segments']} segments, "
              f"{r['passages']} passages, {r['words']} words")
        print("registry:", {k: v[0] for k, v in r["registry"].items()})
        return

    # batch mode
    q = """SELECT i.id, i.code, s.future_path, s.language, s.kind
           FROM items i
           JOIN item_subtitles s ON s.item_id=i.id
             AND s.kind='manual' AND s.status='downloaded' AND s.language IN ('en','en-GB')
           WHERE i.corpus_include = 1"""
    params: list = []
    if args.event_type:
        q += " AND i.event_type=?"
        params.append(args.event_type)
    q += " ORDER BY i.pdf_order"
    if args.limit:
        q += f" LIMIT {int(args.limit)}"
    rows = conn.execute(q, params).fetchall()
    done = skipped = empty = collapsed = 0
    for item_id, code, future_path, language, kind in rows:
        path, via = resolve_vtt(code, future_path, args.media_root)
        if path is None:
            print(f"  SKIP {code}: VTT not found ({future_path})")
            skipped += 1
            continue
        cues = parse_cues(read_vtt(path))
        if not cues:
            # 0 cues from a resolved file = iCloud-evict race or a non-VTT file.
            # Do NOT write an empty transcript; surface it for a re-run.
            print(f"  WARN {code}: 0 cues parsed from {path} (evicted/not-VTT?) — not written")
            empty += 1
            continue
        r = ingest(conn, item_id=item_id, kind=kind, language=language,
                   source_path=str(path), resolved_via=via, cues=cues)
        done += 1
        # collapse guard: a manual item that yields no K passages almost always means
        # the speaker labels failed to parse (e.g. an unseen label style) — surface it.
        flag = "  ⚠ 0 K-passages (check speaker labels)" if r["k_passages"] == 0 else ""
        if flag:
            collapsed += 1
        print(f"  {code}: {len(cues)} cues -> {r['segments']} seg, {r['passages']} pass ({via}){flag}")
    print(f"done={done} skipped={skipped} empty={empty} collapsed={collapsed}")


if __name__ == "__main__":
    main()
