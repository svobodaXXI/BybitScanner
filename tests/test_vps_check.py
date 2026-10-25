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
VENV_PYTHON = "/opt/BybitScanner/venv/bin/python"
FORBIDDEN_MODULES = (
    "terminal.runtime.paper_http_server", "terminal.runtime.paper_runtime", "terminal.persistence.sqlite_store",
    "terminal.application.robot_breakout_monitor", "main", "mirror_scanner", "telegram_monitoring",
    "pybit", "websocket", "requests",
)
BACKEND = "bybitscanner-paper-backend.service"
TELEGRAM = "bybitscanner-telegram.service"


def names(checks, ok=None):
    return [c.name for c in checks if ok is None or c.ok is ok]


def repo_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


class FakeHost:
    """Read-only system answers: ``systemctl show``, ``nginx -T``, ``ss -ltn`` and installed files."""

    def __init__(self):
        self.files = {
            Path(f"/etc/systemd/system/{unit}"): repo_text(vps_check.UNIT_DIR / unit) for unit in (BACKEND, TELEGRAM)}
        self.files[vps_check.ENV_FILE] = repo_text("deploy/systemd/paper.env.example")
        self.files[vps_check.NGINX_SITE] = repo_text(vps_check.NGINX_LOOPBACK)
        self.show = {unit: {"LoadState": "loaded", "UnitFileState": "static", "ActiveState": "inactive",
                            "FragmentPath": f"/etc/systemd/system/{unit}", "DropInPaths": "",
                            "EnvironmentFiles": f"{vps_check.ENV_FILE.as_posix()} (ignore_errors=no)", "Environment": ""}
                     for unit in (BACKEND, TELEGRAM)}
        self.nginx = repo_text(vps_check.NGINX_LOOPBACK)
        self.ss = "LISTEN 0 511 127.0.0.1:8080 0.0.0.0:*\nLISTEN 0 4096 127.0.0.53%lo:53 0.0.0.0:*\n" \
                  "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n"
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[:2] == ["systemctl", "show"]:
            return SimpleNamespace(returncode=0, stdout="\n".join(f"{k}={v}" for k, v in self.show[argv[2]].items()))
        if argv[:2] == ["nginx", "-T"]:
            return SimpleNamespace(returncode=0, stdout=self.nginx)
        if argv[0] == "ss":
            return SimpleNamespace(returncode=0, stdout=self.ss)
        raise AssertionError(f"unexpected command {argv}")

    def read(self, path):
        path = Path(path)
        if path in self.files:
            return self.files[path]
        if path.is_relative_to(ROOT):
            return path.read_text(encoding="utf-8")
        raise OSError(path)


def which(name):
    return f"/usr/bin/{name}"


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
                checks, complete = vps_check.run_checks(env={"BYBITSCANNER_PAPER_DB": str(db)}, env_file=None,
                                                        systemd=False)
            self.assertFalse(complete)
            self.assertFalse(db.exists())
            self.assertEqual({host for host, _ in connections}, {"127.0.0.1"})
            self.assertIn("paper_db_not_transferred", names(checks, ok=True))


class VerdictTests(unittest.TestCase):
    def test_skipped_installed_state_is_never_ok(self):
        passing = [vps_check.Check("a", True, "")]
        self.assertEqual(vps_check.verdict(passing, complete=False), ("INCOMPLETE", 2))
        self.assertEqual(vps_check.verdict(passing, complete=True), ("OK", 0))
        self.assertEqual(vps_check.verdict(passing + [vps_check.Check("b", False, "")], True), ("FAILED", 1))

    def test_non_linux_or_no_systemd_is_incomplete(self):
        with mock.patch.object(socket, "create_connection", side_effect=OSError("refused")):
            _, complete = vps_check.run_checks(env={}, env_file=None, platform="win32")
            self.assertFalse(complete)
            _, complete = vps_check.run_checks(env={}, env_file=None, platform="linux", systemd=False)
            self.assertFalse(complete)


class SafetyEnvTests(unittest.TestCase):
    def test_live_gates_operator_token_and_standalone_switch_must_be_off(self):
        self.assertTrue(all(c.ok for c in vps_check.check_safety_env({}, "env")))
        unsafe = vps_check.check_safety_env({
            "LIVE_MARKET_MUTATIONS_ENABLED": "true", "BYBITSCANNER_OPERATOR_TOKEN": "s3cr3t",
            "LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING": "50", "BYBITSCANNER_MIRROR_STANDALONE_ROBOT": "1"}, "env")
        self.assertEqual(set(names(unsafe, ok=False)), {
            "env:LIVE_MARKET_MUTATIONS_ENABLED", "env:BYBITSCANNER_OPERATOR_TOKEN",
            "env:LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING", "env:BYBITSCANNER_MIRROR_STANDALONE_ROBOT"})
        token = next(c for c in unsafe if c.name == "env:BYBITSCANNER_OPERATOR_TOKEN")
        self.assertEqual(token.detail, "<set>")                                   # value never printed

    def test_the_env_template_is_paper_only_without_secrets_and_keeps_the_db_outside_the_repo(self):
        env = vps_check.parse_env_file(ROOT / "deploy/systemd/paper.env.example")
        self.assertTrue(all(c.ok for c in vps_check.check_safety_env(env, "template")))
        self.assertEqual(set(runtime_intent.PAPER_SAFE_BACKEND_ENV) - set(env), set())
        self.assertEqual({k: v for k, v in env.items() if vps_check.SECRET_KEY.search(k) and v}, {})
        self.assertTrue(env["BYBITSCANNER_PAPER_DB"].startswith(vps_check.STATE_DIR.as_posix() + "/"))
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_paper_db_identity_is_the_bootstrap_identity_and_an_existing_db_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "paper.sqlite3"
            env = {"BYBITSCANNER_PAPER_DB": str(db)}
            check = vps_check.check_paper_db(ROOT, env)[0]
            self.assertTrue(check.ok)
            self.assertIn(runtime_intent.expected_database_identity(ROOT, env)[:16], check.detail)
            Path(f"{db}-wal").write_bytes(b"")
            self.assertFalse(vps_check.check_paper_db(ROOT, env)[0].ok)


class RepositoryUnitTests(unittest.TestCase):
    def test_units_use_the_existing_venv_cannot_be_enabled_and_never_restart(self):
        self.assertTrue(all(c.ok for c in vps_check.check_repo_units(ROOT)))
        for unit in (BACKEND, TELEGRAM):
            text = repo_text(vps_check.UNIT_DIR / unit)
            self.assertIn(f"ExecStart={VENV_PYTHON} ", text)
            self.assertNotIn(".venv", text)
            self.assertIn("StateDirectory=bybitscanner", text)
        self.assertIn(f"ExecStartPre={VENV_PYTHON} -m tools.vps_check --pre-start", repo_text(
            vps_check.UNIT_DIR / BACKEND))

    def test_an_enableable_or_restarting_unit_fails(self):
        text = repo_text(vps_check.UNIT_DIR / BACKEND).replace("Restart=no", "Restart=always") + \
            "\n[Install]\nWantedBy=multi-user.target\n"
        problems = vps_check.unit_problems(text, "-m terminal.runtime.paper_http_server", check_interpreter=False)
        self.assertTrue(any("[Install]" in p for p in problems) and any("Restart=always" in p for p in problems))

    def test_runbook_keeps_the_branch_and_never_chowns_the_whole_repository(self):
        runbook = repo_text("DOCUMENTS/VPS_DEPLOYMENT_RUNBOOK.md").split("## Previous VPS", 1)[0]
        self.assertNotIn("checkout --detach", runbook)
        self.assertNotIn("chown -R", runbook)
        self.assertNotIn(".venv", runbook)
        self.assertIn("merge --ff-only", runbook)
        self.assertIn(VENV_PYTHON, runbook)


class InstalledStateTests(unittest.TestCase):
    def installed(self, host):
        return vps_check.check_installed_units(ROOT, run=host.run, which=which, read=host.read)

    def test_matching_installed_static_inactive_units_with_safe_effective_env_pass(self):
        with mock.patch.object(Path, "exists", lambda self: True):          # the VPS venv interpreter exists
            checks = self.installed(FakeHost())
        self.assertTrue(all(c.ok for c in checks), [c for c in checks if not c.ok])
        self.assertIn(f"effective:{BACKEND}:LIVE_MAINNET_AUTHORIZED", names(checks))

    def test_installed_mismatch_drop_in_enablement_activity_and_unsafe_effective_env_fail(self):
        cases = {
            "differs": lambda h: h.files.__setitem__(Path(f"/etc/systemd/system/{BACKEND}"),
                                                     h.files[Path(f"/etc/systemd/system/{BACKEND}")] + "# edit\n"),
            "drop-ins": lambda h: h.show[BACKEND].__setitem__("DropInPaths", "/etc/systemd/system/x.d/o.conf"),
            "UnitFileState=enabled": lambda h: h.show[BACKEND].__setitem__("UnitFileState", "enabled"),
            "ActiveState=active": lambda h: h.show[BACKEND].__setitem__("ActiveState", "active"),
            "not installed": lambda h: h.show[BACKEND].__setitem__("LoadState", "not-found"),
            "EnvironmentFiles": lambda h: h.show[BACKEND].__setitem__("EnvironmentFiles", ""),
        }
        for expected, mutate in cases.items():
            with self.subTest(expected):
                host = FakeHost()
                mutate(host)
                with mock.patch.object(Path, "exists", lambda self: True):
                    unit = next(c for c in self.installed(host) if c.name == f"installed_unit:{BACKEND}")
                self.assertFalse(unit.ok)
                self.assertIn(expected, unit.detail)
        host = FakeHost()
        host.show[BACKEND]["Environment"] = "LIVE_MARKET_MUTATIONS_ENABLED=true"
        with mock.patch.object(Path, "exists", lambda self: True):
            failed = names(self.installed(host), ok=False)
        self.assertEqual(failed, [f"effective:{BACKEND}:LIVE_MARKET_MUTATIONS_ENABLED"])

    def test_missing_interpreter_on_the_host_fails(self):
        with mock.patch.object(Path, "exists", lambda self: False):
            unit = next(c for c in self.installed(FakeHost()) if c.name == f"installed_unit:{BACKEND}")
        self.assertIn(f"interpreter {VENV_PYTHON} not found", unit.detail)

    def test_effective_nginx_must_be_loopback_only_and_the_enabled_site_must_match(self):
        host = FakeHost()
        ok = vps_check.check_installed_nginx(ROOT, run=host.run, which=which, read=host.read)
        self.assertTrue(all(c.ok for c in ok), ok)
        host.nginx += "\nserver {\n    listen 80 default_server;\n}\n"            # e.g. the default site
        public = vps_check.check_installed_nginx(ROOT, run=host.run, which=which, read=host.read)
        self.assertIn("nginx_effective_loopback_only", names(public, ok=False))
        host = FakeHost()
        host.files[vps_check.NGINX_SITE] = host.files[vps_check.NGINX_SITE].replace("127.0.0.1:8080", "8080")
        mismatch = vps_check.check_installed_nginx(ROOT, run=host.run, which=which, read=host.read)
        self.assertIn("nginx_site_matches_repo", names(mismatch, ok=False))

    def test_actual_listeners_on_guarded_ports_must_be_loopback(self):
        host = FakeHost()
        self.assertTrue(vps_check.check_listeners(run=host.run, which=which)[0].ok)
        host.ss += "LISTEN 0 511 0.0.0.0:80 0.0.0.0:*\nLISTEN 0 511 [::]:8765 [::]:*\n"
        exposed = vps_check.check_listeners(run=host.run, which=which)[0]
        self.assertFalse(exposed.ok)
        self.assertIn("0.0.0.0:80", exposed.detail)
        self.assertIn("[::]:8765", exposed.detail)

    def test_only_commands_used_are_read_only_queries(self):
        host = FakeHost()
        with mock.patch.object(Path, "exists", lambda self: True):
            self.installed(host)
        vps_check.check_installed_nginx(ROOT, run=host.run, which=which, read=host.read)
        vps_check.check_listeners(run=host.run, which=which)
        verbs = {tuple(argv[:2]) for argv in host.calls}
        self.assertEqual(verbs, {("systemctl", "show"), ("nginx", "-T"), ("ss", "-H")})

    def test_write_targets_belong_to_the_service_user_but_the_repository_does_not(self):
        owners = {vps_check.STATE_DIR: "bybitscanner", ROOT: "root",
                  **{ROOT / t: "bybitscanner" for t in vps_check.WRITE_TARGETS}}
        checks = vps_check.check_write_targets(ROOT, owner_of=lambda p: owners[p])
        self.assertTrue(all(c.ok for c in checks), checks)
        owners[ROOT] = "bybitscanner"                                              # chown -R of the repository
        self.assertIn("repository_owner_unchanged",
                      names(vps_check.check_write_targets(ROOT, owner_of=lambda p: owners[p]), ok=False))


class PreStartAndPortTests(unittest.TestCase):
    def test_pre_start_gate_keeps_live_and_port_checks_but_not_prepare_only_ones(self):
        with mock.patch.object(socket, "create_connection", side_effect=OSError("refused")):
            checks, _ = vps_check.run_checks(env={"LIVE_MAINNET_AUTHORIZED": "true"}, systemd=False,
                                             pre_start=True)
        self.assertIn("process_env:LIVE_MAINNET_AUTHORIZED", names(checks, ok=False))
        self.assertIn("port_8765_free", names(checks, ok=True))
        self.assertNotIn("paper_db_not_transferred", names(checks))

    def test_a_listening_backend_port_fails_the_check(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        self.assertFalse(vps_check.check_ports(ports=(listener.getsockname()[1],))[0].ok)

    def test_repository_nginx_is_loopback_only(self):
        self.assertTrue(vps_check.check_repo_nginx(ROOT)[0].ok)


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
