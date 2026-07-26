"""Guards on subtitle filename construction.

A `.with_suffix()` call in `subtitle_output_path` silently destroyed 111 manual
VTTs. Item codes carry a part number after a dot (`BR72DSS1.02`), so pathlib
read `.02 - Are you revolutionary` as the file's suffix and replacing it
collapsed all ten parts of the series onto `BR72DSS1.en.vtt`. Each download
overwrote the last; the catalog still recorded a per-item `future_path` and a
`file_size`, so 111 rows claimed `downloaded` for files that were not there,
and 82 of those items never reached the corpus at all.

The bug was invisible because the two functions that build the name disagreed:
the one writing the DB got it right by string, the one writing the disk got it
wrong by pathlib. They now share `subtitle_name`, and these tests hold the two
properties that failure violated: distinct items get distinct files, and the
path the downloader writes is the path the catalog records.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import download_subtitles as ds  # noqa: E402

CATALOG_DB = ROOT / "catalog" / "krishnamurti.db"
SERIES_DIR = "library/6A-k-school-discussions-england-and-switzerland/1212-BR72DSS1.1-1.10"


class SubtitleNameTests(unittest.TestCase):
    def test_dotted_item_codes_do_not_collapse(self) -> None:
        """Ten parts of one series must yield ten filenames, not one."""
        names = {
            ds.subtitle_name(f"BR72DSS1.{n:02d} - Some title {n}.m4a", "en")
            for n in range(1, 11)
        }
        self.assertEqual(len(names), 10, f"filenames collapsed: {sorted(names)}")
        self.assertIn("BR72DSS1.02 - Some title 2.en.vtt", names)
        self.assertNotIn("BR72DSS1.en.vtt", names)

    def test_media_extension_is_stripped_not_the_code(self) -> None:
        self.assertEqual(
            ds.subtitle_name("BR72DSS1.02 - You can live without an image.m4a", "en"),
            "BR72DSS1.02 - You can live without an image.en.vtt",
        )

    def test_all_media_suffixes_handled(self) -> None:
        for ext in ds.MEDIA_SUFFIXES:
            self.assertEqual(
                ds.subtitle_name(f"X84DSG1.1 - A title{ext}", "en"),
                "X84DSG1.1 - A title.en.vtt",
                f"suffix {ext} not stripped",
            )

    def test_name_without_media_suffix_is_left_alone(self) -> None:
        self.assertEqual(ds.subtitle_name("BR72DSS1.02 - Title", "en"),
                         "BR72DSS1.02 - Title.en.vtt")

    def test_download_destination_matches_catalog_path(self) -> None:
        """What the downloader writes must be what the catalog records.

        These drifted apart once, which is why the DB could report a file that
        was never written to that path.
        """
        for n in range(1, 11):
            future = f"{SERIES_DIR}/BR72DSS1.{n:02d} - Title {n}.m4a"
            recorded = Path(ds.subtitle_future_path(future, "en")).name
            written = ds.subtitle_output_path(
                future, "en", root=ROOT, series_code="BR72DSS1"
            ).name
            self.assertEqual(recorded, written, f"part {n} drifted")


class CatalogSubtitleIntegrityTests(unittest.TestCase):
    """`status='downloaded'` is a claim about the filesystem. Gate it.

    Nothing checked this, so 111 false claims sat in the catalog for seven
    weeks. This test is skipped on a clone with no media tree (`library/` is
    gitignored and cannot be shipped), but it fails loudly on the machine that
    actually holds the archive.
    """

    def test_downloaded_manual_subtitles_exist_on_disk(self) -> None:
        if not CATALOG_DB.exists():
            self.skipTest("catalog DB not present")
        if not (ROOT / "library").is_dir():
            self.skipTest("no library/ tree on this machine")
        conn = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT i.code, s.future_path FROM item_subtitles s "
                "JOIN items i ON i.id = s.item_id "
                "WHERE s.kind = 'manual' AND s.status = 'downloaded'"
            ).fetchall()
        finally:
            conn.close()
        missing = [code for code, fp in rows if not (ROOT / fp).exists()]
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} of {len(rows)} manual subtitles are marked "
            f"'downloaded' but absent from disk, e.g. {sorted(missing)[:5]}. "
            "Re-probe and re-download them, or correct the status.",
        )


if __name__ == "__main__":
    unittest.main()
