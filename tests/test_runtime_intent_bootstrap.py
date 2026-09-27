"""tools.runtime_intent desktop bootstrap with fake HTTP, process spawner and clock.

No real backend, Telegram worker, Scanner or Robot is started.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import runtime_intent
from tools.runtime_intent import (
    HttpResponse, RuntimeIntentBootstrap, Unreachable, expected_database_identity,
)

ROOT = Path(__file__).resolve().parents[1]
BACKEND = "http://127.0.0.1:8765"
BACKEND_HEALTH = BACKEND + "/api/health"
TELEGRAM_HEALTH = "http://127.0.0.1:8766/health"
INTENT_URL = BACKEND + "/api/runtime/intent"


def _response(status, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    return HttpResponse(status, raw)


class FakeWorld:
    """Scripted endpoints; a spawn makes the spawned dependency answer later."""

    def __init__(self, identity):
        self.identity = identity
        self.backend = None
        self.telegram = None
        self.after_spawn = {}
        self.spawns = []
        self.spawn_envs = []
        self.posts = []
        self.intent_reply = None
        self.now = 0.0
        self.lines = []

    def backend_health(self, **overrides):
        return _response(200, {"ok": True, "component": "paper_backend", "mode": "paper",
                               "database_identity": self.identity, **overrides})

    def telegram_health(self, status="ready", code=None, **overrides):
        return _response(code or (200 if status == "ready" else 503), {
            "component": "telegram_monitoring", "status": status,
            "database_identity": self.identity, **overrides,
        })

    def get(self, url, timeout):
        current = {BACKEND_HEALTH: self.backend, TELEGRAM_HEALTH: self.telegram}[url]
        if isinstance(current, list):
            current = current.pop(0) if len(current) > 1 else current[0]
        if current is None:
            raise Unreachable("connection refused")
        return current

    def post(self, url, payload, timeout):
        self.posts.append((url, dict(payload)))
        if isinstance(self.intent_reply, Exception):
            raise self.intent_reply
        return self.intent_reply

    def spawn(self, name, argv, cwd, env=None):
        self.spawns.append((name, list(argv)))
        self.spawn_envs.append((name, None if env is None else dict(env)))
        replacement = self.after_spawn.get(name)
        if name == "PAPER backend":
            self.backend = replacement
        else:
            self.telegram = replacement

    def sleep(self, seconds):
        self.now += seconds

    def bootstrap(self, env=None, require_telegram=True):
        return RuntimeIntentBootstrap(
            root=ROOT, env=env or {}, get=self.get, post=self.post, spawn=self.spawn,
            python="python.exe", sleep=self.sleep, monotonic=lambda: self.now,
            out=self.lines.append, require_telegram=require_telegram,
        )


UNSAFE_PARENT_ENV = {
    "BYBITSCANNER_OPERATOR_TOKEN": "t" * 64,
    "LIVE_MARKET_MUTATIONS_ENABLED": "true",
    "LIVE_MAINNET_AUTHORIZED": "true",
    "LIVE_MARKET_ACCEPTANCE_SINGLE_FLIGHT": "true",
    "LIVE_PARITY_MUTATIONS_ENABLED": "true",
    "LIVE_LIMIT_MUTATIONS_ENABLED": "TRUE",
    "LIVE_MARKET_ACCEPTANCE_NOTIONAL_CEILING": "25",
    "LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING": "10",
    "LIVE_PARITY_MUTATION_SCOPE": "full_close",
    "BYBITSCANNER_PAPER_DB": "paper_runtime.sqlite3",
    "BYBITSCANNER_PAPER_BACKEND_URL": BACKEND,
    "HTTPS_PROXY": "http://proxy.local:3128",
    "BYBITSCANNER_DEPLOYMENT_IDENTITY": "local",
    "BYBITSCANNER_IKIGAI_BOX_SIGNALS": "1",
}

EXPECTED_PAPER_SAFE_CHILD = {
    "BYBITSCANNER_OPERATOR_TOKEN": "",
    "LIVE_MARKET_MUTATIONS_ENABLED": "false",
    "LIVE_MAINNET_AUTHORIZED": "false",
    "LIVE_MARKET_ACCEPTANCE_SINGLE_FLIGHT": "false",
    "LIVE_PARITY_MUTATIONS_ENABLED": "false",
    "LIVE_LIMIT_MUTATIONS_ENABLED": "false",
    "LIVE_MARKET_ACCEPTANCE_NOTIONAL_CEILING": "0",
    "LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING": "0",
    "LIVE_PARITY_MUTATION_SCOPE": "",
}


def _converged(intent="ALL", changed=("robot:start", "scanner:start")):
    return _response(200, {
        "ok": True, "intent": intent, "changed": list(changed),
        "final": {"robot": "READY", "scanner": "RUNNING", "protection": "HEALTHY"},
        "blocked_by": [],
    })


class RuntimeIntentBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.identity = expected_database_identity(ROOT, {})
        self.world = FakeWorld(self.identity)
        self.world.backend = self.world.backend_health()
        self.world.telegram = self.world.telegram_health()
        self.world.intent_reply = _converged()

    def run_intent(self, intent="ALL"):
        return self.world.bootstrap().run(intent)

    def test_warm_backend_and_telegram_are_reused_and_one_intent_is_posted(self):
        self.assertEqual(self.run_intent("ALL"), 0)
        self.assertEqual(self.world.spawns, [])
        self.assertEqual(self.world.posts, [(INTENT_URL, {"intent": "ALL"})])
        self.assertEqual(self.world.lines[-1], (
            "READY: intent=ALL changed=robot:start,scanner:start "
            "robot=READY scanner=RUNNING protection=HEALTHY"
        ))

    def test_cold_backend_is_spawned_once_then_waited_for(self):
        self.world.backend = None
        self.world.after_spawn["PAPER backend"] = [None, None, self.world.backend_health()]
        self.assertEqual(self.run_intent(), 0)
        self.assertEqual([name for name, _ in self.world.spawns], ["PAPER backend"])
        self.assertEqual(len(self.world.posts), 1)

    def test_wrong_backend_identity_fails_before_any_spawn_or_intent(self):
        for health in (
            self.world.backend_health(database_identity="0" * 64),
            self.world.backend_health(database_identity=self.identity.upper()),
            self.world.backend_health(component="telegram_monitoring"),
            self.world.backend_health(mode="live"),
            self.world.backend_health(ok="true"),
            _response(503, {"ok": False, "error": "paper_runtime_unavailable"}),
            _response(200, b"not json"),
        ):
            with self.subTest(health=health.body):
                self.world.backend = health
                self.world.spawns.clear()
                self.world.posts.clear()
                self.assertEqual(self.run_intent(), 1)
                self.assertEqual(self.world.spawns, [])
                self.assertEqual(self.world.posts, [])

    def test_spawned_backend_with_wrong_identity_fails_closed_without_respawn(self):
        self.world.backend = None
        self.world.after_spawn["PAPER backend"] = [
            None, self.world.backend_health(database_identity="0" * 64),
        ]
        self.assertEqual(self.run_intent(), 1)
        self.assertEqual(len(self.world.spawns), 1)
        self.assertEqual(self.world.posts, [])

    def test_backend_that_never_becomes_ready_times_out_after_one_spawn(self):
        self.world.backend = None
        self.world.after_spawn["PAPER backend"] = None
        self.assertEqual(self.run_intent(), 1)
        self.assertEqual(len(self.world.spawns), 1)
        self.assertGreaterEqual(self.world.now, runtime_intent.READY_TIMEOUT_S)
        self.assertEqual(self.world.posts, [])

    def test_missing_telegram_is_spawned_once_then_waited_for(self):
        self.world.telegram = None
        self.world.after_spawn["Telegram monitoring"] = [
            None, self.world.telegram_health("not_ready", database_identity=None),
            self.world.telegram_health("ready"),
        ]
        self.assertEqual(self.run_intent(), 0)
        self.assertEqual([name for name, _ in self.world.spawns], ["Telegram monitoring"])
        self.assertEqual(len(self.world.posts), 1)

    def test_not_ready_telegram_on_its_port_is_waited_for_without_duplicate_spawn(self):
        self.world.telegram = [
            self.world.telegram_health("not_ready"),
            self.world.telegram_health("not_ready"),
            self.world.telegram_health("ready"),
        ]
        self.assertEqual(self.run_intent(), 0)
        self.assertEqual(self.world.spawns, [])

    def test_not_ready_telegram_that_never_becomes_ready_times_out_without_spawn(self):
        self.world.telegram = self.world.telegram_health("not_ready")
        self.assertEqual(self.run_intent(), 1)
        self.assertEqual(self.world.spawns, [])
        self.assertEqual(self.world.posts, [])

    def test_wrong_telegram_identity_or_foreign_port_fails_without_spawn_or_intent(self):
        missing = self.world.telegram_health("ready")
        body = json.loads(missing.body)
        del body["database_identity"]
        for health in (
            self.world.telegram_health("ready", database_identity="0" * 64),
            self.world.telegram_health("ready", database_identity=None),
            _response(200, body),
            self.world.telegram_health("not_ready", database_identity="0" * 64),
            _response(200, {"component": "something_else", "status": "ready"}),
            _response(200, b"not json"),
        ):
            with self.subTest(health=health.body):
                self.world.telegram = health
                self.world.spawns.clear()
                self.world.posts.clear()
                self.assertEqual(self.run_intent(), 1)
                self.assertEqual(self.world.spawns, [])
                self.assertEqual(self.world.posts, [])

    def test_blocked_intent_is_nonzero_and_not_retried(self):
        self.world.intent_reply = _response(409, {
            "ok": False, "intent": "ALL", "changed": ["robot:start"],
            "final": {"robot": "READY", "protection": "UNHEALTHY", "scanner": "STOPPED"},
            "blocked_by": ["ROBOT_PROTECTION_UNHEALTHY"],
        })
        self.assertEqual(self.run_intent(), 2)
        self.assertEqual(len(self.world.posts), 1)
        self.assertTrue(self.world.lines[-1].startswith(
            "BLOCKED: intent=ALL blocked_by=ROBOT_PROTECTION_UNHEALTHY"
        ))

    def test_ambiguous_or_invalid_intent_response_is_nonzero_and_not_retried(self):
        for reply in (
            TimeoutError("timed out"),
            ConnectionResetError("reset"),
            _response(503, {"ok": False, "error": "runtime_intent_unavailable"}),
            _response(400, {"ok": False, "error": "invalid_runtime_intent"}),
            _response(200, b"not json"),
            _converged(intent="SCANNER"),
            _response(409, {"ok": False, "intent": "ALL", "changed": [], "final": {},
                            "blocked_by": []}),
        ):
            with self.subTest(reply=reply):
                self.world.intent_reply = reply
                self.world.posts.clear()
                self.assertEqual(self.run_intent("ALL"), 3)
                self.assertEqual(len(self.world.posts), 1)

    def test_each_intent_is_posted_verbatim(self):
        for intent in ("SCANNER", "ROBOT", "ALL"):
            with self.subTest(intent=intent):
                self.world.posts.clear()
                self.world.intent_reply = _converged(intent=intent, changed=())
                self.assertEqual(self.run_intent(intent), 0)
                self.assertEqual(self.world.posts, [(INTENT_URL, {"intent": intent})])

    def test_unknown_intent_touches_nothing(self):
        for intent in ("all", "BOGUS", ""):
            with self.subTest(intent=intent):
                self.assertEqual(self.run_intent(intent), runtime_intent.EXIT_USAGE)
        self.assertEqual(self.world.spawns, [])
        self.assertEqual(self.world.posts, [])

    def test_env_overrides_backend_url_and_telegram_port(self):
        requested = []
        world = self.world

        def get(url, timeout):
            requested.append(url)
            return world.backend if url.endswith("/api/health") else world.telegram

        env = {"BYBITSCANNER_PAPER_BACKEND_URL": "http://127.0.0.1:9000/",
               "BYBITSCANNER_TELEGRAM_MONITORING_PORT": "9001"}
        bootstrap = RuntimeIntentBootstrap(
            root=ROOT, env=env, get=get, post=world.post, spawn=world.spawn,
            sleep=world.sleep, monotonic=lambda: world.now, out=world.lines.append,
        )
        self.assertEqual(bootstrap.run("ALL"), 0)
        self.assertEqual(requested, ["http://127.0.0.1:9000/api/health",
                                     "http://127.0.0.1:9001/health"])
        self.assertEqual(world.posts[-1][0], "http://127.0.0.1:9000/api/runtime/intent")

    def test_spawned_processes_are_only_backend_and_telegram_never_scanner(self):
        self.world.backend = None
        self.world.telegram = None
        self.world.after_spawn = {
            "PAPER backend": self.world.backend_health(),
            "Telegram monitoring": self.world.telegram_health("ready"),
        }
        self.assertEqual(self.run_intent(), 0)
        self.assertEqual(self.world.spawns, [
            ("PAPER backend", [str(ROOT / "start_paper_backend.bat")]),
            ("Telegram monitoring", ["python.exe", str(ROOT / "telegram_monitoring.py")]),
        ])
        source = Path(runtime_intent.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\bmain\.py\b")
        self.assertNotIn("/api/scanner", source)
        self.assertNotIn("robot_admission_ready", source)


class PaperSafeBackendSpawnTests(unittest.TestCase):
    def setUp(self):
        self.parent = dict(UNSAFE_PARENT_ENV)
        self.world = FakeWorld(expected_database_identity(ROOT, self.parent))
        self.world.backend = None
        self.world.after_spawn["PAPER backend"] = self.world.backend_health()
        self.world.telegram = None
        self.world.after_spawn["Telegram monitoring"] = self.world.telegram_health("ready")
        self.world.intent_reply = _converged()

    def test_spawned_backend_gets_forced_paper_safe_env_and_parent_is_untouched(self):
        before = dict(self.parent)
        with mock.patch.dict("os.environ", {"BYBITSCANNER_OPERATOR_TOKEN": "g" * 64}):
            global_before = dict(runtime_intent.os.environ)
            self.assertEqual(self.world.bootstrap(env=self.parent).run("ALL"), 0)
            self.assertEqual(dict(runtime_intent.os.environ), global_before)
        self.assertEqual(self.parent, before)

        backend = [env for name, env in self.world.spawn_envs if name == "PAPER backend"]
        self.assertEqual(len(backend), 1)
        child = backend[0]
        for key, value in EXPECTED_PAPER_SAFE_CHILD.items():
            self.assertEqual(child[key], value, key)
        for key in ("BYBITSCANNER_PAPER_DB", "BYBITSCANNER_PAPER_BACKEND_URL", "HTTPS_PROXY",
                    "BYBITSCANNER_DEPLOYMENT_IDENTITY", "BYBITSCANNER_IKIGAI_BOX_SIGNALS"):
            self.assertEqual(child[key], self.parent[key], key)
        self.assertEqual(len(self.world.posts), 1)

    def test_telegram_child_keeps_default_inheritance(self):
        self.world.bootstrap(env=self.parent).run("ALL")
        self.assertEqual(
            [name for name, _ in self.world.spawn_envs],
            ["PAPER backend", "Telegram monitoring"],
        )
        self.assertIsNone(dict(self.world.spawn_envs)["Telegram monitoring"])

    def test_forced_keys_replace_case_variants_without_duplicates(self):
        parent = {"bybitscanner_operator_token": "x" * 64, "Live_Limit_Mutations_Enabled": "true",
                  "BYBITSCANNER_PAPER_DB": "db.sqlite3"}
        child = runtime_intent.paper_safe_backend_env(parent)
        upper = [key.upper() for key in child]
        self.assertEqual(len(upper), len(set(upper)))
        self.assertEqual(child["BYBITSCANNER_OPERATOR_TOKEN"], "")
        self.assertEqual(child["LIVE_LIMIT_MUTATIONS_ENABLED"], "false")
        self.assertEqual(child["BYBITSCANNER_PAPER_DB"], "db.sqlite3")
        self.assertEqual(parent["bybitscanner_operator_token"], "x" * 64)

    def test_existing_canonical_backend_is_reused_even_when_parent_env_is_unsafe(self):
        self.world.backend = self.world.backend_health()
        self.world.telegram = self.world.telegram_health("ready")
        self.world.intent_reply = _response(409, {
            "ok": False, "intent": "ALL", "changed": [], "final": {},
            "blocked_by": ["PAPER_LIVE_UNSAFE"],
        })
        self.assertEqual(self.world.bootstrap(env=self.parent).run("ALL"), 2)
        self.assertEqual(self.world.spawns, [])
        self.assertEqual(len(self.world.posts), 1)
        self.assertIn("blocked_by=PAPER_LIVE_UNSAFE", self.world.lines[-1])

    def test_mismatched_existing_backend_still_fails_closed_without_spawn(self):
        self.world.backend = self.world.backend_health(database_identity="0" * 64)
        self.assertEqual(self.world.bootstrap(env=self.parent).run("ALL"), 1)
        self.assertEqual(self.world.spawns, [])
        self.assertEqual(self.world.posts, [])


class ProductionPrimitivesTests(unittest.TestCase):
    def test_identity_matches_sqlite_store_without_touching_the_database(self):
        from terminal.persistence.sqlite_store import SQLiteStore

        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "paper.sqlite3"
            identity = expected_database_identity(ROOT, {"BYBITSCANNER_PAPER_DB": str(db)})
            self.assertFalse(db.exists())
            store = SQLiteStore.open(db)
            try:
                self.assertEqual(identity, store.database_identity)
            finally:
                store.close()

    def test_relative_and_default_db_paths_resolve_against_project_root(self):
        expected = hashlib.sha256(
            str((ROOT / "paper_runtime.sqlite3").resolve()).encode("utf-8")
        ).hexdigest()
        self.assertEqual(expected_database_identity(ROOT, {}), expected)
        self.assertEqual(
            expected_database_identity(ROOT, {"BYBITSCANNER_PAPER_DB": "paper_runtime.sqlite3"}),
            expected,
        )

    def test_spawn_uses_a_new_visible_console_without_shell(self):
        with mock.patch("tools.runtime_intent.subprocess.Popen") as popen:
            runtime_intent.spawn_console(["start_paper_backend.bat"], ROOT)
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["cmd.exe", "/k", "start_paper_backend.bat"])
        self.assertEqual(kwargs["cwd"], str(ROOT))
        self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        self.assertNotIn("shell", kwargs)
        self.assertIsNone(kwargs["env"])

        child = {"BYBITSCANNER_OPERATOR_TOKEN": "", "BYBITSCANNER_PAPER_DB": "db.sqlite3"}
        with mock.patch("tools.runtime_intent.subprocess.Popen") as popen:
            runtime_intent.spawn_console(["start_paper_backend.bat"], ROOT, child)
        self.assertEqual(popen.call_args.kwargs["env"], child)
        self.assertIsNot(popen.call_args.kwargs["env"], child)

    def test_main_defaults_to_all_and_rejects_extra_arguments(self):
        with mock.patch.object(RuntimeIntentBootstrap, "run", return_value=0) as run:
            self.assertEqual(runtime_intent.main([]), 0)
            self.assertEqual(runtime_intent.main(["SCANNER"]), 0)
        self.assertEqual([call.args[0] for call in run.call_args_list], ["ALL", "SCANNER"])
        self.assertEqual(runtime_intent.main(["ALL", "ROBOT"]), runtime_intent.EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
