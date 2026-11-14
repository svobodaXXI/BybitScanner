"""Offline, per-user native filmstrip URI tests; no Windows registry mutation."""
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import patch

from research.local_replay_viewer import windows_protocol as w


class FakeKey:
    def __init__(self, registry, path):
        self.registry, self.path = registry, path

    def __enter__(self): return self

    def __exit__(self, *_): return None


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    REG_SZ = 1
    REG_DWORD = 4
    KEY_READ = 0x1
    KEY_WRITE = 0x2

    def __init__(self):
        self.keys = {}

    def CreateKeyEx(self, _, path):
        self.keys.setdefault(path, {})
        return FakeKey(self, path)

    def OpenKey(self, _, path, *args):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return FakeKey(self, path)

    def SetValueEx(self, key, name, reserved, kind, value):
        self.keys[key.path][name] = value

    def QueryValueEx(self, key, name):
        return self.keys[key.path][name], self.REG_SZ

    def DeleteValue(self, key, name):
        del self.keys[key.path][name]


class FilmstripProtocolTests(TestCase):
    EPISODE = "te_" + "a" * 24

    def test_exact_episode_only_no_url_or_command_injection(self):
        self.assertEqual(w.episode_from_url(
            "bybitscanner-simulator://open?episode=" + self.EPISODE
        ), self.EPISODE)
        for value in [
            "", "https://127.0.0.1/?episode=" + self.EPISODE,
            "bybitscanner-simulator://evil?episode=" + self.EPISODE,
            "bybitscanner-simulator://open/path?episode=" + self.EPISODE,
            "bybitscanner-simulator://open?episode=" + self.EPISODE + "&cmd=stop",
            "bybitscanner-simulator://open?episode=" + self.EPISODE + "#fragment",
            "bybitscanner-simulator://open?episode=te_" + "A" * 24,
            "bybitscanner-simulator://open?episode=%74e_" + "a" * 24,
            "bybitscanner-simulator://open?episode=../../PAPER",
            "bybitscanner-simulator://open?episode=" + self.EPISODE + "\\n--execute",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                w.episode_from_url(value)

    def test_only_per_user_handler_and_same_release_live_loopback(self):
        reg = FakeRegistry()
        script, python = Path(__file__).resolve(), Path(sys.executable).resolve()
        class Reply:
            status = 200
            headers = {"Server": "MachineTimeLocal/1.0 Python"}
            def __enter__(self): return self
            def __exit__(self, *_): pass

        with patch.object(w, "_registry", return_value=reg):
            self.assertTrue(w.install_per_user_handler(script, python))
            self.assertIn(w.CLASSES_KEY, reg.keys)
            command = reg.keys[w.CLASSES_KEY + r"\\shell\\open\\command"][""]
            self.assertEqual(command, f'"{python}" -B "{script}" --open-url "%1"')
            self.assertNotIn("HKEY_LOCAL_MACHINE", repr(reg.keys))
            w.set_active_viewer(script, 44944)
            with patch.object(w, "urlopen", return_value=Reply()) as hit:
                self.assertEqual(w.active_viewer_port(script), 44944)
                self.assertEqual(hit.call_args.args[0], "http://127.0.0.1:44944/replay.html")
                self.assertIsNone(w.active_viewer_port(Path("/other/server.py")))
            w.clear_active_viewer(script, 44944)
            self.assertNotIn("Port", reg.keys[w.APP_KEY])
