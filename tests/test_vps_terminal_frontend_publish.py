"""Isolated static frontend publication regressions; no VPS/PAPER/HTTP."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import vps_terminal_frontend_publish as ui


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class StaticFrontendPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "installed"
        self.root.mkdir()
        self.webroot = self.base / "web"
        self.webroot.mkdir()
        (self.webroot / "assets").mkdir()
        self.old = b"<html>old app</html>"
        (self.webroot / "index.html").write_bytes(self.old)
        (self.webroot / "assets" / "index-old.js").write_bytes(b"owner-old")
        self.tx = self.base / "transactions"
        self.tx.mkdir(mode=0o700)
        self.sha = "a" * 40
        (self.tx / self.sha).mkdir(mode=0o700)
        self.bundle = self.base / "dist"
        (self.bundle / "assets").mkdir(parents=True)
        self.html = b'<script type="module" src="/assets/index-new.js"></script>'
        self.js = "Сделок за день".encode("utf-8")
        self._seal(self.sha)

    def _seal(self, sha):
        (self.bundle / "index.html").write_bytes(self.html)
        (self.bundle / "assets" / "index-new.js").write_bytes(self.js)
        manifest = {"source_sha": sha, "files": {
            "index.html": digest(self.html),
            "assets/index-new.js": digest(self.js),
        }}
        (self.bundle / "frontend-release.json").write_text(
            json.dumps(manifest), encoding="utf-8")

    def publish(self, **overrides):
        opts = dict(bundle=self.bundle, root=self.root, webroot=self.webroot,
                    expected_index_sha256=digest(self.old),
                    transactions=self.tx, uid=os.geteuid(),
                    release_verifier=lambda _: self.sha)
        opts.update(overrides)
        return ui.publish_frontend(self.sha, **opts)

    def test_first_adoption_is_pinned_and_preserves_original_and_old_assets(self):
        self.assertTrue(self.publish().startswith("FRONTEND_READY"))
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.html)
        self.assertEqual((self.webroot / "assets" / "index-new.js").read_bytes(), self.js)
        self.assertEqual((self.webroot / "assets" / "index-old.js").read_bytes(), b"owner-old")
        self.assertEqual((self.tx / self.sha / "frontend-previous-index.html").read_bytes(), self.old)
        self.assertTrue(self.publish(expected_index_sha256=None).startswith("FRONTEND_READY"))

    def test_successor_release_uses_existing_receipt_without_a_new_owner_pin(self):
        self.assertTrue(self.publish().startswith("FRONTEND_READY"))
        successor = "b" * 40
        (self.tx / successor).mkdir(mode=0o700)
        second = self.base / "next-dist"
        (second / "assets").mkdir(parents=True)
        second_html = b'<script type="module" src="/assets/index-second.js"></script>'
        second_js = b"successor frontend"
        (second / "index.html").write_bytes(second_html)
        (second / "assets" / "index-second.js").write_bytes(second_js)
        (second / "frontend-release.json").write_text(json.dumps({
            "source_sha": successor,
            "files": {
                "index.html": digest(second_html),
                "assets/index-second.js": digest(second_js),
            },
        }), encoding="utf-8")
        opts = dict(bundle=second, root=self.root, webroot=self.webroot,
                    transactions=self.tx, uid=os.geteuid(),
                    release_verifier=lambda _: successor)
        self.assertTrue(ui.publish_frontend(successor, **opts).startswith("FRONTEND_READY"))
        self.assertEqual((self.tx / successor / "frontend-previous-index.html").read_bytes(),
                         self.html)
        self.assertEqual((self.webroot / "index.html").read_bytes(), second_html)
        self.assertEqual((self.webroot / "assets" / "index-new.js").read_bytes(), self.js)
        receipt = json.loads((self.webroot / ui.RECEIPT).read_text())
        self.assertEqual(receipt["source_sha"], successor)
        self.assertEqual(receipt["previous_index_sha256"], digest(self.html))
        self.assertTrue(ui.publish_frontend(successor, **opts).startswith("FRONTEND_READY"))

    def test_same_release_missing_backup_still_blocks(self):
        self.assertTrue(self.publish().startswith("FRONTEND_READY"))
        (self.tx / self.sha / "frontend-previous-index.html").unlink()
        with self.assertRaisesRegex(
            ui.FrontendPublishBlocked, "frontend_previous_index_backup_missing"
        ):
            self.publish(expected_index_sha256=None)

    def test_unpinned_first_adoption_is_no_op(self):
        with self.assertRaisesRegex(ui.FrontendPublishBlocked, "first_frontend_adoption"):
            self.publish(expected_index_sha256=None)
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.old)
        self.assertFalse((self.webroot / "assets" / "index-new.js").exists())

    def test_wrong_installed_sha_fails_before_webroot_change(self):
        with self.assertRaisesRegex(ui.FrontendPublishBlocked, "frontend_backend_release_mismatch"):
            self.publish(release_verifier=lambda _: "b" * 40)
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.old)

    def test_tampered_or_mismatched_bundle_fails_before_webroot_change(self):
        (self.bundle / "assets" / "index-new.js").write_bytes(b"tampered")
        with self.assertRaisesRegex(ui.FrontendPublishBlocked, "frontend_bundle_content_mismatch"):
            self.publish()
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.old)

    def test_asset_collision_never_overwrites_owner_file(self):
        (self.webroot / "assets" / "index-new.js").write_bytes(b"other")
        with self.assertRaisesRegex(ui.FrontendPublishBlocked, "frontend_asset_collision"):
            self.publish()
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.old)
        self.assertEqual((self.webroot / "assets" / "index-new.js").read_bytes(), b"other")

    def test_unknown_webroot_index_fails_closed(self):
        (self.webroot / "index.html").write_bytes(b"new owner page")
        with self.assertRaisesRegex(ui.FrontendPublishBlocked, "frontend_index_changed"):
            self.publish()
        self.assertFalse((self.webroot / "assets" / "index-new.js").exists())

    def test_interruption_after_asset_copy_before_index_switch_resumes_without_delete(self):
        original = ui._atomic_file
        def fail_on_index(path, data, mode=0o644):
            if path.name == "index.html":
                raise OSError("simulated power loss")
            return original(path, data, mode)
        with patch.object(ui, "_atomic_file", side_effect=fail_on_index):
            with self.assertRaisesRegex(OSError, "simulated power loss"):
                self.publish()
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.old)
        self.assertEqual((self.webroot / "assets" / "index-new.js").read_bytes(), self.js)
        self.assertTrue(self.publish().startswith("FRONTEND_READY"))
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.html)

    def test_bundle_symlink_cannot_escape_release_assets(self):
        (self.bundle / "assets" / "external.js").symlink_to(self.webroot / "index.html")
        with self.assertRaisesRegex(ui.FrontendPublishBlocked, "symlink"):
            self.publish()
        self.assertEqual((self.webroot / "index.html").read_bytes(), self.old)


if __name__ == "__main__":
    unittest.main()
