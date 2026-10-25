"""Issue #624: offline Linux prepare/validate-only path. Nothing is started, opened or connected."""

from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tools import runtime_intent, vps_check

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = (
    "terminal.runtime.paper_http_server", "terminal.runtime.paper_runtime", "terminal.persistence.sqlite_store",
    "terminal.application.robot_breakout_monitor", "main", "mirror_scanner", "telegram_monitoring",
    "pybit", "websocket", "requests",
)


def names(checks, ok=None):
    return [c.name for c in checks if ok is None or c.ok is ok]


class PrepareOnlySideEffectTests(unittest.TestCase):
    def test_full_check_imports_no_runtime_module_in_a_clean_interpreter(self):
        code = ("import socket, sys, tools.vps_check as v; "
                "socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError('stub')); "
                "v.run_checks(systemd=False); "
                f"print([m for m in {FORBIDDEN_MODULES!r} if m in sys.modules])")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "[]")

    def test_no_remote_connection_no_dns_no_sqlite_no_process_and_db_is_never_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "paper.sqlite3"
            connections = []

            def connect(address, timeout=None):
                connections.append(address)
                raise OSError("refused")

            with mock.patch.object(socket, "create_connection", connect), \
                    mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS lookup")), \
                    mock.patch.object(sqlite3, "connect", side_effect=AssertionError("SQLite opened")), \
                    mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process spawned")):
                checks = vps_check.run_checks(env={"BYBITSCANNER_PAPER_DB": str(db)}, systemd=False)
            self.assertFalse(db.exists())
            self.assertTrue(connections)
            self.assertEqual({host for host, _ in connections}, {"127.0.0.1"})
            self.assertIn("paper_db_not_transferred", names(checks, ok=True))


class SafetyEnvTests(unittest.TestCase):
    def test_live_gates_operator_token_and_standalone_switch_must_be_off(self):
        safe = vps_check.check_safety_env({}, "env")
        self.assertTrue(all(c.ok for c in safe))
        unsafe = vps_check.check_safety_env({
            "LIVE_MARKET_MUTATIONS_ENABLED": "true", "BYBITSCANNER_OPERATOR_TOKEN": "s3cr3t",
            "LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING": "50", "BYBITSCANNER_MIRROR_STANDALONE_ROBOT": "1"}, "env")
        failed = names(unsafe, ok=False)
        self.assertEqual(set(failed), {"env:LIVE_MARKET_MUTATIONS_ENABLED", "env:BYBITSCANNER_OPERATOR_TOKEN",
                                       "env:LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING",
                                       "env:BYBITSCANNER_MIRROR_STANDALONE_ROBOT"})
        token = next(c for c in unsafe if c.name == "env:BYBITSCANNER_OPERATOR_TOKEN")
        self.assertEqual(token.detail, "<set>")                                   # value never printed

    def test_the_env_template_is_paper_only_without_secrets(self):
        env = vps_check.parse_env_file(ROOT / "deploy/systemd/paper.env.example")
        self.assertTrue(all(c.ok for c in vps_check.check_safety_env(env, "template")))
        self.assertEqual(set(runtime_intent.PAPER_SAFE_BACKEND_ENV) - set(env), set())   # every gate listed
        secrets = {k: v for k, v in env.items() if vps_check.SECRET_KEY.search(k) and v}
        self.assertEqual(secrets, {})

    def test_paper_db_identity_is_the_bootstrap_identity_and_an_existing_db_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "paper.sqlite3"
            env = {"BYBITSCANNER_PAPER_DB": str(db)}
            check = vps_check.check_paper_db(ROOT, env)[0]
            self.assertTrue(check.ok)
            self.assertIn(runtime_intent.expected_database_identity(ROOT, env)[:16], check.detail)
            Path(f"{db}-wal").write_bytes(b"")
            self.assertFalse(vps_check.check_paper_db(ROOT, env)[0].ok)


class UnitAndNginxTests(unittest.TestCase):
    def test_repository_units_cannot_be_enabled_never_restart_and_run_paper_entrypoints(self):
        checks = vps_check.check_repo_units(ROOT)
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(c.ok for c in checks), checks)
        backend = (ROOT / "deploy/systemd/bybitscanner-paper-backend.service").read_text(encoding="utf-8")
        self.assertIn("ExecStartPre=/opt/BybitScanner/.venv/bin/python -m tools.vps_check", backend)
        self.assertIn("--pre-start", backend)

    def test_an_enableable_or_restarting_unit_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / vps_check.UNIT_DIR).mkdir(parents=True)
            for unit in vps_check.UNITS:
                shutil.copy(ROOT / vps_check.UNIT_DIR / unit, root / vps_check.UNIT_DIR / unit)
            backend = root / vps_check.UNIT_DIR / "bybitscanner-paper-backend.service"
            backend.write_text(backend.read_text(encoding="utf-8").replace("Restart=no", "Restart=always")
                               + "\n[Install]\nWantedBy=multi-user.target\n", encoding="utf-8")
            failed = [c for c in vps_check.check_repo_units(root) if not c.ok]
            self.assertEqual(len(failed), 1)
            self.assertIn("[Install]", failed[0].detail)
            self.assertIn("Restart=always", failed[0].detail)

    def test_installed_units_must_be_disabled_and_inactive(self):
        def run_with(enabled, active):
            def run(argv, **kwargs):
                return SimpleNamespace(stdout=enabled if argv[1] == "is-enabled" else active)
            return vps_check.check_installed_units(run=run, which=lambda name: "/bin/systemctl")

        self.assertTrue(all(c.ok for c in run_with("static", "inactive")))
        self.assertFalse(any(c.ok for c in run_with("enabled", "inactive")))
        self.assertFalse(any(c.ok for c in run_with("static", "active")))
        self.assertFalse(vps_check.check_installed_units(which=lambda name: None)[0].ok)

    def test_terminal_nginx_is_loopback_only(self):
        self.assertTrue(vps_check.check_nginx(ROOT)[0].ok)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / vps_check.NGINX_LOOPBACK
            target.parent.mkdir(parents=True)
            target.write_text((ROOT / vps_check.NGINX_LOOPBACK).read_text(encoding="utf-8")
                              .replace("listen 127.0.0.1:8080;", "listen 80;"), encoding="utf-8")
            self.assertFalse(vps_check.check_nginx(Path(tmp))[0].ok)

    def test_pre_start_gate_keeps_live_and_port_checks_but_not_prepare_only_ones(self):
        with mock.patch.object(socket, "create_connection", side_effect=OSError("refused")):
            checks = vps_check.run_checks(env={"LIVE_MAINNET_AUTHORIZED": "true"}, systemd=False, pre_start=True)
        self.assertIn("process_env:LIVE_MAINNET_AUTHORIZED", names(checks, ok=False))
        self.assertIn("port_8765_free", names(checks, ok=True))
        self.assertNotIn("paper_db_not_transferred", names(checks))
        self.assertNotIn("nginx_loopback", names(checks))

    def test_a_listening_backend_port_fails_the_check(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        self.assertFalse(vps_check.check_ports(ports=(port,))[0].ok)


class RuntimeIntentLinuxTests(unittest.TestCase):
    def test_linux_bootstrap_never_spawns_and_sends_no_intent(self):
        posts = []
        with mock.patch.object(runtime_intent.os, "name", "posix"), \
                mock.patch.object(runtime_intent.subprocess, "Popen", side_effect=AssertionError("spawned")):
            with self.assertRaisesRegex(OSError, "owned by systemd"):
                runtime_intent.spawn_console(["x"], ROOT)
            bootstrap = runtime_intent.RuntimeIntentBootstrap(
                root=ROOT, env={}, get=lambda url, timeout: (_ for _ in ()).throw(runtime_intent.Unreachable()),
                post=lambda url, payload, timeout: posts.append(url), sleep=lambda s: None)
            result = bootstrap.execute("ALL")
        self.assertEqual(result.outcome, runtime_intent.OUTCOME_FAILED)
        self.assertIn("owned by systemd", result.message)
        self.assertEqual(posts, [])

    def test_windows_console_spawn_is_unchanged(self):
        with mock.patch.object(runtime_intent.os, "name", "nt"), \
                mock.patch.object(runtime_intent.subprocess, "Popen") as popen:
            runtime_intent.spawn_console(["start_paper_backend.bat"], ROOT, {"A": "1"})
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["cmd.exe", "/c", "start_paper_backend.bat"])
        self.assertEqual(kwargs["env"], {"A": "1"})


if __name__ == "__main__":
    unittest.main()
