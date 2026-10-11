"""SwordCounter S4: "MetaScalp + Мечи" launcher, single instance guard, desktop shortcut script.

Offline: processes are faked (MetaScalp is never started), no API keys, no network. The
shortcut script is exercised only against a temporary directory standing in for the Desktop.
"""

import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from tools.SwordCounter import launcher as lc
from tools.SwordCounter import single_instance as si

REPO = Path(__file__).resolve().parents[1]
SECRET_KEY = "KEY-sentinel-ABCDEF123456"
SECRET_VALUE = "TOPSECRET-sentinel-0123456789abcdef"
ENV = {"SWORDCOUNTER_BYBIT_API_KEY": SECRET_KEY, "SWORDCOUNTER_BYBIT_API_SECRET": SECRET_VALUE,
       "PATH": "C:\\Windows", "LOCALAPPDATA": "C:\\Users\\x\\AppData\\Local"}
ROOT = Path(r"C:\repo")
PYTHONW = Path(r"C:\repo\venv\Scripts\pythonw.exe")
EXE = Path(r"C:\Users\x\AppData\Local\MetaScalp\current\MetaScalp.exe")


class FakeProcess:
    def __init__(self, record):
        self.pid = 4242
        self._record = record

    def wait(self, *a, **k):
        raise AssertionError("the launcher must never wait for a child")

    communicate = poll = wait


class FakePopen:
    def __init__(self, fail_for=()):
        self.calls = []
        self.fail_for = fail_for

    def __call__(self, args, **kwargs):
        self.calls.append({"args": [str(a) for a in args], **kwargs})
        if any(str(args[0]).endswith(name) for name in self.fail_for):
            raise OSError("cannot start")
        return FakeProcess(self.calls[-1])


def deps(*, metascalp=False, sword=False, popen=None, environ=None):
    popen = popen or FakePopen()
    return lc.Deps(
        metascalp_running=lambda: metascalp, swordcounter_running=lambda: sword,
        popen=popen, environ=dict(ENV if environ is None else environ),
    ), popen


def run(d, dry_run=False):
    out = io.StringIO()
    code = lc.launch(ROOT, PYTHONW, EXE, d, dry_run=dry_run, out=out.write)
    return code, out.getvalue()


class FindMetaScalpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.exe = Path(self.tmp.name) / "MetaScalp" / "current" / "MetaScalp.exe"
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b"MZ")

    def test_default_location_is_the_installed_velopack_path(self):
        found = lc.find_metascalp(environ={"LOCALAPPDATA": self.tmp.name})
        self.assertEqual(found, self.exe)

    def test_explicit_path_and_environment_override_are_accepted(self):
        self.assertEqual(lc.find_metascalp(str(self.exe), environ={}), self.exe)
        self.assertEqual(lc.find_metascalp(environ={lc.METASCALP_ENV: str(self.exe)}), self.exe)

    def test_an_unknown_path_is_a_blocker_never_a_guess(self):
        with self.assertRaises(lc.MetaScalpNotFound):
            lc.find_metascalp(environ={"LOCALAPPDATA": str(Path(self.tmp.name) / "nowhere")})
        with self.assertRaises(lc.MetaScalpNotFound):
            lc.find_metascalp(environ={})
        other = Path(self.tmp.name) / "notepad.exe"
        other.write_bytes(b"MZ")
        for bad in (other, self.exe.parent, Path(self.tmp.name) / "missing" / "MetaScalp.exe"):
            with self.subTest(bad=str(bad)), self.assertRaises(lc.MetaScalpNotFound):
                lc.find_metascalp(str(bad), environ={})


class EntryPointTests(unittest.TestCase):
    def test_unknown_metascalp_location_starts_nothing(self):
        d, popen = deps()
        out = io.StringIO()
        with mock.patch.object(lc, "live_deps", return_value=d), \
                mock.patch.object(lc, "find_metascalp", side_effect=lc.MetaScalpNotFound("unknown")), \
                mock.patch.object(lc.sys, "stdout", out):
            self.assertEqual(lc.main([]), lc.EXIT_BLOCKED)
        self.assertEqual(popen.calls, [])
        self.assertIn("unknown", out.getvalue())

    def test_dry_run_entry_point_starts_nothing(self):
        d, popen = deps()
        with mock.patch.object(lc, "live_deps", return_value=d), \
                mock.patch.object(lc, "find_metascalp", return_value=EXE), \
                mock.patch.object(lc.sys, "stdout", io.StringIO()):
            self.assertEqual(lc.main(["--dry-run"]), 0)
        self.assertEqual(popen.calls, [])


class ProcessProbeTests(unittest.TestCase):
    def probe(self, stdout="", returncode=0, error=None):
        def fake_run(cmd, **kwargs):
            self.assertEqual(cmd[0].lower(), "tasklist")
            self.assertNotIn("/s", [c.lower() for c in cmd])  # local machine only
            if error:
                raise error
            return subprocess.CompletedProcess(cmd, returncode, stdout, "")
        return lc.is_metascalp_running(run=fake_run)

    def test_detects_a_running_metascalp_by_image_name(self):
        self.assertTrue(self.probe('"MetaScalp.exe","1234","Console","1","90,000 K"\n'))
        self.assertTrue(self.probe('"metascalp.exe","1234","Console","1","90,000 K"\r\n'))

    def test_no_match_means_not_running(self):
        self.assertFalse(self.probe("INFO: No tasks are running which match the specified criteria.\n"))
        self.assertFalse(self.probe('"MetaScalpHelper.exe","1","Console","1","1 K"\n'))

    def test_an_unreadable_process_list_is_unknown_not_false(self):
        self.assertIsNone(self.probe(returncode=1))
        self.assertIsNone(self.probe(error=OSError("no tasklist")))
        self.assertIsNone(self.probe(error=subprocess.TimeoutExpired("tasklist", 1)))


class LaunchTests(unittest.TestCase):
    def test_neither_running_starts_both_as_independent_detached_processes(self):
        d, popen = deps()
        code, text = run(d)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(popen.calls), 2)
        meta, sword = popen.calls
        self.assertEqual(meta["args"], [str(EXE)])
        self.assertEqual(Path(meta["cwd"]), EXE.parent)
        self.assertEqual(sword["args"], [str(PYTHONW), "-m", "tools.SwordCounter"])
        self.assertEqual(Path(sword["cwd"]), ROOT)
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        for call in popen.calls:
            self.assertEqual(call["creationflags"] & flags, flags)
            self.assertNotIn("shell", call)  # never through a shell
            self.assertIs(call["close_fds"], True)
            self.assertIs(call["stdin"], subprocess.DEVNULL)

    def test_a_running_metascalp_is_not_started_twice(self):
        d, popen = deps(metascalp=True)
        code, text = run(d)
        self.assertEqual(code, 0)
        self.assertEqual([c["args"][0] for c in popen.calls], [str(PYTHONW)])
        self.assertIn("MetaScalp", text)

    def test_a_running_swordcounter_is_not_started_twice(self):
        d, popen = deps(sword=True)
        self.assertEqual(run(d)[0], 0)
        self.assertEqual([c["args"] for c in popen.calls], [[str(EXE)]])

    def test_both_running_starts_nothing(self):
        d, popen = deps(metascalp=True, sword=True)
        self.assertEqual(run(d)[0], 0)
        self.assertEqual(popen.calls, [])

    def test_unknown_metascalp_state_never_risks_a_second_instance(self):
        d, popen = deps(metascalp=None)
        code, text = run(d)
        self.assertNotEqual(code, 0)
        self.assertEqual([c["args"][0] for c in popen.calls], [str(PYTHONW)])
        self.assertIn("MetaScalp", text)

    def test_one_failing_start_does_not_stop_the_other(self):
        d, popen = deps(popen=FakePopen(fail_for=("MetaScalp.exe",)))
        code, text = run(d)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(popen.calls), 2)
        d2, popen2 = deps(popen=FakePopen(fail_for=("pythonw.exe",)))
        code2, _ = run(d2)
        self.assertNotEqual(code2, 0)
        self.assertEqual(len(popen2.calls), 2)

    def test_dry_run_starts_nothing_and_reports_the_plan(self):
        d, popen = deps()
        code, text = run(d, dry_run=True)
        self.assertEqual((code, popen.calls), (0, []))
        self.assertIn(str(EXE), text)
        self.assertIn("tools.SwordCounter", text)
        self.assertIn("DRY-RUN", text)

    def test_api_keys_never_travel_on_a_command_line_or_reach_metascalp(self):
        d, popen = deps()
        code, text = run(d)
        everything = "\n".join(" ".join(c["args"]) + str(c["cwd"]) for c in popen.calls) + text
        self.assertNotIn(SECRET_VALUE, everything)
        self.assertNotIn(SECRET_KEY, everything)
        self.assertNotIn("SWORDCOUNTER_BYBIT", " ".join(" ".join(c["args"]) for c in popen.calls))
        meta, sword = popen.calls
        for name in lc.SECRET_ENV:
            self.assertNotIn(name, meta["env"])            # MetaScalp gets a scrubbed environment
        self.assertEqual(meta["env"]["PATH"], ENV["PATH"])
        self.assertIsNone(sword.get("env"))                # SwordCounter inherits the user environment
        self.assertEqual(ENV["SWORDCOUNTER_BYBIT_API_KEY"], SECRET_KEY)  # the source mapping is untouched

    def test_no_elevation_and_no_trading_runtime(self):
        source = Path(lc.__file__).read_text(encoding="utf-8")
        script = (REPO / "tools" / "SwordCounter" / "create_desktop_shortcut.ps1").read_text(encoding="utf-8")
        for text in (source, script):
            for forbidden in ("runas", "ShellExecute", "-Verb", "requireAdministrator", "RunAsAdministrator"):
                self.assertNotIn(forbidden.lower(), text.lower(), forbidden)
        self.assertNotRegex(source, r"(?m)^\s*(from|import)\s+(terminal|robot_|paper_|sqlite3|config)\b")
        for forbidden in ("start_robot", "stop_robot", "runtime_intent", "paper_http_server", "start_scanner"):
            self.assertNotIn(forbidden, source)


class PythonResolutionTests(unittest.TestCase):
    def test_prefers_the_windowless_interpreter_next_to_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp)
            (scripts / "python.exe").write_bytes(b"MZ")
            (scripts / "pythonw.exe").write_bytes(b"MZ")
            self.assertEqual(lc.windowless_python(scripts / "python.exe"), scripts / "pythonw.exe")
            self.assertEqual(lc.windowless_python(scripts / "pythonw.exe"), scripts / "pythonw.exe")
            (scripts / "pythonw.exe").unlink()
            self.assertEqual(lc.windowless_python(scripts / "python.exe"), scripts / "python.exe")


@unittest.skipUnless(sys.platform == "win32", "Windows named mutex")
class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.name = f"Local\\SwordCounterTest-{uuid.uuid4().hex}"

    def test_second_instance_is_refused_until_the_first_releases(self):
        first, second = si.SingleInstance(self.name), si.SingleInstance(self.name)
        self.addCleanup(first.release)
        self.addCleanup(second.release)
        self.assertFalse(si.is_running(self.name))
        self.assertTrue(first.acquire())
        self.assertTrue(si.is_running(self.name))
        self.assertFalse(second.acquire())
        first.release()
        self.assertFalse(si.is_running(self.name))
        self.assertTrue(second.acquire())

    def test_the_application_entry_point_exits_quietly_when_already_running(self):
        from tools.SwordCounter import __main__ as entry

        started = []
        busy = mock.Mock(**{"acquire.return_value": False})
        self.assertEqual(entry.main(guard=busy, run_app=lambda: started.append(1)), 0)
        self.assertEqual(started, [])
        free = mock.Mock(**{"acquire.return_value": True})
        self.assertEqual(entry.main(guard=free, run_app=lambda: started.append(1)), 0)
        self.assertEqual(started, [1])
        free.release.assert_called_once()

    def test_the_default_mutex_name_is_per_user_session(self):
        self.assertTrue(si.MUTEX_NAME.startswith("Local\\"))


@unittest.skipUnless(sys.platform == "win32", "Windows shortcut (WScript.Shell)")
class DesktopShortcutScriptTests(unittest.TestCase):
    SCRIPT = REPO / "tools" / "SwordCounter" / "create_desktop_shortcut.ps1"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.desktop = Path(self.tmp.name) / "Desktop"
        self.desktop.mkdir()
        self.pythonw = Path(self.tmp.name) / "venv" / "Scripts" / "pythonw.exe"
        self.pythonw.parent.mkdir(parents=True)
        self.pythonw.write_bytes(b"MZ")
        self.exe = Path(self.tmp.name) / "MetaScalp.exe"
        self.exe.write_bytes(b"MZ")
        self.name = "MetaScalp + " + "\u041c\u0435\u0447\u0438" + ".lnk"

    def invoke(self, *extra):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
             str(self.SCRIPT), "-RepoRoot", str(REPO), "-PythonW", str(self.pythonw),
             "-Desktop", str(self.desktop), "-MetaScalpExe", str(self.exe), *extra],
            capture_output=True, text=True, encoding="utf-8", timeout=60)

    def read_back(self, path):
        probe = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                 "$l=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK_PATH);"
                 "@($l.TargetPath,$l.Arguments,$l.WorkingDirectory,$l.IconLocation) -join '|'")
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", probe],
                             capture_output=True, text=True, encoding="utf-8", timeout=60,
                             env={**os.environ, "LNK_PATH": str(path)})
        return out.stdout.strip().split("|")

    def test_dry_run_creates_nothing(self):
        result = self.invoke("-DryRun")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(list(self.desktop.iterdir()), [])

    def test_creates_the_shortcut_with_the_verified_target_and_no_secrets(self):
        existing = self.desktop / "MetaScalp.lnk"
        existing.write_bytes(b"existing-shortcut-bytes")
        before = hashlib.sha256(existing.read_bytes()).hexdigest()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        created = self.desktop / self.name
        self.assertTrue(created.is_file(), [p.name for p in self.desktop.iterdir()])
        target, arguments, workdir, icon = self.read_back(created)

        def same(a, b):  # Windows stores long names; the temp dir may be an 8.3 short path
            return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))

        self.assertTrue(same(target, self.pythonw), (target, self.pythonw))
        self.assertEqual(arguments, "-m tools.SwordCounter.launcher")
        self.assertTrue(same(workdir, REPO), (workdir, REPO))
        self.assertTrue(same(icon.rsplit(",", 1)[0], self.exe), (icon, self.exe))
        self.assertNotIn("SWORDCOUNTER_BYBIT", arguments + target + workdir)
        self.assertEqual(hashlib.sha256(existing.read_bytes()).hexdigest(), before)  # untouched

    def test_never_overwrites_an_existing_shortcut_of_that_name(self):
        created = self.desktop / self.name
        created.write_bytes(b"owner-made")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(created.read_bytes(), b"owner-made")

    def test_refuses_a_missing_interpreter_or_repository(self):
        self.pythonw.unlink()
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual(list(self.desktop.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
