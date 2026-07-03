#!/usr/bin/env python3
"""
Discover streaming links from KFT Full-Length Directory PDF only (no downloads).

Populates item_links exclusively with youtu.be hyperlinks embedded in the PDF.
On each run: DELETE all rows in item_links (except rows whose notes start with
"Manually verified", which are kept as-is), then insert fresh primary links.

Optional: --archive for Internet Archive alternates (off by default).

Outputs:
  - catalog/krishnamurti.db item_links
  - catalog/link_cache.json (oEmbed cache, gitignored)
  - catalog/exports/links-comparison.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

# Reuse catalog code parsing for structural YouTube title matching
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_catalog import EVENT_TYPES, parse_code  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLACES_FILE = Path(__file__).resolve().parent / "places.json"
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
PDF_DEFAULT = ROOT / "Krishnamurti-Foundation-Trust-–-Full-Length-Directory-2026.pdf"
CACHE_PATH = ROOT / "catalog" / "link_cache.json"
EXPORT_PATH = ROOT / "catalog" / "exports" / "links-comparison.csv"
KFT_VIDEO_PAGE = "https://kfoundation.org/video/"

USER_AGENT = "krishnamurti-catalog-research/1.0 (+local indexing; no downloads)"

YEAR_IN_TITLE_RE = re.compile(r"\b((?:19|20)\d{2})\b")
YEAR_SLASH_RE = re.compile(r"\b(\d{2})/(\d{2})\b")
GENERIC_QA_TITLE_RE = re.compile(
    r"^\d+(?:st|nd|rd|th)\s+question\s+and\s+answer\s+meeting$", re.I
)


@dataclass
class YouTubeLink:
    video_id: str
    url: str
    page: int
    y: float


def http_json(url: str, timeout: int = 20) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def norm_title(s: str) -> str:
    s = s.replace("–", "-").replace("—", "-").replace("&", "").lower()
    s = re.sub(r"[^a-z0-9 -]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def yt_tail(title: str) -> str:
    t = title.replace("–", "-").replace("—", "-")
    parts = [p.strip() for p in t.split("-") if p.strip()]
    return norm_title(parts[-1] if parts else t)


def is_generic_catalog_title(title: str) -> bool:
    return bool(GENERIC_QA_TITLE_RE.match(norm_title(title)))


def years_in_youtube_title(yt_title: str) -> set[int]:
    years = {int(y) for y in YEAR_IN_TITLE_RE.findall(yt_title)}
    for a, b in YEAR_SLASH_RE.findall(yt_title):
        years.add(1900 + int(a))
        years.add(1900 + int(b))
    return {y for y in years if 1900 <= y <= 2035}


def catalog_match_years(code: str, year: int | None, places: dict[str, str]) -> set[int]:
    years: set[int] = set()
    if year and 1900 <= year <= 2035:
        years.add(year)
    parsed = parse_code(code, places)
    py = parsed.get("year")
    if py and 1900 <= py <= 2035:
        years.add(py)
    m = re.match(r"^[A-Z]{2,3}(\d{2,4})", code)
    if m:
        digits = m.group(1)
        if len(digits) == 2:
            yi = int(digits)
            years.add(1900 + yi if yi > 30 else 2000 + yi)
        elif len(digits) == 4:
            years.add(1900 + int(digits[:2]))
            years.add(1900 + int(digits[2:]))
    return {y for y in years if 1900 <= y <= 2035}


def year_overlap(
    code: str, year: int | None, yt_title: str, places: dict[str, str]
) -> bool:
    cat = catalog_match_years(code, year, places)
    yt = years_in_youtube_title(yt_title)
    if not cat:
        return True
    if not yt:
        return False
    return bool(cat & yt)


def place_overlap(
    code: str,
    place_name: str | None,
    yt_title: str,
    places: dict[str, str],
) -> bool:
    parsed = parse_code(code, places)
    pc = parsed.get("place_code")
    place_kws = _place_keywords(place_name or parsed.get("place_name_catalog"), pc)
    if not place_kws:
        return True
    ytn = norm_title(yt_title)
    return any(kw in ytn for kw in place_kws if len(kw) >= 4)


def titles_match(db_title: str, yt_title: str) -> bool:
    dbn = norm_title(db_title)
    ytn = norm_title(yt_title)
    ytl = yt_tail(yt_title)
    if not dbn:
        return False
    if dbn[:20] in ytn or ytl[:25] in dbn or dbn[:25] in ytl:
        return True
    return False


def _place_keywords(place_name: str | None, place_code: str | None) -> list[str]:
    keys: list[str] = []
    if place_code:
        keys.append(place_code.lower())
    if not place_name:
        return keys
    name = place_name.lower()
    keys.append(norm_title(place_name.split(",")[0]))
    for token in ("brockwood", "london", "saanen", "madras", "chennai", "bombay", "mumbai",
                  "delhi", "bangalore", "rajghat", "rishi", "ojai", "berkeley", "malibu",
                  "calcutta", "kolkata", "amsterdam", "ommen", "gstaad", "wimbledon"):
        if token in name:
            keys.append(token)
    return [k for k in keys if len(k) >= 4]


def _event_patterns(event_type: str | None, event_number: str | None) -> list[str]:
    if not event_type:
        return []
    n = event_number or ""
    label = EVENT_TYPES.get(event_type, "")
    patterns: list[str] = []
    if event_type == "T":
        patterns.extend([f"public talk {n}", f"talk {n}"])
    elif event_type == "Q":
        patterns.extend([f"public q&a {n}", f"q&a {n}", f"question & answer {n}"])
        if n == "1":
            patterns.append("1st question")
        if n == "2":
            patterns.append("2nd question")
    elif event_type == "D":
        patterns.extend([f"public discussion {n}", f"discussion {n}"])
    elif event_type in ("DS", "DSG", "DSS", "DT", "DYP"):
        patterns.extend([f"discussion {n}", label.lower() if label else ""])
    elif event_type == "C":
        patterns.append("conversation")
    if label:
        patterns.append(norm_title(label))
    return [p for p in patterns if p.strip()]


def event_type_matches(
    *,
    code: str,
    event_type: str | None,
    event_number: str | None,
    yt_title: str,
    places: dict[str, str],
) -> bool:
    ytn = norm_title(yt_title)
    parsed = parse_code(code, places)
    et = event_type or parsed.get("event_type")
    en = event_number if event_number is not None else parsed.get("event_number")
    if not et:
        return True
    pats = _event_patterns(et, str(en) if en is not None else None)
    if not pats:
        return True
    return any(norm_title(p) in ytn for p in pats)


def infer_format(yt_title: str, db_media: str | None) -> str:
    t = yt_title.lower()
    if t.startswith("video") or "| video" in t:
        return "video"
    if t.startswith("audio") or "| audio" in t:
        return "audio"
    return db_media or "unknown"


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {"oembed": {}, "archive": {}}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def oembed_lookup(video_id: str, cache: dict) -> tuple[str, str]:
    if video_id in cache["oembed"]:
        d = cache["oembed"][video_id]
        return d["title"], d.get("author", "")
    url = f"https://www.youtube.com/oembed?url={urllib.parse.quote('https://youtu.be/' + video_id)}&format=json"
    data = http_json(url, timeout=15)
    title = data.get("title", "")
    author = data.get("author_name", "")
    cache["oembed"][video_id] = {"title": title, "author": author}
    return title, author


def extract_pdf_youtube(pdf_path: Path) -> tuple[list[YouTubeLink], list[dict]]:
    reader = PdfReader(str(pdf_path))
    links: list[YouTubeLink] = []
    playlists: list[dict] = []
    for pi, page in enumerate(reader.pages):
        annots = page.get("/Annots")
        if not annots:
            continue
        for ref in annots:
            obj = ref.get_object()
            if obj.get("/Subtype") != "/Link" or "/A" not in obj:
                continue
            uri = str(obj["/A"].get("/URI", ""))
            if "youtu.be/" in uri:
                vid = uri.split("youtu.be/")[-1].split("?")[0]
                rect = obj.get("/Rect")
                y = -float(rect[1]) if rect else 0.0
                links.append(
                    YouTubeLink(
                        video_id=vid,
                        url=f"https://youtu.be/{vid}",
                        page=pi + 1,
                        y=y,
                    )
                )
            elif "youtube.com/playlist" in uri:
                m = re.search(r"list=([^&\s]+)", uri)
                if m:
                    playlists.append(
                        {
                            "playlist_id": m.group(1),
                            "url": re.sub(r"&si=.*", "", uri),
                            "page": pi + 1,
                        }
                    )
    links.sort(key=lambda x: (x.page, x.y))
    return links, playlists


def scrape_kft_video_playlists() -> list[dict]:
    req = urllib.request.Request(KFT_VIDEO_PAGE, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    out = []
    for m in re.finditer(
        r'href="(https://youtube\.com/playlist\?list=[^"]+)"', html, re.I
    ):
        url = m.group(1).replace("&#038;", "&")
        pid = re.search(r"list=([^&]+)", url)
        if pid:
            out.append({"playlist_id": pid.group(1), "url": url, "source": "kft_video_page"})
    # dedupe
    seen: set[str] = set()
    deduped = []
    for p in out:
        if p["playlist_id"] in seen:
            continue
        seen.add(p["playlist_id"])
        deduped.append(p)
    return deduped


def match_score(row: tuple, yt_title: str, places: dict[str, str]) -> float:
    _id, code, title, media_type, year, place_name, pdf_order, event_type, event_number = row
    if not year_overlap(code, year, yt_title, places):
        return 0.0
    if not place_overlap(code, place_name, yt_title, places):
        return 0.0
    if not is_generic_catalog_title(title) and titles_match(title, yt_title):
        return 1.0
    if event_type_matches(
        code=code,
        event_type=event_type,
        event_number=event_number,
        yt_title=yt_title,
        places=places,
    ):
        return 0.88
    return 0.0


def align_pdf_links_to_items(
    items: list[tuple],
    links: list[YouTubeLink],
    cache: dict,
    places: dict[str, str],
    *,
    min_score: float = 0.85,
    sleep_s: float = 0.02,
) -> list[dict]:
    """Assign each item the best unused PDF YouTube link (global match)."""
    link_meta: list[dict] = []
    for link in links:
        try:
            yt_title, author = oembed_lookup(link.video_id, cache)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            continue
        link_meta.append(
            {
                "video_id": link.video_id,
                "url": link.url,
                "page": link.page,
                "title": yt_title,
                "author": author,
            }
        )
        if sleep_s:
            time.sleep(sleep_s)

    used: set[str] = set()
    results: list[dict] = []
    for row in items:
        item_id, code, title, media_type, year, place_name, pdf_order, event_type, event_number = row
        best = None
        best_score = 0.0
        for lm in link_meta:
            if lm["video_id"] in used:
                continue
            sc = match_score(row, lm["title"], places)
            if sc > best_score:
                best_score = sc
                best = lm
        if best and best_score >= min_score:
            used.add(best["video_id"])
            results.append(
                {
                    "item_id": item_id,
                    "code": code,
                    "video_id": best["video_id"],
                    "url": best["url"],
                    "source": "kft_pdf_youtube",
                    "link_kind": "primary",
                    "remote_title": best["title"],
                    "author": best["author"],
                    "media_format": infer_format(best["title"], media_type),
                    "match_score": best_score,
                    "pdf_page": best["page"],
                    "pdf_order": pdf_order,
                }
            )
    return results


def archive_search(title: str, year: int | None, cache: dict) -> list[dict]:
    key = f"{year}|{title[:80]}"
    if key in cache["archive"]:
        return cache["archive"][key]
    q_parts = ["krishnamurti", f'"{title[:60]}"']
    if year:
        q_parts.append(str(year))
    q = " AND ".join(q_parts)
    params = urllib.parse.urlencode(
        {
            "q": q,
            "fl[]": ["identifier", "title", "format", "downloads"],
            "rows": 5,
            "output": "json",
        }
    )
    url = f"https://archive.org/advancedsearch.php?{params}"
    try:
        data = http_json(url, timeout=25)
    except urllib.error.URLError:
        cache["archive"][key] = []
        return []
    hits = []
    for doc in data.get("response", {}).get("docs", []):
        formats = doc.get("format", []) or []
        fmt = ", ".join(formats[:6]) if isinstance(formats, list) else str(formats)
        ident = doc.get("identifier", "")
        if not ident:
            continue
        hits.append(
            {
                "url": f"https://archive.org/details/{ident}",
                "remote_title": doc.get("title", ""),
                "media_format": fmt,
                "source": "archive_org",
                "link_kind": "alternate",
            }
        )
    cache["archive"][key] = hits
    time.sleep(0.35)
    return hits


def ensure_link_schema(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(item_links)").fetchall()}
    migrations = [
        ("video_id", "TEXT"),
        ("remote_title", "TEXT"),
        ("media_format", "TEXT"),
        ("match_score", "REAL"),
        ("discovered_at", "TEXT"),
        ("notes", "TEXT"),
    ]
    for name, typ in migrations:
        if name not in cols:
            conn.execute(f"ALTER TABLE item_links ADD COLUMN {name} {typ}")


def write_links(
    conn: sqlite3.Connection,
    rows: list[dict],
    now: str,
    *,
    replace: bool = True,
    item_ids: set[int] | None = None,
) -> int:
    ensure_link_schema(conn)
    if replace:
        # Rows marked "Manually verified" fix PDF hyperlink errors (wrong-row
        # association, season-shifted Q&A links); re-discovery must not undo them.
        if item_ids is not None:
            placeholders = ",".join("?" * len(item_ids))
            conn.execute(
                f"DELETE FROM item_links WHERE item_id IN ({placeholders})"
                " AND COALESCE(notes,'') NOT LIKE 'Manually verified%'",
                tuple(item_ids),
            )
        else:
            conn.execute(
                "DELETE FROM item_links WHERE COALESCE(notes,'') NOT LIKE 'Manually verified%'"
            )
    manual = {
        (item_id, link_kind)
        for item_id, link_kind in conn.execute(
            "SELECT item_id, link_kind FROM item_links"
            " WHERE COALESCE(notes,'') LIKE 'Manually verified%'"
        )
    }
    n = 0
    for r in rows:
        if (r["item_id"], r.get("link_kind", "alternate")) in manual:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO item_links (
                item_id, url, link_kind, source,
                video_id, remote_title, media_format, match_score, discovered_at, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                r["item_id"],
                r["url"],
                r.get("link_kind", "alternate"),
                r.get("source", "unknown"),
                r.get("video_id"),
                r.get("remote_title"),
                r.get("media_format"),
                r.get("match_score"),
                now,
                r.get("notes"),
            ),
        )
        n += 1
    return n


def export_comparison_csv(conn: sqlite3.Connection, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT i.code, i.title, i.media_type, i.year, i.place_name,
               l.source, l.link_kind, l.url, l.video_id, l.remote_title,
               l.media_format, l.match_score
        FROM items i
        LEFT JOIN item_links l ON l.item_id = i.id
        ORDER BY i.pdf_order, l.link_kind, l.source
        """
    ).fetchall()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "code",
                "title",
                "catalog_media",
                "year",
                "place",
                "source",
                "link_kind",
                "url",
                "video_id",
                "remote_title",
                "remote_format",
                "match_score",
            ]
        )
        w.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover KFT and alternate streaming links")
    parser.add_argument("--pdf", type=Path, default=PDF_DEFAULT)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Limit items (0=all)")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also search archive.org (slow; rate-limited)",
    )
    parser.add_argument(
        "--archive-all",
        action="store_true",
        help="Search archive.org for all items (not only unmatched)",
    )
    parser.add_argument(
        "--archive-limit",
        type=int,
        default=50,
        help="Max items to query on archive.org",
    )
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clear oEmbed cache before run (re-fetches all YouTube metadata)",
    )
    parser.add_argument(
        "--save-playlists",
        action="store_true",
        help="Also scrape kfoundation.org/video playlists into kft_playlists.json",
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}. Run build_catalog.py first.")
    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    if args.fresh and CACHE_PATH.exists():
        CACHE_PATH.unlink()
        print("Cleared oEmbed cache (--fresh)")

    cache = load_cache()
    now = datetime.now(timezone.utc).isoformat()

    print("Extracting YouTube links from KFT PDF…")
    yt_links, pdf_playlists = extract_pdf_youtube(args.pdf)
    print(f"  {len(yt_links)} youtu.be links in PDF")

    web_playlists: list[dict] = []
    if args.save_playlists:
        print("Scraping kfoundation.org/video playlists…")
        web_playlists = scrape_kft_video_playlists()
        print(f"  {len(web_playlists)} playlists on video page")

    places = json.loads(PLACES_FILE.read_text(encoding="utf-8"))

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    q = """
        SELECT id, code, title, media_type, year, place_name, pdf_order,
               event_type, event_number
        FROM items ORDER BY pdf_order
    """
    items = list(conn.execute(q))
    if args.limit:
        items = items[: args.limit]

    print(f"Matching PDF links to {len(items)} catalog items (year/place validated)…")
    primary = align_pdf_links_to_items(
        [tuple(r) for r in items], yt_links, cache, places
    )
    print(f"  matched {len(primary)} / {len(items)}")

    all_rows: list[dict] = list(primary)

    if args.save_playlists:
        playlist_meta_path = ROOT / "catalog" / "kft_playlists.json"
        playlist_meta_path.write_text(
            json.dumps(
                {
                    "pdf_playlists": pdf_playlists,
                    "video_page_playlists": web_playlists,
                    "imported_at": now,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    matched_ids = {r["item_id"] for r in primary}

    if args.limit:
        print(
            f"Removing previous item_links for {len(items)} limited items and writing PDF YouTube links…"
        )
    else:
        print("Removing all previous item_links and writing PDF YouTube links only…")
    if args.archive:
        archive_items = items[: args.archive_limit]
        if not getattr(args, "archive_all", False):
            archive_items = [r for r in items if r[0] not in matched_ids][
                : args.archive_limit
            ]
        print(f"Searching archive.org for {len(archive_items)} items…")
        for row in archive_items:
            item_id, code, title, media_type, year, place_name, pdf_order, event_type, event_number = row
            alts = archive_search(title, year, cache)
            for hit in alts[:2]:
                hit["item_id"] = item_id
                hit["code"] = code
                hit["match_score"] = 0.5
                hit["notes"] = "fuzzy archive.org search"
                all_rows.append(hit)

    if args.limit:
        n = write_links(
            conn, all_rows, now, item_ids={r[0] for r in items}
        )
    else:
        n = write_links(conn, all_rows, now)
    conn.commit()
    save_cache(cache)

    if not args.no_export:
        export_comparison_csv(conn, EXPORT_PATH)

    other = conn.execute(
        "SELECT COUNT(*) FROM item_links WHERE source != 'kft_pdf_youtube'"
    ).fetchone()[0]
    if other:
        print(f"WARNING: {other} non-PDF links present (unexpected)")

    by_source = conn.execute(
        "SELECT source, link_kind, COUNT(*) FROM item_links GROUP BY source, link_kind"
    ).fetchall()
    print("\nLink counts:")
    for src, kind, cnt in by_source:
        print(f"  {src} ({kind}): {cnt}")
    if not args.no_export:
        print(f"\nWrote {EXPORT_PATH}")
    print(f"Cache: {CACHE_PATH}")


if __name__ == "__main__":
    main()