#!/usr/bin/env python3
"""Bundle the irreplaceable artifacts into a single checksummed archive.

Why this exists: the gold KFT transcripts and the generated corpus live only in
self-evicting iCloud, and `corpus/krishnamurti-corpus.db` is gitignored and
exists in exactly one copy. That risk has already fired once — on 2026-07-25,
111 manual VTTs recorded as `downloaded` were found **absent from disk**, and
the 29 of them that had been ingested survived only inside the corpus DB. (The
other 82 had no copy at all; this docstring used to say all 111 were ingested,
which was wrong — see the 2026-07-26 entries in STRATEGY.md.) All 111 were
re-downloaded on 2026-07-26, so a run today reports `corpus-only items: 0`. That
line is the live measure of how much text this archive is the last copy of.

What goes in, in priority order:

1. `corpus/krishnamurti-corpus.db` — expensive to rebuild, and the sole copy of
   whatever the `corpus-only items` line counts. Copied via the sqlite3 backup
   API, so the snapshot is consistent even if something is mid-write.
2. Manual `.en.vtt` files — the gold standard; re-downloadable only while KFT
   keeps them public.
3. `catalog/krishnamurti.db` + `concepts/concepts.jsonl` — small, tracked in
   git, included so a restore needs nothing but this archive.
4. Whisper outputs — regenerable, but ~682 h of compute. `--include-whisper`.

iCloud-evicted members are materialized first (`brctl download`, issued for
every file up front so they warm in parallel, then awaited). A file that never
materializes is recorded in the manifest as `unmaterialized` and the run exits
non-zero — but the archive is still written, because a partial backup beats
none.

The destination is deliberately a parameter with a non-iCloud default: writing
the backup back into iCloud would preserve the single point of failure this
script exists to remove. Point `--dest` at an external disk or a mounted remote
for a genuinely offsite copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DB = ROOT / "corpus" / "krishnamurti-corpus.db"
CATALOG_DB = ROOT / "catalog" / "krishnamurti.db"
CONCEPTS = ROOT / "concepts" / "concepts.jsonl"
DEFAULT_DEST = Path.home() / "Backups" / "jiddu-krishnamurti"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def is_icloud_item(path: Path) -> bool:
    return path.exists() or (path.parent / f".{path.name}.icloud").exists()


def local_bytes(path: Path) -> int:
    """Bytes actually resident on this Mac. An evicted iCloud file reports its
    full logical st_size but zero allocated blocks, so st_size cannot answer
    'is this really here' — st_blocks can."""
    try:
        return path.stat().st_blocks * 512
    except OSError:
        return 0


def is_materialized(path: Path) -> bool:
    if not path.exists():
        return False
    size = path.stat().st_size
    if size == 0:
        return True
    return local_bytes(path) >= size * 0.98


def prefetch(paths: list[Path]) -> None:
    """Ask iCloud for every file up front. brctl download returns immediately,
    so issuing all of them lets the downloads overlap instead of serializing at
    one round-trip per file."""
    for p in paths:
        if is_icloud_item(p) and not is_materialized(p):
            subprocess.run(["brctl", "download", str(p)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def await_materialization(paths: list[Path], timeout_s: int) -> list[Path]:
    pending = [p for p in paths if not is_materialized(p)]
    if not pending:
        return []
    log(f"materializing {len(pending)} evicted file(s) from iCloud …")
    deadline = time.time() + timeout_s
    while pending and time.time() < deadline:
        time.sleep(5)
        still = [p for p in pending if not is_materialized(p)]
        if len(still) != len(pending):
            log(f"  {len(paths) - len(still)}/{len(paths)} ready")
        pending = still
    return pending


def sidecar(archive: Path) -> Path:
    """The checksum file that sits beside `archive`.

    By string, never `with_suffix`: the archive name ends `.tar.zst`, and
    `with_suffix` replaces only the last suffix, so asking it for
    `.tar.zst.sha256` yields `…tar.tar.zst.sha256` — a name that no longer
    matches the archive it certifies, and that the pruning path below then
    fails to delete. This is the same misuse that collapsed 111 manual VTTs
    onto one filename; see `tests/test_subtitle_paths.py`."""
    return archive.parent / (archive.name + ".sha256")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_db(src: Path, dst: Path) -> None:
    """Consistent copy via the sqlite3 backup API — a raw file copy of a live
    DB can capture a torn page or miss the WAL."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def collect_members(include_whisper: bool) -> list[Path]:
    library = ROOT / "library"
    members: list[Path] = []
    if library.exists():
        members += sorted(library.rglob("*.en.vtt"))
        if include_whisper:
            members += sorted(library.rglob("*.whisper.*"))
    return members


def corpus_only_items() -> list[str]:
    """Item codes whose manual VTT is gone from disk but whose text survives in
    the corpus DB — the rows that make this backup non-optional."""
    if not (CORPUS_DB.exists() and CATALOG_DB.exists()):
        return []
    cat = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro", uri=True)
    cor = sqlite3.connect(f"file:{CORPUS_DB}?mode=ro", uri=True)
    try:
        gone = {
            code
            for code, rel in cat.execute(
                """SELECT i.code, s.future_path FROM item_subtitles s
                   JOIN items i ON i.id = s.item_id
                   WHERE s.kind = 'manual' AND s.status = 'downloaded'"""
            )
            if not (ROOT / rel).exists()
        }
        ingested = {
            r[0] for r in cor.execute(
                "SELECT item_code FROM transcripts WHERE kind = 'manual'")
        }
    finally:
        cor.close()
        cat.close()
    return sorted(gone & ingested)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST,
                    help=f"archive directory (default: {DEFAULT_DEST})")
    ap.add_argument("--include-whisper", action="store_true",
                    help="also archive the regenerable whisper outputs")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="seconds to wait for iCloud materialization (default 1800)")
    ap.add_argument("--keep", type=int, default=3,
                    help="how many previous archives to retain (default 3)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not CORPUS_DB.exists():
        print(f"error: {CORPUS_DB} not found", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    members = collect_members(args.include_whisper)
    orphans = corpus_only_items()

    log(f"corpus DB      : {CORPUS_DB.stat().st_size / 1048576:.1f} MB")
    log(f"transcript files: {len(members)}")
    log(f"corpus-only items: {len(orphans)} (no VTT on disk; DB is the only copy)")

    if args.dry_run:
        total = sum(p.stat().st_size for p in members) + CORPUS_DB.stat().st_size
        log(f"dry run — would archive ~{total / 1048576:.1f} MB "
            f"to {args.dest}/krishnamurti-backup-{stamp}.tar.zst")
        return 0

    prefetch(members)
    unmaterialized = await_materialization(members, args.timeout)
    if unmaterialized:
        log(f"WARNING: {len(unmaterialized)} file(s) never materialized; "
            f"archiving without them")

    args.dest.mkdir(parents=True, exist_ok=True)
    archive = args.dest / f"krishnamurti-backup-{stamp}.tar.zst"
    manifest: dict[str, object] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(ROOT),
        "include_whisper": args.include_whisper,
        "corpus_only_items": orphans,
        "unmaterialized": [str(p.relative_to(ROOT)) for p in unmaterialized],
        "files": {},
    }

    with tempfile.TemporaryDirectory(prefix="kbackup-") as tmp:
        stage = Path(tmp) / "krishnamurti-backup"
        stage.mkdir(parents=True)

        log("snapshotting corpus DB …")
        snapshot_db(CORPUS_DB, stage / "corpus" / CORPUS_DB.name)
        if CATALOG_DB.exists():
            log("snapshotting catalog DB …")
            snapshot_db(CATALOG_DB, stage / "catalog" / CATALOG_DB.name)
        if CONCEPTS.exists():
            (stage / "concepts").mkdir(parents=True, exist_ok=True)
            shutil.copy2(CONCEPTS, stage / "concepts" / CONCEPTS.name)

        skipped = set(unmaterialized)
        copied = 0
        for src in members:
            if src in skipped:
                continue
            rel = src.relative_to(ROOT)
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
            if copied % 200 == 0:
                log(f"  staged {copied}/{len(members) - len(skipped)}")

        files = manifest["files"]
        assert isinstance(files, dict)
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                files[str(path.relative_to(stage))] = {
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                }
        (stage / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        log(f"compressing → {archive.name} …")
        proc = subprocess.run(
            ["tar", "--use-compress-program=zstd -12 -T0", "-cf", str(archive),
             "-C", str(stage.parent), stage.name],
            check=False)
        if proc.returncode != 0:
            print("error: tar failed", file=sys.stderr)
            return 1

    log("verifying archive …")
    # Two checks: `zstd -t` proves the compressed frame decodes and its checksum
    # matches; `tar -tf` proves the tar inside is readable end to end. bsdtar
    # detects zstd on its own — passing --use-compress-program here makes tar
    # stop reading early and zstd die on a broken pipe, failing a good archive.
    if subprocess.run(["zstd", "-t", str(archive)], check=False,
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode != 0:
        print("error: archive failed zstd integrity check", file=sys.stderr)
        return 1
    verify = subprocess.run(["tar", "-tf", str(archive)],
                            check=False, stdout=subprocess.PIPE)
    if verify.returncode != 0:
        print("error: archive failed verification", file=sys.stderr)
        return 1
    entries = len([ln for ln in verify.stdout.decode().splitlines() if ln.strip()])

    digest = sha256(archive)
    sidecar(archive).write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    log(f"wrote {archive} ({archive.stat().st_size / 1048576:.1f} MB, "
        f"{entries} entries)")
    log(f"sha256 {digest}")

    olds = sorted(args.dest.glob("krishnamurti-backup-*.tar.zst"))[:-args.keep] \
        if args.keep > 0 else []
    for old in olds:
        log(f"pruning {old.name}")
        old.unlink()
        sidecar(old).unlink(missing_ok=True)

    if unmaterialized:
        print(f"\n{len(unmaterialized)} file(s) could not be materialized from "
              f"iCloud and are NOT in this archive:", file=sys.stderr)
        for p in unmaterialized[:20]:
            print(f"  {p.relative_to(ROOT)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
