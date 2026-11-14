"""Offline secure Windows per-user pairing proof; no registry or real DPAPI."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import quote
import json

from research.local_replay_viewer import paired_device as pair


class PairingTests(TestCase):
    ORIGIN = "https://statistics.example.test"
    TOKEN = "X" * 64
    DEVICE = "owner-pc"

    def uri(self, **changes):
        values = {
            "device_id": self.DEVICE,
            "token": self.TOKEN,
            "origin": self.ORIGIN,
            **changes,
        }
        return "bybitscanner-simulator://pair?" + "&".join(
            f"{key}={quote(value, safe='')}" for key, value in values.items()
        )

    def test_exact_pairing_uri_only_https_no_duplicate_or_commands(self):
        self.assertEqual(pair.parse_pairing_uri(self.uri()),
                         (self.DEVICE, self.TOKEN, self.ORIGIN))
        for invalid in [
            "", "bybitscanner-simulator://open?episode=te_" + "a" * 24,
            self.uri(origin="http://statistics.example.test"),
            self.uri(origin="https://user:pass@statistics.example.test"),
            self.uri(origin="https://statistics.example.test/untrusted"),
            self.uri(device_id="owner-pc;cmd"),
            self.uri(token="abc"),
            self.uri() + "&cmd=run",
            self.uri() + "&token=" + self.TOKEN,
            self.uri() + "#fragment",
            self.uri().replace("://pair?", "://evil?"),
            self.uri() + "\n--script=bad",
            "bybitscanner-simulator://pair?token=%ZZ&origin=https%3A%2F%2Fevil.test&device_id=owner-pc",
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                pair.parse_pairing_uri(invalid)

    def test_consent_required_before_any_credential_write(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / "protected.dpapi"
            with patch.object(pair, "_is_windows", return_value=True), \
                 patch.object(pair, "_storage", return_value=target), \
                 patch.object(pair, "_crypt", return_value=b"cipher"):
                self.assertFalse(pair.accept_pairing_url(self.uri(), confirm=lambda *_: False))
                self.assertFalse(target.exists())
                approved = []
                def confirm(origin, device):
                    approved.append((origin, device))
                    return True
                self.assertTrue(pair.accept_pairing_url(self.uri(), confirm=confirm))
                self.assertEqual(approved, [(self.ORIGIN, self.DEVICE)])
                self.assertEqual(target.read_bytes(), b"cipher")
                self.assertNotIn(self.TOKEN.encode(), target.read_bytes())
                self.assertFalse(target.with_name(target.name + ".new").exists())

    def test_persisted_config_is_dpapi_encrypted_and_schema_checked(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / "protected.dpapi"
            calls = []
            def fake_dpapi(raw, *, decrypt):
                calls.append(decrypt)
                return raw[5:] if decrypt else b"SEAL:" + raw
            with patch.object(pair, "_is_windows", return_value=True), \
                 patch.object(pair, "_storage", return_value=target), \
                 patch.object(pair, "_crypt", side_effect=fake_dpapi):
                self.assertTrue(pair.accept_pairing_url(self.uri(), confirm=lambda *_: True))
                self.assertTrue(target.read_bytes().startswith(b"SEAL:"))
                self.assertNotIn(self.TOKEN.encode(), target.read_bytes()[:5])
                loaded = pair.load_pairing()
                self.assertEqual(loaded, {
                    "schema": 1, "device_id": self.DEVICE,
                    "token": self.TOKEN, "origin": self.ORIGIN,
                })
                self.assertEqual(calls, [False, True])
                target.write_bytes(b"SEAL:" + json.dumps({
                    "schema": 1, "device_id": "owner-pc", "token": self.TOKEN,
                    "origin": "https://evil.test", "extra": "cmd",
                }).encode())
                with self.assertRaises(OSError):
                    pair.load_pairing()

    def test_receiver_hot_starts_only_after_explicit_pairing(self):
        read = [None, {
            "schema": 1, "device_id": self.DEVICE,
            "token": self.TOKEN, "origin": self.ORIGIN,
        }]
        made = []
        class Stop:
            n = 0
            def is_set(self): return self.n >= 3
            def wait(self, delay):
                self.n += 1
                return self.is_set()
        class FakeReceiver:
            def __init__(self, **kwargs):
                made.append(("init", kwargs["origin"], kwargs["device_id"]))
            def poll_once(self): made.append(("poll",))
        with patch.object(pair, "load_pairing", side_effect=lambda: read.pop(0) if read else {
                "schema": 1, "device_id": self.DEVICE,
                "token": self.TOKEN, "origin": self.ORIGIN,
            }), patch.object(pair, "PairedEpisodeReceiver", FakeReceiver):
            pair.run_paired_receiver(Stop(), local_archive=Path("."),
                                     open_episode=lambda _: True, poll_interval=0)
        self.assertEqual(made, [
            ("init", self.ORIGIN, self.DEVICE), ("poll",), ("poll",),
        ])
