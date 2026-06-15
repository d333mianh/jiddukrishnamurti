#!/usr/bin/env python3
"""Local whisper.cpp transcription backfill for items without manual EN subs.

For each item with downloaded audio and no downloaded subtitles (any kind):
materialize the m4a from iCloud, decode to 16 kHz mono WAV, run whisper-cli,
write <stem>.whisper.{vtt,json,txt} next to the media, record an
item_subtitles row (kind='whisper-large-v3'), then evict the audio again.

Idempotent and resumable: items that already have a downloaded whisper row
with the VTT present on disk are skipped, so the script can be stopped and
re-run at any time. Manual subs always take priority in the corpus pipeline
(filter by kind); a future cloud-STT pass supersedes these rows the same way.

Model/settings chosen by pilot eval 2026-06-11 (see STRATEGY.md): turbo beat
large-v3 on both test clips (5.05/6.69% vs 5.50/9.43% strong WER) and is 3x
faster; -mc 0 prevents repetition loops (16.1% WER without it); whisper's
initial prompt is ignored under -mc 0 and hurts with -mc 224, so no keyterms.

Usage:
  transcribe_whisper.py [--limit N] [--dry-run] [--model PATH] [--prompt-file PATH]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
ICLOUD = Path.home() / (
    "Library/Mobile Documents/com~apple~CloudDocs/00-cod3/jiddu-krishnamurti"
)
DEFAULT_MODEL = (
    Path.home()
    / "Library/Mobile Documents/com~apple~CloudDocs/ggml-large-v3-turbo.bin"
)
KIND = "whisper-large-v3-turbo"
TMP_WAV = Path("/tmp/whisper_backfill.wav")
STOP_FILE = ROOT / "catalog" / "logs" / "whisper_backfill.stop"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


def materialize(path: Path, expect_size: int, timeout_s: int = 900) -> bool:
    if not path.exists():
        placeholder = path.parent / f".{path.name}.icloud"
        if not placeholder.exists():
            return False
    subprocess.run(["brctl", "download", str(path)], check=False)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if path.exists():
            have = int(subprocess.check_output(["du", "-k", str(path)]).split()[0]) * 1024
            if have >= expect_size * 0.98:
                return True
        time.sleep(10)
    return False


def worklist(conn: sqlite3.Connection):
    return conn.execute(
        """SELECT i.id, i.code, i.event_type, i.duration_minutes, m.future_path, m.file_size
           FROM items i
           JOIN item_media m ON m.item_id = i.id AND m.media = 'audio'
                AND m.status = 'downloaded'
           LEFT JOIN item_subtitles s ON s.item_id = i.id AND s.status = 'downloaded'
           WHERE s.id IS NULL
           ORDER BY CASE WHEN i.event_type IN ('T','TS','TYP','TR','Q') THEN 0 ELSE 1 END,
                    i.pdf_order"""
    ).fetchall()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--prompt-file", type=Path, default=None,
                    help="optional initial prompt (off by default; ignored by -mc 0)")
    args = ap.parse_args()

    if not args.model.exists():
        sys.exit(f"model not found: {args.model}")
    prompt = ""
    if args.prompt_file and args.prompt_file.exists():
        prompt = args.prompt_file.read_text(encoding="utf-8").strip()

    conn = sqlite3.connect(DB_PATH, timeout=60)
    items = worklist(conn)
    if args.limit:
        items = items[: args.limit]
    total_min = sum(r[3] or 0 for r in items)
    log(f"worklist: {len(items)} items, {total_min/60:.0f} h (PDF minutes); "
        f"model={args.model.name}, prompt={'yes' if prompt else 'no'}")
    if args.dry_run:
        for r in items[:20]:
            log(f"  would do {r[1]} ({r[2]}, {r[3]} min)")
        return

    STOP_FILE.unlink(missing_ok=True)
    done = failed = 0
    t_start = time.time()
    for item_id, code, etype, minutes, rel_path, file_size in items:
        if STOP_FILE.exists():
            log(f"stop file found ({STOP_FILE}) — pausing after {done} items; "
                "re-run the script to resume")
            break
        audio = ICLOUD / rel_path
        out_base = audio.parent / (audio.stem + ".whisper")
        vtt = Path(str(out_base) + ".vtt")

        # already-done guard (covers re-runs after the DB row was written)
        row = conn.execute(
            "SELECT status FROM item_subtitles WHERE item_id=? AND kind=?",
            (item_id, KIND),
        ).fetchone()
        if row and row[0] == "downloaded" and vtt.exists():
            continue

        log(f"=== {code} ({etype}, {minutes} min)")
        if not materialize(audio, file_size or 0):
            log(f"  SKIP: could not materialize {audio.name}")
            failed += 1
            continue

        t0 = time.time()
        TMP_WAV.unlink(missing_ok=True)
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(audio), "-ar", "16000", "-ac", "1",
             "-c:a", "pcm_s16le", str(TMP_WAV)],
        )
        if r.returncode != 0:
            log("  SKIP: ffmpeg failed")
            failed += 1
            continue

        cmd = ["whisper-cli", "-m", str(args.model), "-f", str(TMP_WAV),
               "-l", "en", "-mc", "0", "-otxt", "-ovtt", "-oj",
               "-of", str(out_base), "-np"]
        if prompt:
            cmd += ["--prompt", prompt, "--carry-initial-prompt"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not vtt.exists():
            log(f"  FAIL: whisper-cli rc={r.returncode}: {r.stderr[-300:]}")
            failed += 1
            continue

        dt = time.time() - t0
        speed = (minutes * 60 / dt) if minutes else 0
        conn.execute(
            """INSERT INTO item_subtitles (item_id, language, kind, format, future_path,
                 file_size, status, downloaded_at)
               VALUES (?, 'en', ?, 'vtt', ?, ?, 'downloaded', ?)
               ON CONFLICT(item_id, language, kind) DO UPDATE SET
                 future_path=excluded.future_path, file_size=excluded.file_size,
                 status='downloaded', downloaded_at=excluded.downloaded_at""",
            (item_id, KIND, str(vtt.relative_to(ICLOUD)), vtt.stat().st_size,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        subprocess.run(["brctl", "evict", str(audio)], check=False,
                       capture_output=True)
        done += 1
        elapsed_h = (time.time() - t_start) / 3600
        log(f"  ok in {dt/60:.1f} min ({speed:.1f}x realtime) | "
            f"done {done}, failed {failed}, elapsed {elapsed_h:.1f} h")

    TMP_WAV.unlink(missing_ok=True)
    log(f"finished: {done} done, {failed} failed of {len(items)}")


if __name__ == "__main__":
    main()
