#!/usr/bin/env python3
"""
Build Krishnamurti recording catalog from KFT Full-Length Directory PDF.

Outputs:
  catalog/krishnamurti.db       - SQLite (canonical)
  catalog/exports/catalog.csv   - flat export
  catalog/exports/catalog.xlsx  - Excel workbook
  catalog/exports/sections.csv  - section index
  obsidian/                     - Series-grouped vault (9 notes: index + 8 mega-groups)
  catalog/exports/catalog-series.csv
  catalog/exports/catalog-compact.csv
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from footage_schema import footage_type_from_media_type  # noqa: E402
from media_schema import ITEM_MEDIA_DDL  # noqa: E402

PDF_DEFAULT = ROOT / "Krishnamurti-Foundation-Trust-–-Full-Length-Directory-2026.pdf"
PLACES_FILE = Path(__file__).resolve().parent / "places.json"
CATALOG_DIR = ROOT / "catalog"
EXPORTS_DIR = CATALOG_DIR / "exports"
OBSIDIAN_DIR = ROOT / "obsidian"
DB_PATH = CATALOG_DIR / "krishnamurti.db"

# PDF section.number → compact Obsidian / library mega-group
MEGA_GROUPS: list[dict] = [
    {
        "id": "01",
        "title": "Public meetings",
        "filename": "01 - Public meetings.md",
        "section_numbers": {1},
        "pdf_sections": "1A–1E (England, India, USA, Switzerland, Misc.)",
    },
    {
        "id": "02",
        "title": "Young people",
        "filename": "02 - Young people.md",
        "section_numbers": {2},
        "pdf_sections": "2A–2B",
    },
    {
        "id": "03",
        "title": "Small group discussions",
        "filename": "03 - Small group discussions.md",
        "section_numbers": {3},
        "pdf_sections": "3A–3B",
    },
    {
        "id": "04",
        "title": "Conversations",
        "filename": "04 - Conversations.md",
        "section_numbers": {4},
        "pdf_sections": "4A–4D",
    },
    {
        "id": "05",
        "title": "Seminars",
        "filename": "05 - Seminars.md",
        "section_numbers": {5},
        "pdf_sections": "5A–5B",
    },
    {
        "id": "06",
        "title": "K School discussions",
        "filename": "06 - K School discussions.md",
        "section_numbers": {6},
        "pdf_sections": "6A–6C",
    },
    {
        "id": "08",
        "title": "Excerpts",
        "filename": "08 - Excerpts.md",
        "section_numbers": {8},
        "pdf_sections": "8A",
    },
    {
        "id": "09",
        "title": "Films and documentaries",
        "filename": "09 - Films and documentaries.md",
        "section_numbers": {9},
        "pdf_sections": "9A",
    },
    {
        "id": "10",
        "title": "Education directory",
        "filename": "10 - Education directory.md",
        "section_numbers": {10},
        "pdf_sections": "10A (items unique to the Education Directory 2026)",
    },
    {
        "id": "11",
        "title": "Channel recordings",
        "filename": "11 - Channel recordings.md",
        "section_numbers": {11},
        "pdf_sections": "11A (official YouTube channel recordings absent from all KFT PDFs)",
    },
]

_SECTION_NUMBER_TO_MEGA = {
    n: g["id"] for g in MEGA_GROUPS for n in g["section_numbers"]
}

EVENT_TYPES = {
    "T": "Public Talk",
    "D": "Public Discussion",
    "Q": "Question & Answer Meeting",
    "DS": "Discussion with Students",
    "DSG": "Discussion with Small Group",
    "DSS": "Discussion with Staff and Students",
    "DT": "Discussion with Teachers",
    "DYP": "Discussion with Young People",
    "TS": "Talk to Students",
    "C": "Conversation",
    "I": "Interview",
    "F": "Film",
    "EBM": "Excerpt (compiled series)",
    "FRR": "Film series episode",
    "FCLW": "Film documentary",
    "FPL": "Film",
    "FOE": "Film on education",
    "FOG": "Film",
    "FQA": "Film",
    "FCC": "Film documentary",
    "IRF": "Film interview",
    "FSM": "Film documentary",
    "FOF": "Film",
    "HF": "Historical film",
    "FTPL": "Film",
    "CPJ": "Conversation",
    "CA": "Conversation",
    "CTM": "Conversation",
    "S": "Seminar",
}

FOOTER_RE = re.compile(
    r"^\d+\s*$|^Click here to return|^Copyright ©|^\f?$", re.I
)
SECTION_RE = re.compile(r"^(\d+)\s+([A-Z])\s+-\s+(.+?)\s*$")
TITLE_RE = re.compile(
    r"^J\.\s+Krishnamurti\s+"
    r"([A-Z]{2,3}[\d&][A-Z0-9.&]*(?:-[A-Z0-9]+)?)\s+"
    r"(.+?)\s*$"
)
MEDIA_RE = re.compile(
    r"^(Audio|Video)\s+-\s+(\d+)\s+minutes?\s+-\s+(.+?)\s+-\s+"
    r"(\d{1,2}\s+\w+\s+\d{4})$"
)
MEDIA_SHORT_DATE_RE = re.compile(
    r"^(Audio|Video)\s+-\s+(\d+)\s+minutes?\s+-\s+(\d{1,2}\s+\w+\s+\d{4})$"
)
MEDIA_DURATION_ONLY_RE = re.compile(
    r"^(Audio|Video)\s+-\s+(\d+)\s+minutes?$"
)
PLACE_DATE_RE = re.compile(
    r"^(.+?)\s+-\s+(\d{1,2}\s+\w+\s+\d{4})$"
)
SERIES_RE = re.compile(
    r"^Series:\s+J\.\s+Krishnamurti\s+([A-Z0-9.&-]+)\s+(.+?)\s*$"
)
CODE_PARSE_RE = re.compile(
    r"^([A-Z]{2,3})"  # place
    r"(\d{2,4})"  # year
    r"([A-Z][A-Z0-9.]*)"  # type + number
    r"(?:-([A-Z0-9]+))?$"  # optional suffix
)


@dataclass
class Section:
    number: int
    letter: str
    title: str
    code: str
    slug: str
    sort_order: int


@dataclass
class Item:
    code: str
    title: str
    section: Section
    media_type: str | None = None
    duration_minutes: int | None = None
    place_name: str | None = None
    event_date: str | None = None
    summary: str = ""
    series_code: str | None = None
    series_title: str | None = None
    notes: str = ""
    place_code: str | None = None
    year: int | None = None
    event_type: str | None = None
    event_number: str | None = None
    suffix: str | None = None
    event_type_label: str | None = None
    media_kind: str = "recording"
    future_path: str = ""
    obsidian_path: str = ""
    pdf_order: int = 0
    series_order: int | None = None


def load_places() -> dict[str, str]:
    with open(PLACES_FILE, encoding="utf-8") as f:
        return json.load(f)


def pdf_to_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(text: str, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:max_len] or "untitled"


def section_slug(number: int, letter: str, title: str) -> str:
    return f"{number}{letter}-{slugify(title, 60)}"


def parse_code(raw_code: str, places: dict[str, str]) -> dict:
    """Parse KFT code into components; handles variants like MA8182, KHF1&2."""
    suffix = None
    base = raw_code
    if "-" in raw_code and not raw_code.endswith("&2"):
        parts = raw_code.split("-", 1)
        base, suffix = parts[0], parts[1]

    place_code = None
    year = None
    event_type = None
    event_number = None

    m = CODE_PARSE_RE.match(base)
    if m:
        place_code, year_s, rest, _ = m.group(1), m.group(2), m.group(3), m.group(4)
        year = int(year_s) if len(year_s) == 4 else int(year_s)
        if len(year_s) == 2:
            year = 1900 + year if year > 30 else 2000 + year

        # Split type letters from trailing digits
        em = re.match(r"^([A-Z]+)(\d+.*)$", rest)
        if em:
            event_type, event_number = em.group(1), em.group(2)
        else:
            event_type = rest
            event_number = None
    else:
        # Films / special: OM24F, KHF1&2, LAT35HF
        em = re.match(r"^([A-Z]{2,3})(\d{0,4})([A-Z].*)$", base)
        if em:
            place_code, year_s, rest = em.group(1), em.group(2), em.group(3)
            if year_s:
                year = int(year_s)
                if year < 100:
                    year = 1900 + year if year > 30 else 2000 + year
            event_type = rest.rstrip("0123456789&")
            event_number = re.sub(r"^[A-Z]+", "", rest) or None

    if suffix:
        suffix = suffix

    event_type_label = None
    if event_type:
        for key in sorted(EVENT_TYPES, key=len, reverse=True):
            if event_type.startswith(key):
                event_type_label = EVENT_TYPES[key]
                break
        if not event_type_label:
            event_type_label = event_type

    place_name = places.get(place_code or "", place_code)

    media_kind = infer_media_kind(event_type, raw_code)

    return {
        "place_code": place_code,
        "year": year,
        "event_type": event_type,
        "event_number": event_number,
        "suffix": suffix,
        "event_type_label": event_type_label,
        "place_name_catalog": place_name,
        "media_kind": media_kind,
    }


def infer_media_kind(event_type: str | None, code: str) -> str:
    if not event_type:
        if code.endswith("F") or "F" in code:
            return "film"
        return "recording"
    if event_type.startswith("I") or "IM" in (event_type or ""):
        return "interview"
    if event_type.startswith("F") or event_type in ("EBM", "FRR", "HF", "FTPL"):
        return "film"
    if event_type.startswith("EBM"):
        return "excerpt"
    if event_type.startswith("C") or event_type in ("CPJ", "CA", "CTM"):
        return "conversation"
    if event_type in ("DS", "DSG", "DSS", "DT", "DYP", "TS"):
        return "school"
    if event_type == "S":
        return "seminar"
    if event_type == "T":
        return "talk"
    if event_type == "D":
        return "discussion"
    if event_type == "Q":
        return "qa"
    return "recording"


def find_catalog_body(text: str) -> str:
    marker = "1 A - Public Meetings (England)"
    first = text.find(marker)
    if first < 0:
        raise ValueError("Catalog body not found in PDF text")
    # Skip TOC: detail body starts at section header followed by first entry
    second = text.find(
        f"{marker}\nJ. Krishnamurti LO61T1",
        first + 1,
    )
    if second >= 0:
        return text[second:]
    # Fallback: first section with media line nearby
    idx = text.find("J. Krishnamurti LO61T1 What is the mind?\nAudio -")
    if idx >= 0:
        sec = text.rfind(marker, 0, idx)
        return text[sec:] if sec >= 0 else text[first:]
    return text[first:]


def parse_sections_and_items(body: str, places: dict[str, str]) -> tuple[list[Section], list[Item]]:
    lines = body.splitlines()
    sections: list[Section] = []
    items: list[Item] = []
    current_section: Section | None = None
    sort_section = 0
    pdf_order = 0

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line or FOOTER_RE.match(line):
            continue

        sm = SECTION_RE.match(line)
        if sm and "..." not in line:
            sort_section += 1
            num, letter, title = int(sm.group(1)), sm.group(2), sm.group(3).strip()
            code = f"{num}{letter}"
            current_section = Section(
                number=num,
                letter=letter,
                title=title,
                code=code,
                slug=section_slug(num, letter, title),
                sort_order=sort_section,
            )
            sections.append(current_section)
            continue

        if not line.startswith("J. Krishnamurti "):
            continue

        # Accumulate wrapped title lines until media/summary/series
        title_lines = [line]
        while i < len(lines):
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt.startswith("J. Krishnamurti ")
                or MEDIA_RE.match(nxt)
                or MEDIA_SHORT_DATE_RE.match(nxt)
                or MEDIA_DURATION_ONLY_RE.match(nxt)
                or re.match(r"^(Audio|Video)\s+-\s+\d+\s+minutes?\s+-", nxt)
                or nxt == "Summary"
                or SECTION_RE.match(nxt)
                or FOOTER_RE.match(nxt)
            ):
                break
            if "..." in nxt and re.search(r"\.{5,}\s*\d+\s*$", nxt):
                break
            title_lines.append(nxt)
            i += 1

        full_title_line = " ".join(title_lines)
        # Some PDF lines merge title and media (e.g. "...1928 Video - 1 minute...")
        inline_media_text = None
        media_inline = re.search(
            r"\s+(Audio|Video)\s+-\s+\d+\s+minutes?\s+-\s+", full_title_line
        )
        if media_inline:
            inline_media_text = full_title_line[media_inline.start() + 1 :]
            full_title_line = full_title_line[: media_inline.start()]

        tm = TITLE_RE.match(full_title_line)
        if not tm or not current_section:
            continue

        raw_code, title = tm.group(1), tm.group(2).strip()
        title = re.sub(r"\.{3,}.*$", "", title).strip()

        media_type = None
        duration = None
        place_name = None
        event_date = None
        summary_parts: list[str] = []
        series_code = None
        series_title = None
        notes_parts: list[str] = []

        if inline_media_text:
            mm = MEDIA_RE.match(inline_media_text.strip()) or MEDIA_SHORT_DATE_RE.match(
                inline_media_text.strip()
            )
            if mm:
                media_type = mm.group(1).lower()
                duration = int(mm.group(2))
                if mm.lastindex >= 4 and mm.group(4):
                    place_name = mm.group(3).strip()
                    event_date = mm.group(4).strip()
                else:
                    event_date = mm.group(3).strip()

        if media_type is None and i < len(lines):
            nxt = lines[i].strip()
            mm = MEDIA_RE.match(nxt) or MEDIA_SHORT_DATE_RE.match(nxt)
            if mm:
                i += 1
                media_type = mm.group(1).lower()
                duration = int(mm.group(2))
                if mm.lastindex >= 4 and mm.group(4):
                    place_name = mm.group(3).strip()
                    event_date = mm.group(4).strip()
                else:
                    event_date = mm.group(3).strip()
            else:
                dm = MEDIA_DURATION_ONLY_RE.match(nxt)
                if dm and i + 1 < len(lines):
                    pd = PLACE_DATE_RE.match(lines[i + 1].strip())
                    if pd:
                        i += 2
                        media_type = dm.group(1).lower()
                        duration = int(dm.group(2))
                        place_name = pd.group(1).strip()
                        event_date = pd.group(2).strip()

        # Parse block until next entry
        while i < len(lines):
            nxt = lines[i].strip()
            if nxt.startswith("J. Krishnamurti ") or SECTION_RE.match(nxt):
                break
            if FOOTER_RE.match(nxt):
                i += 1
                continue
            i += 1

            if nxt == "Summary":
                continue
            ser = SERIES_RE.match(nxt)
            if ser:
                series_code, series_title = ser.group(1), ser.group(2)
                continue
            if nxt.startswith("Note:"):
                notes_parts.append(nxt)
                continue
            if nxt.startswith("Series:"):
                continue
            if re.match(r"^Q:\s", nxt) or len(nxt) > 20:
                summary_parts.append(nxt)

        parsed = parse_code(raw_code, places)
        if place_name is None:
            place_name = parsed.get("place_name_catalog")

        ext = "mp4" if media_type == "video" else "m4a" if media_type == "audio" else "bin"
        safe_title = re.sub(r'[<>:"/\\|?*]', "", title)
        safe_title = re.sub(r"\s+", " ", safe_title).strip()[:100]
        filename = f"{raw_code} - {safe_title}.{ext}"
        if series_code and series_code.strip():
            future_path = f"library/{current_section.slug}/{series_code}/{filename}"
        else:
            future_path = f"library/{current_section.slug}/{filename}"

        item = Item(
            code=raw_code,
            title=title,
            section=current_section,
            media_type=media_type,
            duration_minutes=duration,
            place_name=place_name,
            event_date=event_date,
            summary="\n\n".join(summary_parts).strip(),
            series_code=series_code,
            series_title=series_title,
            notes="\n".join(notes_parts).strip(),
            place_code=parsed.get("place_code"),
            year=parsed.get("year"),
            event_type=parsed.get("event_type"),
            event_number=parsed.get("event_number"),
            suffix=parsed.get("suffix"),
            event_type_label=parsed.get("event_type_label"),
            media_kind=parsed.get("media_kind", "recording"),
            future_path=future_path,
            pdf_order=pdf_order,
        )
        pdf_order += 1
        items.append(item)

    return sections, items


def dedupe_items(items: list[Item]) -> list[Item]:
    """Keep best record per code; preserve earliest PDF position for ordering."""
    by_code: dict[str, Item] = {}
    order_by_code: dict[str, int] = {}
    for item in items:
        prev = by_code.get(item.code)
        if prev is None:
            by_code[item.code] = item
            order_by_code[item.code] = item.pdf_order
            continue
        order_by_code[item.code] = min(order_by_code[item.code], item.pdf_order)
        if item.media_type and not prev.media_type:
            item.pdf_order = order_by_code[item.code]
            by_code[item.code] = item
        elif item.duration_minutes and not prev.duration_minutes:
            item.pdf_order = order_by_code[item.code]
            by_code[item.code] = item
        else:
            prev.pdf_order = order_by_code[item.code]
    for code, item in by_code.items():
        item.pdf_order = order_by_code[code]
    return sorted(by_code.values(), key=lambda x: x.pdf_order)


def assign_series_order(items: list[Item]) -> None:
    """Set series_order from first PDF appearance of each series."""
    series_first: dict[str, int] = {}
    for item in sorted(items, key=lambda x: x.pdf_order):
        sc = (item.series_code or "").strip()
        if sc and sc not in series_first:
            series_first[sc] = item.pdf_order
    for item in items:
        sc = (item.series_code or "").strip()
        item.series_order = series_first.get(sc) if sc else None


def apply_series_folder_paths(items: list[Item]) -> None:
    """Prefix series folders with PDF order (e.g. 0000-LO61T1-12) for Finder sort."""
    from download_series import ordered_series_future_path

    for item in items:
        sc = (item.series_code or "").strip()
        if not sc:
            continue
        item.future_path = ordered_series_future_path(
            item.future_path,
            series_code=sc,
            series_order=item.series_order,
        )


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS catalog_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            pdf_sha256 TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            section_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER NOT NULL,
            letter TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            section_id INTEGER NOT NULL REFERENCES sections(id),
            title TEXT NOT NULL,
            media_type TEXT,
            footage_type TEXT,
            duration_minutes INTEGER,
            place_name TEXT,
            place_code TEXT,
            event_date TEXT,
            year INTEGER,
            event_type TEXT,
            event_number TEXT,
            event_type_label TEXT,
            suffix TEXT,
            media_kind TEXT NOT NULL,
            summary TEXT,
            series_code TEXT,
            series_title TEXT,
            notes TEXT,
            future_path TEXT NOT NULL,
            mega_group TEXT NOT NULL,
            pdf_order INTEGER NOT NULL,
            series_order INTEGER,
            obsidian_path TEXT NOT NULL,
            source_pdf TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (section_id) REFERENCES sections(id)
        );

        CREATE TABLE IF NOT EXISTS series (
            series_code TEXT NOT NULL,
            series_title TEXT,
            mega_group TEXT NOT NULL,
            pdf_order INTEGER NOT NULL,
            episode_count INTEGER NOT NULL,
            minutes_total INTEGER,
            year_from INTEGER,
            year_to INTEGER,
            place_name TEXT,
            media_types TEXT,
            PRIMARY KEY (series_code, mega_group)
        );

        CREATE INDEX IF NOT EXISTS idx_items_footage_type ON items(footage_type);
        CREATE INDEX IF NOT EXISTS idx_items_section ON items(section_id);
        CREATE INDEX IF NOT EXISTS idx_items_year ON items(year);
        CREATE INDEX IF NOT EXISTS idx_items_place ON items(place_code);
        CREATE INDEX IF NOT EXISTS idx_items_kind ON items(media_kind);
        CREATE INDEX IF NOT EXISTS idx_items_mega ON items(mega_group);
        CREATE INDEX IF NOT EXISTS idx_items_pdf_order ON items(pdf_order);
        CREATE INDEX IF NOT EXISTS idx_items_series_order ON items(series_order);
        CREATE INDEX IF NOT EXISTS idx_series_pdf_order ON series(pdf_order);

        -- Phase 2: streaming links (populated by scripts/discover_links.py)
        CREATE TABLE IF NOT EXISTS item_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            url TEXT NOT NULL,
            link_kind TEXT NOT NULL DEFAULT 'primary',
            source TEXT,
            video_id TEXT,
            remote_title TEXT,
            media_format TEXT,
            match_score REAL,
            discovered_at TEXT,
            notes TEXT,
            UNIQUE(item_id, url)
        );

        CREATE TABLE IF NOT EXISTS item_subtitles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            language TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'manual',
            format TEXT NOT NULL DEFAULT 'vtt',
            future_path TEXT NOT NULL,
            file_size INTEGER,
            status TEXT NOT NULL,
            error_message TEXT,
            probed_at TEXT,
            downloaded_at TEXT,
            UNIQUE(item_id, language, kind)
        );
        CREATE INDEX IF NOT EXISTS idx_item_subtitles_item ON item_subtitles(item_id);
        CREATE INDEX IF NOT EXISTS idx_item_subtitles_status ON item_subtitles(status);
        """
    )
    # item_media (download tracking) shares its DDL with the download scripts.
    conn.executescript(ITEM_MEDIA_DDL)


# Tables populated by phase-2 scripts (discover_links.py, download_*.py).
# A rebuild drops the DB, so their rows are carried across keyed by item code.
PHASE2_TABLES = ("item_links", "item_subtitles", "item_media")


def snapshot_phase2_tables(db_path: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    """Read phase-2 rows from the existing DB as (item code, *columns)."""
    snapshot: dict[str, tuple[list[str], list[tuple]]] = {}
    if not db_path.exists():
        return snapshot
    conn = sqlite3.connect(db_path)
    try:
        existing = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "items" not in existing:
            return snapshot
        for table in PHASE2_TABLES:
            if table not in existing:
                continue
            cols = [
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})")
                if row[1] not in ("id", "item_id")
            ]
            col_list = ", ".join(f"t.{c}" for c in cols)
            rows = conn.execute(
                f"SELECT i.code, {col_list} FROM {table} t JOIN items i ON i.id = t.item_id"
            ).fetchall()
            if rows:
                snapshot[table] = (cols, rows)
    finally:
        conn.close()
    return snapshot


def restore_phase2_tables(
    conn: sqlite3.Connection,
    snapshot: dict[str, tuple[list[str], list[tuple]]],
) -> None:
    """Re-insert snapshot rows against fresh item ids; orphaned codes are dropped."""
    if not snapshot:
        return
    code_to_id = {row[1]: row[0] for row in conn.execute("SELECT id, code FROM items")}
    for table, (cols, rows) in snapshot.items():
        table_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        keep = [c for c in cols if c in table_cols]
        col_list = ", ".join(keep)
        placeholders = ", ".join("?" for _ in keep)
        restored = orphaned = 0
        for code, *values in rows:
            item_id = code_to_id.get(code)
            if item_id is None:
                orphaned += 1
                continue
            by_col = dict(zip(cols, values))
            conn.execute(
                f"INSERT OR IGNORE INTO {table} (item_id, {col_list}) VALUES (?, {placeholders})",
                (item_id, *(by_col[c] for c in keep)),
            )
            restored += 1
        msg = f"  Preserved {table}: {restored} rows"
        if orphaned:
            msg += f" ({orphaned} rows dropped: item code no longer in PDF)"
        print(msg)


def save_db(
    sections: list[Section],
    items: list[Item],
    pdf_path: Path,
    pdf_hash: str,
) -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    phase2 = snapshot_phase2_tables(DB_PATH)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    now = datetime.now(timezone.utc).isoformat()

    for s in sections:
        conn.execute(
            """
            INSERT INTO sections (number, letter, code, title, slug, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (s.number, s.letter, s.code, s.title, s.slug, s.sort_order),
        )

    section_ids = {
        row[1]: row[0]
        for row in conn.execute("SELECT id, code FROM sections").fetchall()
    }

    mega_filename = {g["id"]: g["filename"] for g in MEGA_GROUPS}

    for item in items:
        mega_id = _SECTION_NUMBER_TO_MEGA[item.section.number]
        base_note = mega_filename[mega_id]
        if item.series_code and item.series_code.strip():
            item.obsidian_path = f"{base_note}#{item.series_code}"
        else:
            item.obsidian_path = f"{base_note}#standalone"

        conn.execute(
            """
            INSERT INTO items (
                code, section_id, title, media_type, footage_type, duration_minutes,
                place_name, place_code, event_date, year,
                event_type, event_number, event_type_label, suffix,
                media_kind, summary, series_code, series_title, notes,
                future_path, mega_group, pdf_order, series_order,
                obsidian_path, source_pdf, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                item.code,
                section_ids[item.section.code],
                item.title,
                item.media_type,
                footage_type_from_media_type(item.media_type),
                item.duration_minutes,
                item.place_name,
                item.place_code,
                item.event_date,
                item.year,
                item.event_type,
                item.event_number,
                item.event_type_label,
                item.suffix,
                item.media_kind,
                item.summary,
                item.series_code,
                item.series_title,
                item.notes,
                item.future_path,
                mega_id,
                item.pdf_order,
                item.series_order,
                item.obsidian_path,
                pdf_path.name,
                now,
            ),
        )

    conn.execute(
        """
        INSERT INTO series (
            series_code, series_title, mega_group, pdf_order, episode_count,
            minutes_total, year_from, year_to, place_name, media_types
        )
        SELECT
            series_code,
            MAX(series_title),
            mega_group,
            MIN(series_order),
            COUNT(*),
            SUM(duration_minutes),
            MIN(year),
            MAX(year),
            CASE
                WHEN COUNT(DISTINCT place_name) = 1 THEN MAX(place_name)
                ELSE NULL
            END,
            GROUP_CONCAT(DISTINCT media_type)
        FROM items
        WHERE series_code IS NOT NULL AND trim(series_code) != ''
        GROUP BY series_code, mega_group
        ORDER BY MIN(series_order)
        """
    )

    conn.execute(
        "INSERT INTO catalog_meta (key, value) VALUES (?, ?)",
        ("source_pdf", str(pdf_path.name)),
    )
    conn.execute(
        "INSERT INTO catalog_meta (key, value) VALUES (?, ?)",
        ("pdf_sha256", pdf_hash),
    )
    conn.execute(
        "INSERT INTO catalog_meta (key, value) VALUES (?, ?)",
        ("last_import", now),
    )
    conn.execute(
        """
        INSERT INTO import_runs (imported_at, pdf_path, pdf_sha256, item_count, section_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now, str(pdf_path), pdf_hash, len(items), len(sections)),
    )
    restore_phase2_tables(conn, phase2)
    conn.commit()
    conn.close()


def export_csv(conn: sqlite3.Connection) -> None:
    import csv

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT
            i.code, s.code AS section_code, s.title AS section_title,
            i.title, i.media_type, i.duration_minutes,
            i.place_code, i.place_name, i.event_date, i.year,
            i.event_type, i.event_type_label, i.event_number,
            i.media_kind, i.series_code, i.series_title,
            i.future_path, i.obsidian_path, i.notes
        FROM items i
        JOIN sections s ON s.id = i.section_id
        ORDER BY s.sort_order, i.code
        """
    ).fetchall()
    headers = [
        "code", "section_code", "section_title", "title", "media_type",
        "duration_minutes", "place_code", "place_name", "event_date", "year",
        "event_type", "event_type_label", "event_number", "media_kind",
        "series_code", "series_title", "future_path", "obsidian_path", "notes",
    ]
    with open(EXPORTS_DIR / "catalog.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)

    sec_rows = conn.execute(
        "SELECT code, number, letter, title, slug, sort_order FROM sections ORDER BY sort_order"
    ).fetchall()
    with open(EXPORTS_DIR / "sections.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "number", "letter", "title", "slug", "sort_order"])
        w.writerows(sec_rows)


def export_csv_compact(conn: sqlite3.Connection) -> None:
    import csv

    headers = [
        "mega_group", "kind", "series_code", "episodes", "section",
        "title", "media_type", "minutes", "place_name", "year", "future_path",
    ]
    rows: list[list] = []

    for mega in [g["id"] for g in MEGA_GROUPS]:
        for s in fetch_series_aggregates(conn, mega):
            rows.append(
                [
                    mega,
                    "series",
                    s["series_code"],
                    s["episodes"],
                    s["section"],
                    s["series_title"],
                    s["media_type"],
                    s["minutes"],
                    s["place_name"],
                    s["year"],
                    "",
                ]
            )

    standalone = conn.execute(
        """
        SELECT
            i.mega_group, i.code, s.code, i.title, i.media_type,
            i.duration_minutes, i.place_name, i.year, i.future_path
        FROM items i
        JOIN sections s ON s.id = i.section_id
        WHERE i.series_code IS NULL OR trim(i.series_code) = ''
        ORDER BY i.pdf_order
        """
    ).fetchall()
    for r in standalone:
        rows.append(
            [r[0], "recording", r[1], 1, r[2], r[3], r[4], r[5], r[6], r[7], r[8]]
        )

    with open(EXPORTS_DIR / "catalog-compact.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def export_xlsx(conn: sqlite3.Connection) -> None:
    import pandas as pd

    items_df = pd.read_sql_query(
        """
        SELECT
            i.code, s.code AS section, s.title AS section_title,
            i.title, i.media_type, i.duration_minutes AS minutes,
            i.place_code, i.place_name, i.year, i.event_date,
            i.event_type, i.event_type_label, i.media_kind,
            i.series_code, i.series_title, i.future_path
        FROM items i
        JOIN sections s ON s.id = i.section_id
        ORDER BY s.sort_order, i.code
        """,
        conn,
    )
    sections_df = pd.read_sql_query(
        "SELECT code, title, slug, sort_order FROM sections ORDER BY sort_order",
        conn,
    )
    summary_df = pd.read_sql_query(
        """
        SELECT code, title, media_kind,
               CASE WHEN length(summary) > 0 THEN 1 ELSE 0 END AS has_summary
        FROM items ORDER BY code
        """,
        conn,
    )

    compact_rows = []
    for mega in [g["id"] for g in MEGA_GROUPS]:
        for s in fetch_series_aggregates(conn, mega):
            compact_rows.append(
                {
                    "mega_group": mega,
                    "kind": "series",
                    "series_code": s["series_code"],
                    "episodes": s["episodes"],
                    "title": s["series_title"],
                    "media_type": s["media_type"],
                    "minutes": s["minutes"],
                    "year": s["year"],
                    "place_name": s["place_name"],
                }
            )
    standalone_df = pd.read_sql_query(
        """
        SELECT mega_group, code AS series_code, title, media_type,
               duration_minutes AS minutes, place_name, year
        FROM items
        WHERE series_code IS NULL OR trim(series_code) = ''
        ORDER BY pdf_order
        """,
        conn,
    )
    compact_df = pd.DataFrame(compact_rows)
    if not standalone_df.empty:
        standalone_df.insert(1, "kind", "recording")
        standalone_df["episodes"] = 1
        compact_df = pd.concat([compact_df, standalone_df], ignore_index=True)
    series_df = pd.read_sql_query(
        """
        SELECT
            MIN(i.series_order) AS pdf_order,
            i.series_code, MAX(i.series_title) AS series_title,
            i.mega_group, COUNT(*) AS episodes,
            MIN(i.year) AS year_from, MAX(i.year) AS year_to
        FROM items i
        WHERE i.series_code IS NOT NULL AND trim(i.series_code) != ''
        GROUP BY i.series_code, i.mega_group
        ORDER BY MIN(i.series_order), i.series_code
        """,
        conn,
    )

    path = EXPORTS_DIR / "catalog.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        series_df.to_excel(writer, sheet_name="Series", index=False)
        compact_df.to_excel(writer, sheet_name="Compact", index=False)
        items_df.to_excel(writer, sheet_name="Catalog", index=False)
        sections_df.to_excel(writer, sheet_name="Sections", index=False)
        summary_df.to_excel(writer, sheet_name="Overview", index=False)


def md_cell(value) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def codes_range_label(codes: list[str]) -> str:
    """LO61T1 … LO61T12 → LO61T1–LO61T12"""
    if not codes:
        return "—"
    if len(codes) == 1:
        return codes[0]
    return f"{codes[0]}–{codes[-1]}"


def range_label(values: list) -> str:
    vals = [v for v in values if v is not None and v != ""]
    if not vals:
        return "—"
    if len(set(vals)) == 1:
        return str(vals[0])
    return f"{min(vals)}–{max(vals)}"


def total_minutes(durations: list) -> str | int:
    vals = [v for v in durations if v is not None]
    if not vals:
        return "—"
    return sum(vals)


def aggregate_episode_rows(episodes: list[tuple]) -> tuple:
    """Aggregate episode tuples into one combined row."""
    media = sorted({e[2] for e in episodes if e[2]})
    durations = [e[3] for e in episodes]
    years = [e[5] for e in episodes]
    places = [e[4] for e in episodes if e[4]]
    return (
        len(episodes),
        ", ".join(media) if media else "—",
        total_minutes(durations),
        range_label(years),
        places[0] if len(set(places)) == 1 else range_label(places),
    )


def fetch_series_aggregates(
    conn: sqlite3.Connection, mega_group: str | None = None
) -> list[dict]:
    """One combined row per series (PDF order), from `series` + `items` tables."""
    where = "WHERE s.mega_group = ?" if mega_group else ""
    params: tuple = (mega_group,) if mega_group else ()
    rows = conn.execute(
        f"""
        SELECT
            s.series_code, s.series_title, s.mega_group, s.episode_count,
            s.minutes_total, s.media_types, s.year_from, s.year_to, s.place_name,
            (SELECT sec.code FROM items i
             JOIN sections sec ON sec.id = i.section_id
             WHERE i.series_code = s.series_code AND i.mega_group = s.mega_group
             ORDER BY i.pdf_order LIMIT 1) AS section_code
        FROM series s
        {where}
        ORDER BY s.pdf_order, s.series_code
        """,
        params,
    ).fetchall()

    results = []
    for row in rows:
        sc, title, mega, ep_count, mins, media, y_from, y_to, place, section = row
        year = str(y_from) if y_from == y_to or y_to is None else f"{y_from}–{y_to}"
        results.append(
            {
                "series_code": sc,
                "series_title": title or sc,
                "mega_group": mega,
                "episodes": ep_count,
                "media_type": media or "—",
                "minutes": mins if mins is not None else "—",
                "year": year if y_from else "—",
                "place_name": place or "—",
                "section": section or "",
            }
        )
    return results


def render_combined_series_table(series_rows: list[dict]) -> list[str]:
    lines = [
        "| Series | Title | Ep. | Media | Min | Year | Place |",
        "|--------|-------|-----|-------|-----|------|-------|",
    ]
    for row in series_rows:
        title = row["series_title"]
        title_short = title[:60] + ("…" if len(title) > 60 else "")
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(row["series_code"]),
                    md_cell(title_short),
                    md_cell(row["episodes"]),
                    md_cell(row["media_type"]),
                    md_cell(row["minutes"]),
                    md_cell(row["year"]),
                    md_cell(row["place_name"]),
                ]
            )
            + " |"
        )
    return lines


def render_episode_table(rows: list[tuple]) -> list[str]:
    """One row per recording (standalone)."""
    lines = [
        "| Code | Title | Media | Min | Year | Place |",
        "|------|-------|-------|-----|------|-------|",
    ]
    for code, row_title, media_type, duration, place_name, year in rows:
        title_short = row_title[:70] + ("…" if len(row_title) > 70 else "")
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(code),
                    md_cell(title_short),
                    md_cell(media_type),
                    md_cell(duration),
                    md_cell(year),
                    md_cell(place_name),
                ]
            )
            + " |"
        )
    return lines


def export_series_csv(conn: sqlite3.Connection) -> None:
    import csv

    out_rows = conn.execute(
        """
        SELECT
            s.pdf_order, s.series_code, s.series_title, s.mega_group,
            s.episode_count,
            (SELECT GROUP_CONCAT(DISTINCT sec.code)
             FROM items i JOIN sections sec ON sec.id = i.section_id
             WHERE i.series_code = s.series_code AND i.mega_group = s.mega_group),
            s.year_from, s.year_to, s.minutes_total
        FROM series s
        ORDER BY s.pdf_order, s.series_code
        """
    ).fetchall()

    with open(EXPORTS_DIR / "catalog-series.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pdf_order", "series_code", "series_title", "mega_group",
                "episodes", "sections", "year_from", "year_to", "minutes_total",
            ]
        )
        w.writerows(out_rows)


def build_obsidian_series(conn: sqlite3.Connection) -> int:
    """Compact vault: one combined row per series + standalone recordings."""
    import shutil

    if OBSIDIAN_DIR.exists():
        shutil.rmtree(OBSIDIAN_DIR)
    OBSIDIAN_DIR.mkdir(parents=True)

    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    series_total = conn.execute(
        """
        SELECT COUNT(DISTINCT series_code) FROM items
        WHERE series_code IS NOT NULL AND trim(series_code) != ''
        """
    ).fetchone()[0]
    standalone_total = conn.execute(
        """
        SELECT COUNT(*) FROM items
        WHERE series_code IS NULL OR trim(series_code) = ''
        """
    ).fetchone()[0]

    index_lines = [
        "---",
        "tags: [krishnamurti, index]",
        "layout: series-combined",
        "---",
        "# Krishnamurti Recordings Library",
        "",
        "Compact catalog — **9 notes** (index + 8 groups). Each **series** is one row "
        "(e.g. `LO61T1-12`); **Min** = total minutes in the series.",
        "",
        f"**{total}** recordings · **{series_total}** series · **{standalone_total}** standalone.",
        "",
        "Full summaries: `catalog/krishnamurti.db` · Series list: `catalog/exports/catalog-series.csv`",
        "",
        "## Groups",
        "",
        "| Group | Series | Standalone | Total |",
        "|-------|--------|------------|-------|",
    ]

    file_count = 1
    mega_filename = {g["id"]: g["filename"] for g in MEGA_GROUPS}

    for group in MEGA_GROUPS:
        gid, title, filename = group["id"], group["title"], group["filename"]
        count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE mega_group = ?", (gid,)
        ).fetchone()[0]
        series_in_group = conn.execute(
            """
            SELECT COUNT(DISTINCT series_code) FROM items
            WHERE mega_group = ? AND series_code IS NOT NULL AND trim(series_code) != ''
            """,
            (gid,),
        ).fetchone()[0]
        standalone_in_group = conn.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE mega_group = ?
              AND (series_code IS NULL OR trim(series_code) = '')
            """,
            (gid,),
        ).fetchone()[0]

        index_lines.append(
            f"| [[{filename}|{title}]] | {series_in_group} | {standalone_in_group} | {count} |"
        )

        lines = [
            "---",
            f"tags: [krishnamurti, mega-group, group-{gid}]",
            f"mega_group: {gid}",
            "layout: series-combined",
            "---",
            f"# {title}",
            "",
            f"[[00 - Library Index|← Library index]] · PDF sections: {group['pdf_sections']}",
            "",
            f"**{count}** recordings in **{series_in_group}** series + **{standalone_in_group}** standalone.",
            "",
        ]

        series_agg = fetch_series_aggregates(conn, gid)
        if series_agg:
            lines.extend(
                ["## Series", "", f"*{len(series_agg)} series* (one row per series).", ""]
            )
            lines.extend(render_combined_series_table(series_agg))
            lines.append("")

        standalone = conn.execute(
            """
            SELECT i.code, i.title, i.media_type, i.duration_minutes,
                   i.place_name, i.year, s.code AS section_code
            FROM items i
            JOIN sections s ON s.id = i.section_id
            WHERE i.mega_group = ?
              AND (i.series_code IS NULL OR trim(i.series_code) = '')
            ORDER BY i.pdf_order
            """,
            (gid,),
        ).fetchall()

        if standalone:
            lines.extend(["## Standalone", ""])
            current_section = None
            section_rows: list[tuple] = []
            for row in standalone:
                code, row_title, media_type, duration, place_name, year, sec_code = row
                if sec_code != current_section:
                    if section_rows:
                        lines.extend(render_episode_table(section_rows))
                        lines.append("")
                    current_section = sec_code
                    sec_title = conn.execute(
                        "SELECT title FROM sections WHERE code = ?", (sec_code,)
                    ).fetchone()[0]
                    lines.append(f"### {sec_code} — {sec_title}")
                    lines.append("")
                    section_rows = []
                section_rows.append(
                    (code, row_title, media_type, duration, place_name, year)
                )
            if section_rows:
                lines.extend(render_episode_table(section_rows))
                lines.append("")

        lines.extend(
            [
                "---",
                "## Full detail",
                "",
                "- Summaries: [[00 - Library Index#Lookup summaries]]",
                f"- All episodes: `catalog/exports/catalog-compact.csv` (`mega_group={gid}`)",
                "",
            ]
        )
        (OBSIDIAN_DIR / filename).write_text("\n".join(lines), encoding="utf-8")
        file_count += 1

    series_index_rows = []
    for s in fetch_series_aggregates(conn):
        mega_id = s.get("mega_group", "")
        fname = mega_filename.get(mega_id, "")
        link = f"[[{fname}|{mega_id}]]" if fname else mega_id
        series_index_rows.append(
            f"| {md_cell(s['series_code'])} | {md_cell(s['series_title'][:50])} | "
            f"{link} | {s['episodes']} | {md_cell(s['minutes'])} |"
        )

    index_lines.extend(
        [
            "",
            "## All series (PDF order)",
            "",
            "| Series | Title | Group | Ep. | Min |",
            "|--------|-------|-------|-----|-----|",
            *series_index_rows,
            "",
            "## Lookup summaries",
            "",
            "```bash",
            "sqlite3 catalog/krishnamurti.db \\",
            '  "SELECT summary FROM items WHERE code = \'BR75T3\';"',
            "```",
            "",
            "## Exports",
            "",
            "| File | Contents |",
            "|------|----------|",
            "| `catalog/exports/catalog-series.csv` | One row per series |",
            "| `catalog/exports/catalog-compact.csv` | One row per series + standalone |",
            "| `catalog/exports/catalog.csv` | Full metadata + summaries |",
            "",
            "Rebuild: `python3 scripts/build_catalog.py`",
            "",
        ]
    )
    (OBSIDIAN_DIR / "00 - Library Index.md").write_text(
        "\n".join(index_lines), encoding="utf-8"
    )
    return file_count


def write_manifest(pdf_path: Path, pdf_hash: str, sections: int, items: int) -> None:
    manifest = {
        "source_pdf": pdf_path.name,
        "pdf_sha256": pdf_hash,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "items": items,
        "obsidian_layout": "series-combined",
        "outputs": {
            "sqlite": str(DB_PATH.relative_to(ROOT)),
            "csv": str((EXPORTS_DIR / "catalog.csv").relative_to(ROOT)),
            "csv_compact": str((EXPORTS_DIR / "catalog-compact.csv").relative_to(ROOT)),
            "csv_series": str((EXPORTS_DIR / "catalog-series.csv").relative_to(ROOT)),
            "xlsx": str((EXPORTS_DIR / "catalog.xlsx").relative_to(ROOT)),
            "obsidian": str(OBSIDIAN_DIR.relative_to(ROOT)),
        },
    }
    (CATALOG_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def main(pdf_path: Path = PDF_DEFAULT) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    places = load_places()
    print(f"Reading {pdf_path.name}...")
    text = pdf_to_text(pdf_path)
    body = find_catalog_body(text)
    sections, raw_items = parse_sections_and_items(body, places)
    items = dedupe_items(raw_items)
    assign_series_order(items)
    apply_series_folder_paths(items)

    print(f"Sections: {len(sections)}")
    print(f"Items (unique codes): {len(items)}")
    audio = sum(1 for i in items if i.media_type == "audio")
    video = sum(1 for i in items if i.media_type == "video")
    print(f"  Audio: {audio}, Video: {video}")

    pdf_hash = file_sha256(pdf_path)
    save_db(sections, items, pdf_path, pdf_hash)

    conn = sqlite3.connect(DB_PATH)
    export_csv(conn)
    print("Wrote catalog/exports/catalog.csv")
    export_csv_compact(conn)
    print("Wrote catalog/exports/catalog-compact.csv")
    export_series_csv(conn)
    print("Wrote catalog/exports/catalog-series.csv")
    export_xlsx(conn)
    print("Wrote catalog/exports/catalog.xlsx")
    note_count = build_obsidian_series(conn)
    print(f"Wrote series-combined Obsidian vault ({note_count} notes)")
    conn.close()

    write_manifest(pdf_path, pdf_hash, len(sections), len(items))
    print("Done.")


if __name__ == "__main__":
    main()