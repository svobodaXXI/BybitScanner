"""Telegram-invoked runtime intent: shared bootstrap without a second Telegram worker."""

import unittest
from unittest import mock

import telegram_runtime_intent
from tests.test_runtime_intent_bootstrap import (
    BACKEND_HEALTH, INTENT_URL, ROOT, TELEGRAM_HEALTH, FakeWorld, _converged, _response,
)
from tools import runtime_intent
from tools.runtime_intent import BootstrapResult, RuntimeIntentBootstrap, expected_database_identity


class TelegramRuntimeIntentBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.world = FakeWorld(expected_database_identity(ROOT, {}))
        self.world.backend = self.world.backend_health()
        self.world.telegram = None
        self.world.intent_reply = _converged(intent="ROBOT", changed=("robot:start",))
        self.requested = []
        original_get = self.world.get

        def get(url, timeout):
            self.requested.append(url)
            return original_get(url, timeout)

        self.bootstrap = RuntimeIntentBootstrap(
            root=ROOT, env={}, get=get, post=self.world.post, spawn=self.world.spawn,
            python="python.exe", sleep=self.world.sleep, monotonic=lambda: self.world.now,
            out=self.world.lines.append, require_telegram=False,
        )

    def test_missing_backend_is_spawned_once_and_telegram_is_never_probed_or_spawned(self):
        self.world.backend = None
        self.world.after_spawn["PAPER backend"] = [None, self.world.backend_health()]
        result = self.bootstrap.execute("ROBOT")
        self.assertTrue(result.ok)
        self.assertEqual([name for name, _ in self.world.spawns], ["PAPER backend"])
        self.assertNotIn(TELEGRAM_HEALTH, self.requested)
        self.assertEqual(set(self.requested), {BACKEND_HEALTH})
        self.assertEqual(self.world.posts, [(INTENT_URL, {"intent": "ROBOT"})])
        self.assertEqual(result.changed, ("robot:start",))

    def test_wrong_backend_identity_fails_closed_without_spawn_or_intent(self):
        self.world.backend = self.world.backend_health(database_identity="0" * 64)
        result = self.bootstrap.execute("ALL")
        self.assertEqual(result.outcome, runtime_intent.OUTCOME_FAILED)
        self.assertEqual(self.world.spawns, [])
        self.assertEqual(self.world.posts, [])

    def test_intent_is_posted_at_most_once_even_when_ambiguous_or_blocked(self):
        for reply, outcome in (
            (TimeoutError("timed out"), runtime_intent.OUTCOME_ERROR),
            (_response(409, {"ok": False, "intent": "ROBOT", "changed": [], "final": {},
                             "blocked_by": ["PAPER_LIVE_UNSAFE"]}), runtime_intent.OUTCOME_BLOCKED),
        ):
            with self.subTest(outcome=outcome):
                self.world.posts.clear()
                self.world.intent_reply = reply
                result = self.bootstrap.execute("ROBOT")
                self.assertEqual(result.outcome, outcome)
                self.assertEqual(len(self.world.posts), 1)


class TelegramRuntimeIntentFacadeTests(unittest.TestCase):
    def test_execute_uses_shared_bootstrap_without_telegram_requirement(self):
        expected = BootstrapResult("SCANNER", runtime_intent.OUTCOME_READY, "READY")
        with mock.patch.object(
            telegram_runtime_intent, "execute_runtime_intent", return_value=expected,
        ) as shared:
            self.assertIs(telegram_runtime_intent.execute("SCANNER"), expected)
        self.assertEqual(shared.call_args.args, ("SCANNER",))
        self.assertIs(shared.call_args.kwargs["require_telegram"], False)

    def test_unexpected_bootstrap_exception_is_one_unconfirmed_result(self):
        with mock.patch.object(
            telegram_runtime_intent, "execute_runtime_intent", side_effect=RuntimeError("boom"),
        ) as shared:
            result = telegram_runtime_intent.execute("ALL")
        shared.assert_called_once()
        self.assertFalse(result.ok)
        self.assertEqual(telegram_runtime_intent.failure_text(result), "⚠ Запуск не подтверждён.")

    def test_failure_text_shows_only_stable_blocker_codes(self):
        blocked = BootstrapResult(
            "ALL", runtime_intent.OUTCOME_BLOCKED, "BLOCKED: secret-free",
            blocked_by=("ROBOT_PROTECTION_UNHEALTHY",),
        )
        self.assertEqual(
            telegram_runtime_intent.failure_text(blocked),
            "⛔ Запуск заблокирован: ROBOT_PROTECTION_UNHEALTHY",
        )
        for outcome in (runtime_intent.OUTCOME_FAILED, runtime_intent.OUTCOME_ERROR):
            self.assertEqual(
                telegram_runtime_intent.failure_text(BootstrapResult("ALL", outcome, "x")),
                "⚠ Запуск не подтверждён.",
            )

    def test_desktop_cli_still_requires_telegram(self):
        with mock.patch.object(RuntimeIntentBootstrap, "__init__", return_value=None) as init, \
                mock.patch.object(RuntimeIntentBootstrap, "run", return_value=0):
            self.assertEqual(runtime_intent.main(["ALL"]), 0)
        self.assertIs(init.call_args.kwargs["require_telegram"], True)


if __name__ == "__main__":
    unittest.main()
