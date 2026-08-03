"""Guards on backup archive filename construction.

The same `.with_suffix()` misuse that destroyed 111 manual VTTs was also in
`backup_corpus.py`: the archive is named `krishnamurti-backup-<stamp>.tar.zst`,
and `with_suffix(".tar.zst.sha256")` replaces only the final `.zst`, so the
checksum was written to `…tar.tar.zst.sha256`. Two consequences, both silent —
the sidecar no longer matched the archive it certifies, and the pruning path
computed the same wrong name, so `unlink(missing_ok=True)` left the real
sidecar of a deleted archive orphaned in the backup directory.

Found on 2026-08-03 by looking at the directory after a run, not by any check.
These tests hold the two properties that failure violated: the sidecar sits
beside its archive under the archive's own name, and pruning removes exactly
the pair it wrote.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import backup_corpus as bc  # noqa: E402

STAMP = "20260803T081552Z"
ARCHIVE = f"krishnamurti-backup-{STAMP}.tar.zst"


class SidecarNameTests(unittest.TestCase):
    def test_sidecar_is_the_archive_name_plus_sha256(self) -> None:
        """The compound `.tar.zst` extension must survive intact."""
        archive = Path("/backups") / ARCHIVE
        self.assertEqual(bc.sidecar(archive).name, ARCHIVE + ".sha256")

    def test_sidecar_does_not_double_the_tar_component(self) -> None:
        """The regression itself: `…tar.tar.zst.sha256`."""
        self.assertNotIn(".tar.tar.", bc.sidecar(Path("/backups") / ARCHIVE).name)

    def test_sidecar_stays_next_to_its_archive(self) -> None:
        archive = Path("/somewhere/else") / ARCHIVE
        self.assertEqual(bc.sidecar(archive).parent, archive.parent)

    def test_pruning_finds_the_sidecar_that_was_written(self) -> None:
        """Write one the way the script writes it, delete it the way the script
        prunes it. A mismatch orphans checksums for archives that no longer
        exist, which is how the bug would have surfaced eventually."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / ARCHIVE
            archive.write_bytes(b"not really an archive")
            bc.sidecar(archive).write_text("digest  " + ARCHIVE + "\n")

            archive.unlink()
            bc.sidecar(archive).unlink(missing_ok=True)

            self.assertEqual(sorted(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
