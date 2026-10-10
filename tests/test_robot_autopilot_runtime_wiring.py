"""Autopilot A7: PAPER runtime wiring. Temporary DBs and candidate files only.

OFF changes nothing, SHADOW stays read-only, and PAPER_AUTO reaches the Robot
only through the canonical admission boundary after its currency is proven from
authoritative evidence. PAPER_AUTO is never enabled implicitly.
"""

import tempfile
import unittest
from pathlib import Path

from robot_candidate_store import load_candidate
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW, OUTCOME_REJECT, OUTCOME_WAIT, REASON_CANDIDATE_FRESHNESS_UNKNOWN,
    REASON_CANDIDATE_STALE, REASON_ELIGIBLE,
)
from terminal.application.robot_autopilot_shadow import (
    PAPER_AUTO_MODE, SHADOW_MODE, SOURCE_SCANNER, admit_arrived_auto_candidate,
    owner_autopilot_mode,
)
from tests.test_robot_autopilot_shadow import ACCOUNT, TRADING_TABLES, _Db, _wedge

T0 = 100 * 60_000 + 5_000


def _healthy():
    return True


class OwnerEnableTests(unittest.TestCase):
    def test_paper_auto_needs_an_explicit_owner_confirmation_on_a_paper_account(self):
        self.assertEqual(owner_autopilot_mode("off", environment="PAPER",
                                              confirm_paper_auto=False), "OFF")
        self.assertEqual(owner_autopilot_mode("shadow", environment="PAPER",
                                              confirm_paper_auto=False), SHADOW_MODE)
        for environment, confirm in (("PAPER", False), ("LIVE", True), ("LIVE", False)):
            with self.subTest(environment=environment, confirm=confirm):
                with self.assertRaises(ValueError):
                    owner_autopilot_mode("PAPER_AUTO", environment=environment,
                                         confirm_paper_auto=confirm)
        self.assertEqual(owner_autopilot_mode("PAPER_AUTO", environment="PAPER",
                                              confirm_paper_auto=True), PAPER_AUTO_MODE)


class ArrivedAutoAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _Db(Path(self.tmp.name))
        self.addCleanup(lambda: self.db.store.close())

    def enable_paper_auto(self, at_ms=T0 - 1_000):
        state = self.db.store.get_robot_autopilot_state(ACCOUNT)
        self.db.store.update_robot_autopilot_state(
            ACCOUNT, mode=PAPER_AUTO_MODE, expected_version=state.version,
            updated_at_ms=at_ms)

    def arrive(self, ref, fresh, now=T0):
        return admit_arrived_auto_candidate(
            self.db.store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref=ref,
            protection_healthy=_healthy, candidate_fresh=fresh,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: now,
        )

    def test_off_and_shadow_never_reach_canonical_admission(self):
        db = self.db
        _wedge(db.candidates, "w")
        before = db.footprint()
        # SHADOW is the durable mode here: the PAPER_AUTO path must not run at all.
        self.assertIsNone(self.arrive("w", lambda *_: True))
        shadow = db.observe("w", health=_healthy, now=T0)
        self.assertEqual(shadow.result.outcome, OUTCOME_ALLOW)
        self.assertIsNone(db.store.get_robot_candidate("w"))
        self.assertEqual(db.footprint(), before)

    def test_proven_live_candidate_is_admitted_once_through_the_canonical_boundary(self):
        db = self.db
        _wedge(db.candidates, "w")
        self.enable_paper_auto()
        admitted = self.arrive("w", lambda *_: True)
        again = self.arrive("w", lambda *_: True, now=T0 + 60_000)

        self.assertEqual((admitted.result.outcome, admitted.result.reason_code),
                         (OUTCOME_ALLOW, REASON_ELIGIBLE))
        self.assertTrue(admitted.candidate_created)
        self.assertFalse(again.candidate_created)
        self.assertEqual(again.decision, admitted.decision)
        self.assertEqual(admitted.candidate.candidate_id, "w")
        self.assertEqual(db.store.get_robot_candidate("w").status, "APPROVED")
        self.assertEqual(load_candidate("w", store_dir=db.candidates)["status"], "APPROVED")
        # Admission only: no order, execution or trade is created by Autopilot.
        self.assertEqual(db.footprint()[:len(TRADING_TABLES)], (0,) * len(TRADING_TABLES))

    def test_unprovable_currency_waits_and_a_dead_setup_is_rejected(self):
        db = self.db
        _wedge(db.candidates, "unknown")
        _wedge(db.candidates, "dead", symbol="AAAUSDT")
        self.enable_paper_auto()

        for ref, prover, outcome, reason in (
            ("unknown", lambda *_: None, OUTCOME_WAIT, REASON_CANDIDATE_FRESHNESS_UNKNOWN),
            ("dead", lambda *_: False, OUTCOME_REJECT, REASON_CANDIDATE_STALE),
        ):
            with self.subTest(ref=ref):
                result = self.arrive(ref, prover)
                self.assertEqual((result.result.outcome, result.result.reason_code),
                                 (outcome, reason))
                self.assertIsNone(result.candidate)
                self.assertIsNone(db.store.get_robot_candidate(ref))

        # A missing prover and a failing one are both unproven, never an implicit ALLOW.
        def broken(*_args):
            raise RuntimeError("evidence source unavailable")

        _wedge(db.candidates, "broken", symbol="BBBUSDT")
        self.assertEqual(self.arrive("broken", broken).result.reason_code,
                         REASON_CANDIDATE_FRESHNESS_UNKNOWN)
        _wedge(db.candidates, "absent", symbol="CCCUSDT")
        self.assertEqual(self.arrive("absent", None).result.reason_code,
                         REASON_CANDIDATE_FRESHNESS_UNKNOWN)
        self.assertEqual(db.footprint()[:len(TRADING_TABLES)], (0,) * len(TRADING_TABLES))

    def test_a_waiting_candidate_is_admitted_once_its_currency_becomes_provable(self):
        db = self.db
        _wedge(db.candidates, "w")
        self.enable_paper_auto()
        waited = self.arrive("w", lambda *_: None)
        self.assertEqual(waited.result.reason_code, REASON_CANDIDATE_FRESHNESS_UNKNOWN)
        # A6 still governs when a WAIT may be looked at again: same candle, no change.
        self.assertEqual(self.arrive("w", lambda *_: True, now=T0 + 1_000).decision,
                         waited.decision)
        admitted = self.arrive("w", lambda *_: True, now=T0 + 60_000)
        self.assertEqual(admitted.result.outcome, OUTCOME_ALLOW)
        self.assertEqual(admitted.candidate.candidate_id, "w")


class RuntimeWiringTests(unittest.TestCase):
    def _runtime(self, temp):
        from tests.test_continuity_recovery_candidate_snapshot import _runtime

        runtime = _runtime(temp)
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        return runtime

    def test_owner_cannot_enable_paper_auto_without_confirming_and_default_stays_off(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp)
            try:
                self.assertEqual(runtime.autopilot_state().mode, "OFF")
                with self.assertRaises(ValueError):
                    runtime.set_autopilot_mode("PAPER_AUTO")
                self.assertEqual(runtime.autopilot_state().mode, "OFF")
                runtime.set_autopilot_mode("SHADOW")
                self.assertEqual(runtime.autopilot_state().mode, SHADOW_MODE)
                runtime.set_autopilot_mode("PAPER_AUTO", confirm_paper_auto=True)
                self.assertEqual(runtime.autopilot_state().mode, PAPER_AUTO_MODE)
            finally:
                runtime.close()
            # Restart recovery keeps forcing automation back off.
            restarted = self._runtime(temp)
            try:
                self.assertEqual(restarted.autopilot_state().mode, "OFF")
            finally:
                restarted.close()

    def test_scanner_arrival_routes_through_paper_auto_and_fails_closed(self):
        from tests.test_terminal_paper_runtime import _CONFIRMED_BOX_FORMATION

        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp)
            try:
                runtime.bind_autopilot_protection_health(lambda: True)
                runtime.set_autopilot_mode("PAPER_AUTO", confirm_paper_auto=True)
                runtime.robot_catchup_evidence = None  # nothing prepared off the owner
                before = tuple(runtime.store._connection.execute(
                    f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TRADING_TABLES)

                source_id = runtime._dispatch_ikigai_box_plan_preparation(
                    "BTCUSDT", "5", _CONFIRMED_BOX_FORMATION)

                decisions = runtime.store.load_robot_auto_decisions(ACCOUNT)
                self.assertEqual([(d.mode, d.outcome, d.reason_code) for d in decisions],
                                 [(PAPER_AUTO_MODE, OUTCOME_WAIT,
                                   REASON_CANDIDATE_FRESHNESS_UNKNOWN)])
                self.assertEqual(runtime.store.get_robot_candidate(source_id).status,
                                 "BOX_PLAN_ONLY")
                self.assertEqual([c for c in runtime.store.load_robot_candidates(ACCOUNT)
                                  if c.status != "BOX_PLAN_ONLY"], [])
                self.assertEqual(tuple(runtime.store._connection.execute(
                    f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in TRADING_TABLES), before)
            finally:
                runtime.close()

    def test_unproven_evidence_keeps_the_runtime_freshness_answer_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp)
            try:
                snapshot = {"symbol": "ONGUSDT", "pattern": "Falling Wedge"}
                # No prepared off-owner evidence: the owner thread never fetches.
                runtime.robot_catchup_evidence = None
                self.assertIsNone(runtime._autopilot_candidate_fresh("ONGUSDT", snapshot))

                def empty(_symbol, _snapshot):
                    return ()

                runtime.robot_catchup_evidence = empty
                self.assertIsNone(runtime._autopilot_candidate_fresh("ONGUSDT", snapshot))

                def broken(_symbol, _snapshot):
                    raise RuntimeError("evidence was never prepared")

                runtime.robot_catchup_evidence = broken
                self.assertIsNone(runtime._autopilot_candidate_fresh("ONGUSDT", snapshot))
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
