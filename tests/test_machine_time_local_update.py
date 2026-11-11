"""No-network regressions for the opt-in, lightweight local updater."""
from __future__ import annotations

from hashlib import sha256
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch

from research.local_replay_viewer import local_update, server


class UpdateMetadataTests(TestCase):
    def test_installed_sha_requires_manifest_and_matching_server_hash(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(local_update.installed_build(root)["build_status"], "UNVERIFIED")
            (root / "server.py").write_bytes(b"fixed exact source")
            record = {
                "schema": "MACHINE_TIME_BUILD_V1",
                "source_sha": "a" * 40,
                "server_sha256": sha256((root / "server.py").read_bytes()).hexdigest(),
            }
            (root / local_update.BUILD_MANIFEST).write_text(json.dumps(record))
            self.assertEqual(local_update.installed_build(root), {
                "installed_sha": "a" * 40,
                "build_status": "MANIFEST_HASH_MATCH",
            })
            (root / "server.py").write_bytes(b"modified source")
            self.assertEqual(local_update.installed_build(root)["build_status"], "UNVERIFIED")

    def test_releases_are_checked_only_via_bounded_explicit_call(self):
        calls = []
        body = json.dumps([{
            "draft": False, "prerelease": False, "tag_name": "machine-time-" + "b" * 40,
            "assets": [{
                "name": "machine-time-windows.zip", "state": "uploaded",
                "size": 24000, "digest": "sha256:" + "c" * 64,
            }],
        }]).encode()

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, limit):
                self.assert_limit = limit
                return body

        def open_url(request, timeout):
            calls.append((request.full_url, timeout))
            return Response()

        self.assertEqual(calls, [])
        result = local_update.check_github_release("a" * 40, open_url=open_url)
        self.assertEqual(result["status"], "PUBLISHED_CANDIDATE")
        self.assertEqual(calls, [(local_update.GITHUB_RELEASES, 8)])
        self.assertEqual(local_update.check_github_release("b" * 40, open_url=open_url)["status"], "CURRENT")

    def test_rejects_unrelated_unsigned_or_oversized_assets(self):
        raw = [{
            "draft": False, "prerelease": False,
            "tag_name": "machine-time-" + "a" * 40,
            "assets": [{"name": "machine-time-windows.zip", "state": "uploaded",
                        "size": 10, "digest": ""}],
        }]
        self.assertEqual(local_update._parse_releases(raw, None)["status"], "NO_COMPATIBLE_RELEASE")
        self.assertEqual(local_update._parse_releases([{
            **raw[0], "assets": [{**raw[0]["assets"][0],
                                   "digest": "sha256:" + "a" * 64,
                                   "size": local_update.MAX_ASSET_SIZE + 1}],
        }], None)["status"], "NO_COMPATIBLE_RELEASE")


class LocalUpdateHttpTests(TestCase):
    def test_local_version_and_opt_in_check_keep_vps_unreachable(self):
        app = ThreadingHTTPServer(("127.0.0.1", 0), server.handler_factory())
        worker = Thread(target=app.serve_forever, daemon=True)
        worker.start()
        try:
            port = app.server_address[1]
            conn = HTTPConnection("127.0.0.1", port, timeout=4)
            with patch.object(server.local_update, "check_github_release",
                              return_value={"status": "NO_COMPATIBLE_RELEASE"}) as github:
                conn.request("GET", "/local-replay/app-version")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn("build_status", json.loads(response.read()))
                self.assertEqual(github.call_count, 0)
                conn.request("POST", "/local-replay/update/check")
                response = conn.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
                self.assertEqual(github.call_count, 0)
                conn.request("POST", "/local-replay/update/check",
                             headers={"Origin": f"http://127.0.0.1:{port}",
                                      "X-Local-Update-Check": "1"})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["status"], "NO_COMPATIBLE_RELEASE")
                self.assertEqual(github.call_count, 1)
            conn.close()
        finally:
            app.shutdown()
            worker.join(timeout=4)
            app.server_close()
