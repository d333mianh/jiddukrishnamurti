#!/usr/bin/env python3
"""Import an official, untimed KFT web transcript as a text subtitle source.

This is for catalog items whose media cannot be downloaded but whose complete
transcript is published by KFT. The importer deliberately writes plain text,
not synthetic VTT cues: estimated timestamps would create false citations in
the L2 passage pipeline.

Example:
  import_kft_web_transcript.py BR74FPL \
    https://kfoundation.org/transcript/film-brockwood-park-1-october-1974/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from subtitle_schema import ensure_subtitle_schema

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "catalog" / "krishnamurti.db"
KIND = "kft-web-transcript"
USER_AGENT = "jiddu-krishnamurti-catalog/1.0"


class ApiLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        values = dict(attrs)
        if values.get("type") == "application/json" and values.get("href"):
            self.urls.append(values["href"] or "")


class ParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            if self.depth == 0:
                self.current = []
            self.depth += 1
        elif tag == "br" and self.depth:
            self.current.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag != "p" or not self.depth:
            return
        self.depth -= 1
        if self.depth == 0:
            text = re.sub(r"\s+", " ", "".join(self.current)).strip()
            if text:
                self.paragraphs.append(text)

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.current.append(data)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def discover_api_url(page_url: str, page_html: str) -> str:
    parser = ApiLinkParser()
    parser.feed(page_html)
    for url in parser.urls:
        if "/wp/v2/kft_transcript/" in url:
            return urllib.parse.urljoin(page_url, url)
    raise ValueError("KFT transcript API link not found on page")


def transcript_from_api(api_url: str) -> tuple[dict, list[str]]:
    payload = json.loads(fetch(api_url).decode("utf-8"))
    rendered = payload.get("content", {}).get("rendered", "")
    parser = ParagraphParser()
    parser.feed(rendered)
    if not parser.paragraphs:
        raise ValueError("KFT API returned no transcript paragraphs")
    return payload, parser.paragraphs


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Import an official untimed KFT web transcript"
    )
    ap.add_argument("item", help="catalog item code, e.g. BR74FPL")
    ap.add_argument("url", help="official kfoundation.org transcript page")
    ap.add_argument("--language", default="en-GB")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    host = (urllib.parse.urlparse(args.url).hostname or "").lower()
    if host not in {"kfoundation.org", "www.kfoundation.org"}:
        raise SystemExit("refusing non-KFT transcript URL")

    conn = sqlite3.connect(DB_PATH)
    ensure_subtitle_schema(conn)
    row = conn.execute(
        "SELECT id, future_path FROM items WHERE code=?", (args.item,)
    ).fetchone()
    if not row:
        raise SystemExit(f"item not in catalog: {args.item}")

    page_html = fetch(args.url).decode("utf-8", errors="replace")
    api_url = discover_api_url(args.url, page_html)
    payload, paragraphs = transcript_from_api(api_url)
    text = "\n\n".join(paragraphs).strip() + "\n"
    word_count = len(text.split())
    if word_count < 100:
        raise SystemExit(f"refusing suspiciously short transcript: {word_count} words")

    media_path = ROOT / row[1]
    text_path = media_path.with_suffix(".kft.txt")
    metadata_path = media_path.with_suffix(".kft.json")
    fetched_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "api_url": api_url,
        "fetched_at": fetched_at,
        "item": args.item,
        "kind": KIND,
        "language": args.language,
        "paragraph_count": len(paragraphs),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_url": args.url,
        "timestamps": False,
        "title": payload.get("title", {}).get("rendered"),
        "word_count": word_count,
        "wordpress_post_id": payload.get("id"),
    }

    print(f"{args.item}: {len(paragraphs)} paragraphs, {word_count} words")
    print(f"  text: {text_path.relative_to(ROOT)}")
    print(f"  metadata: {metadata_path.relative_to(ROOT)}")
    print("  timestamps: unavailable (text will not enter timed passage ingestion)")
    if args.dry_run:
        return

    atomic_write(text_path, text)
    atomic_write(metadata_path, json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    conn.execute(
        """INSERT INTO item_subtitles (
               item_id, language, kind, format, future_path, file_size,
               status, error_message, downloaded_at
           ) VALUES (?, ?, ?, 'txt', ?, ?, 'downloaded', NULL, ?)
           ON CONFLICT(item_id, language, kind) DO UPDATE SET
               format='txt', future_path=excluded.future_path,
               file_size=excluded.file_size, status='downloaded',
               error_message=NULL, downloaded_at=excluded.downloaded_at""",
        (
            row[0],
            args.language,
            KIND,
            str(text_path.relative_to(ROOT)),
            text_path.stat().st_size,
            fetched_at,
        ),
    )
    conn.commit()
    print("  registered in item_subtitles")


if __name__ == "__main__":
    main()
