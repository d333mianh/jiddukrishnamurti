#!/usr/bin/env python3
"""Add the Education Directory 2026 items (section 10A) to the catalog.

The Education Directory PDF is almost entirely a thematic re-listing of items
already cataloged from the Full-Length Directory; the only new recordings are
the 11 GSBR74DT items (Gstaad/Brockwood 1974 teacher discussions). Their
metadata and manually verified YouTube links live in
catalog/education_directory_2026.json.

Idempotent: safe to re-run, including after a build_catalog.py rebuild
(which only knows the Full-Length PDF and would otherwise drop these rows).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
META_PATH = ROOT / "catalog" / "education_directory_2026.json"


def safe_title(title: str) -> str:
    t = re.sub(r'[<>:"/\\|?*]', "", title)
    return re.sub(r"\s+", " ", t).strip()[:100]


def main() -> None:
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    sec = meta["section"]
    ser = meta["series"]
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

    base_order = 1484  # continues after the Full-Length Directory's max pdf_order 1483
    entries = meta["entries"]
    places = sorted({e["place"] for e in entries})
    conn.execute(
        """INSERT OR IGNORE INTO series (series_code, series_title, mega_group, pdf_order,
           episode_count, minutes_total, year_from, year_to, place_name, media_types)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ser["code"], ser["title"], sec["mega_group"], base_order, len(entries),
         sum(e["minutes"] for e in entries), 1974, 1974, " / ".join(places), "audio"),
    )

    added_items = added_links = 0
    for i, e in enumerate(entries):
        future_path = (f"library/{sec['slug']}/{base_order:04d}-{ser['code']}/"
                       f"{e['code']} - {safe_title(e['title'])}.m4a")
        cur = conn.execute(
            """INSERT OR IGNORE INTO items (code, section_id, title, media_type,
               duration_minutes, place_name, place_code, event_date, year, event_type,
               event_number, event_type_label, suffix, media_kind, summary, series_code,
               series_title, notes, future_path, mega_group, pdf_order, series_order,
               obsidian_path, source_pdf, updated_at, footage_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (e["code"], section_id, e["title"], "audio", e["minutes"], e["place"],
             "GSBR", e["date"], 1974, "DT", e["code"].split("DT")[1],
             "Discussion with Teachers", "", "school", e["summary"], ser["code"],
             ser["title"], "From Education Directory 2026 (only new items in that PDF)",
             future_path, sec["mega_group"], base_order + i, base_order,
             f"10 - Education directory.md#{ser['code']}", meta["source_pdf"], now,
             "audio_only"),
        )
        added_items += cur.rowcount
        item_id = conn.execute(
            "SELECT id FROM items WHERE code = ?", (e["code"],)
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT OR IGNORE INTO item_links (item_id, url, link_kind, source,
               video_id, remote_title, media_format, match_score, discovered_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (item_id, f"https://youtu.be/{e['video_id']}", "primary", "kft_pdf_youtube",
             e["video_id"], e["remote_title"], "audio", 1.0, now,
             "Manually verified: Education Directory 2026 PDF hyperlink; "
             "remote title and duration match the PDF entry"),
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
