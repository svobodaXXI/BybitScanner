"""Bounded offline checks for the immutable Wedge BE owner configuration change."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest

from tools.vps_wedge_be_activation import (
    FLAG, WedgeBEBlocked, _no_be_key, _read_env, _unchanged, _write_once,
)


@unittest.skipUnless(os.name == "posix", "Linux root-owned config semantics")
class WedgeBEConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.env"
        self.path.write_bytes(b"BYBITSCANNER_PAPER_MODE=paper\n")
        self.uid = os.geteuid()
        self.original, self.info = _read_env(self.path, required=True, uid=self.uid)

    def test_create_once_preserves_original_backup(self):
        _write_once(self.path, self.original, self.info, uid=self.uid)
        self.assertEqual(
            self.path.read_bytes(),
            self.original + FLAG + b"=1\n",
        )
        backups = list(self.path.parent.glob("paper.env.before-wedge-be-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.assertFalse(_no_be_key(self.path.read_bytes()))

    def test_conflicting_flag_refuses_without_write(self):
        self.path.write_bytes(self.original + FLAG + b"=0\n")
        with self.assertRaises(WedgeBEBlocked):
            _write_once(self.path, self.original, self.info, uid=self.uid)
        self.assertEqual(list(self.path.parent.glob("paper.env.before-wedge-be-*")), [])
        self.assertIn(FLAG + b"=0", self.path.read_bytes())

    def test_inode_change_refuses(self):
        swapped = self.path.parent / "swapped.env"
        swapped.write_bytes(self.original)
        os.replace(swapped, self.path)
        self.assertFalse(_unchanged(self.path, self.original, self.info, self.uid))
        with self.assertRaises(WedgeBEBlocked):
            _write_once(self.path, self.original, self.info, uid=self.uid)

    def test_symlink_refused(self):
        self.path.unlink()
        self.path.symlink_to(self.path.parent / "missing.env")
        with self.assertRaises(WedgeBEBlocked):
            _read_env(self.path, required=True, uid=self.uid)

    def test_duplicate_or_commented_key_refused(self):
        self.assertFalse(_no_be_key(b"# " + FLAG + b"=1\n"))
        self.assertFalse(_no_be_key(FLAG + b"=0\n"))
        self.assertTrue(_no_be_key(b"BYBITSCANNER_PAPER_MODE=paper\n"))


if __name__ == "__main__":
    unittest.main()
