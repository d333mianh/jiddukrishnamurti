#!/usr/bin/env python3
"""Add section 11A: long-form recordings from the official YouTube channel
that appear in no KFT PDF (found by the 2026-06-12 @KFoundation scan).

Groups: The Ending of Time (K & Bohm 1980, 15), The Limits of Thought
(K & Bohm 1975, 12), the complete London 1962 season (15), and the
Santa Monica 1971 talks (4). Metadata: catalog/channel_recordings_2026.json.

The "not from PDF" mark is threefold: items.source_pdf =
'youtube_channel_scan_2026-06-12', items.notes explains the origin, and
item_links.source = 'kft_channel_scan' (PDF-derived links use
'kft_pdf_youtube').

Idempotent: safe to re-run, including after a build_catalog.py rebuild
(which only knows the PDFs and would otherwise drop these rows).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
META_PATH = ROOT / "catalog" / "channel_recordings_2026.json"
NOTES = ("Not in any KFT PDF; found via official @KFoundation channel scan "
         "2026-06-12")


def safe_title(title: str) -> str:
    t = re.sub(r'[<>:"/\\|?*]', "", title)
    return re.sub(r"\s+", " ", t).strip()[:100]


def main() -> None:
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    sec = meta["section"]
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)

    cur = conn.execute(
        """INSERT OR IGNORE INTO sections (number, letter, code, title, slug, sort_order)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sec["number"], sec["letter"], f"{sec['number']}{sec['letter']}",
         sec["title"], sec["slug"], sec["sort_order"]),
    )
    section_id = conn.execute(
        "SELECT id FROM sections WHERE slug = ?", (sec["slug"],)
    ).fetchone()[0]
    print(f"section {sec['slug']}: id={section_id} ({'created' if cur.rowcount else 'exists'})")

    entries = meta["entries"]
    by_series = {s["code"]: s for s in meta["series"]}
    for s in meta["series"]:
        eps = [e for e in entries if e["series_code"] == s["code"]]
        places = sorted({e["place"] for e in eps})
        years = sorted({e["year"] for e in eps})
        media = sorted({"video" if e["footage_type"] == "video_footage" else "audio"
                        for e in eps})
        conn.execute(
            """INSERT OR IGNORE INTO series (series_code, series_title, mega_group,
               pdf_order, episode_count, minutes_total, year_from, year_to,
               place_name, media_types)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (s["code"], s["title"], sec["mega_group"], s["base"], len(eps),
             sum(e["minutes"] for e in eps), years[0], years[-1],
             " / ".join(places), "+".join(media)),
        )

    added_items = added_links = 0
    for e in entries:
        s = by_series[e["series_code"]]
        order = s["base"] + e["sort"] - 1
        media_type = "video" if e["footage_type"] == "video_footage" else "audio"
        future_path = (f"library/{sec['slug']}/{s['base']:04d}-{s['code']}/"
                       f"{e['code']} - {safe_title(e['title'])}.m4a")
        cur = conn.execute(
            """INSERT OR IGNORE INTO items (code, section_id, title, media_type,
               duration_minutes, place_name, place_code, event_date, year, event_type,
               event_number, event_type_label, suffix, media_kind, summary, series_code,
               series_title, notes, future_path, mega_group, pdf_order, series_order,
               obsidian_path, source_pdf, updated_at, footage_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (e["code"], section_id, e["title"], media_type, e["minutes"],
             e["place"], e["place_code"], None, e["year"], e["event_type"],
             e["event_number"], e["event_type_label"], "", e["media_kind"], None,
             s["code"], s["title"], NOTES, future_path, sec["mega_group"],
             order, s["base"], f"11 - Channel recordings.md#{s['code']}",
             "youtube_channel_scan_2026-06-12", now, e["footage_type"]),
        )
        added_items += cur.rowcount
        item_id = conn.execute(
            "SELECT id FROM items WHERE code = ?", (e["code"],)
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT OR IGNORE INTO item_links (item_id, url, link_kind, source,
               video_id, remote_title, media_format, match_score, discovered_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (item_id, f"https://youtu.be/{e['video_id']}", "primary",
             "kft_channel_scan", e["video_id"], e["remote_title"],
             media_type, 1.0, now,
             "Manually verified: official channel upload; title and series "
             "numbering match; recording absent from all KFT PDFs"),
        )
        added_links += cur.rowcount

    conn.commit()
    n = conn.execute(
        "SELECT COUNT(*) FROM items WHERE section_id = ?", (section_id,)
    ).fetchone()[0]
    print(f"items added {added_items}, links added {added_links}; "
          f"section now holds {n} items")


if __name__ == "__main__":
    main()
