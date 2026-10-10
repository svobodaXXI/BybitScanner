"""Autopilot A6: bounded WAIT reevaluation. Temporary DBs and candidate files only.

A recorded WAIT may be evaluated again only by the existing observer/admission
calls, on a newly closed source candle or a durable Robot/Autopilot state
transition. There is no age-based expiry; invalidated ideas are never resumed,
repeats are idempotent and an ALLOW still has to pass the S3 boundary.
"""

import tempfile
import unittest
from pathlib import Path

from robot_candidate_store import load_candidate
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW, OUTCOME_REJECT, OUTCOME_WAIT, REASON_CANDIDATE_INVALIDATED,
    REASON_ELIGIBLE, REASON_PROTECTION_HEALTH_UNKNOWN,
    REASON_ROBOT_NOT_READY,
)
from terminal.application.robot_autopilot_shadow import (
    SOURCE_SCANNER, admit_paper_auto_candidate,
)
from terminal.domain.models import Symbol
from tests.test_robot_autopilot_shadow import ACCOUNT, TRADING_TABLES, _Db, _wedge

MINUTE = 60_000
T0 = 100 * MINUTE + 5_000  # inside one closed-candle bucket of the 1m source


def _healthy():
    return True


class WaitReevaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _Db(Path(self.tmp.name))
        self.addCleanup(lambda: self.db.store.close())

    def outcomes(self, ref):
        return [(d.outcome, d.reason_code) for d in self.db.decisions() if d.candidate_ref == ref]

    def enable_paper_auto(self, at_ms):
        state = self.db.store.get_robot_autopilot_state(ACCOUNT)
        self.db.store.update_robot_autopilot_state(
            ACCOUNT, mode="PAPER_AUTO", expected_version=state.version, updated_at_ms=at_ms)

    def auto(self, decision, now, health):
        return admit_paper_auto_candidate(
            self.db.store, ACCOUNT, allow_decision_id=decision.decision_id,
            source=SOURCE_SCANNER, protection_healthy=health,
            candidate_fresh=lambda *_: True,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: now,
        )

    def test_wait_becomes_allow_only_on_a_new_closed_candle_and_passes_s3_again(self):
        db = self.db
        _wedge(db.candidates, "w")
        before = db.footprint()
        first = db.observe("w", now=T0)  # no protection-health source yet
        self.assertEqual((first.result.outcome, first.result.reason_code),
                         (OUTCOME_WAIT, REASON_PROTECTION_HEALTH_UNKNOWN))

        # Same closed candle, no durable state transition: nothing is evaluated or written.
        same = db.observe("w", health=_healthy, now=T0 + 10_000)
        self.assertFalse(same.created)
        self.assertEqual(same.decision, first.decision)

        allowed = db.observe("w", health=_healthy, now=T0 + MINUTE)
        self.assertTrue(allowed.created)
        self.assertEqual((allowed.result.outcome, allowed.result.reason_code),
                         (OUTCOME_ALLOW, REASON_ELIGIBLE))
        self.assertFalse(allowed.facts.candidate_stale)
        # SHADOW still admits, approves and trades nothing; a repeat changes nothing.
        self.assertFalse(db.observe("w", health=_healthy, now=T0 + 2 * MINUTE).created)
        self.assertEqual(self.outcomes("w"), [(OUTCOME_WAIT, REASON_PROTECTION_HEALTH_UNKNOWN),
                                              (OUTCOME_ALLOW, REASON_ELIGIBLE)])
        self.assertEqual(db.footprint(), before)
        self.assertEqual(load_candidate("w", store_dir=db.candidates)["status"], "AVAILABLE")

        # The fresh ALLOW still has to cross S3, whose own WAIT is bounded the same way.
        self.enable_paper_auto(T0 + MINUTE + 1_000)
        waited = self.auto(allowed.decision, T0 + MINUTE + 2_000, None)
        self.assertEqual((waited.result.outcome, waited.result.reason_code),
                         (OUTCOME_WAIT, REASON_PROTECTION_HEALTH_UNKNOWN))
        frozen = self.auto(allowed.decision, T0 + MINUTE + 9_000, _healthy)
        self.assertEqual(frozen.decision, waited.decision)
        self.assertIsNone(db.store.get_robot_candidate("w"))

        admitted = self.auto(allowed.decision, T0 + 2 * MINUTE, _healthy)
        again = self.auto(allowed.decision, T0 + 3 * MINUTE, _healthy)
        self.assertEqual(admitted.result.outcome, OUTCOME_ALLOW)
        self.assertTrue(admitted.candidate_created)
        self.assertFalse(again.candidate_created)
        self.assertEqual(again.decision, admitted.decision)
        self.assertEqual(admitted.candidate.candidate_id, "w")
        self.assertEqual(db.footprint()[:len(TRADING_TABLES)], (0,) * len(TRADING_TABLES))

    def test_robot_state_transition_resumes_earlier_waits_first_on_the_next_arrival(self):
        root = Path(self.tmp.name) / "stopped"
        root.mkdir()
        db = _Db(root, robot=("ROBOT_STOPPED", "ROBOT_STOPPED"))
        self.addCleanup(lambda: db.store.close())
        _wedge(db.candidates, "a", symbol="AAAUSDT")
        waited = db.observe("a", health=_healthy, now=T0)
        self.assertEqual(waited.result.reason_code, REASON_ROBOT_NOT_READY)

        runtime = db.store.get_robot_runtime_state(ACCOUNT)
        db.store.update_robot_runtime_state(
            ACCOUNT, mode="ROBOT_RUNNING", recovery_status="READY", reason=None,
            expected_version=runtime.version, updated_at_ms=T0 + 1_000)
        # No new scheduler: the next arriving candidate (same candle) drives the resume.
        _wedge(db.candidates, "b", symbol="BBBUSDT")
        arrived = db.observe("b", health=_healthy, now=T0 + 2_000)
        self.assertEqual(arrived.decision.candidate_ref, "b")
        self.assertEqual(arrived.result.outcome, OUTCOME_ALLOW)
        by_ref = lambda ref: [(d.outcome, d.reason_code) for d in db.decisions()
                              if d.candidate_ref == ref]
        self.assertEqual(by_ref("a"), [(OUTCOME_WAIT, REASON_ROBOT_NOT_READY),
                                       (OUTCOME_ALLOW, REASON_ELIGIBLE)])
        # The transition is consumed once: later arrivals in the same candle add nothing.
        _wedge(db.candidates, "c", symbol="CCCUSDT")
        db.observe("c", health=_healthy, now=T0 + 3_000)
        self.assertEqual(len(by_ref("a")), 2)

    def test_wait_and_shadow_allow_do_not_expire_by_age(self):
        db = self.db
        _wedge(db.candidates, "old-wait")
        _wedge(db.candidates, "old-allow", symbol="AAAUSDT")
        db.observe("old-wait", now=T0)
        allowed = db.observe("old-allow", health=_healthy, now=T0)
        much_later = T0 + 100 * MINUTE

        # A later arrival rechecks older WAITs without an arbitrary expiry.
        _wedge(db.candidates, "new", symbol="BBBUSDT")
        self.assertEqual(db.observe("new", health=_healthy, now=much_later).result.outcome,
                         OUTCOME_ALLOW)
        self.assertEqual(self.outcomes("old-wait"),
                         [(OUTCOME_WAIT, REASON_PROTECTION_HEALTH_UNKNOWN),
                          (OUTCOME_ALLOW, REASON_ELIGIBLE)])
        self.assertFalse(db.observe("old-wait", health=_healthy,
                                    now=much_later + MINUTE).created)

        # S3 still runs full admission for an old SHADOW ALLOW, not age rejection.
        self.enable_paper_auto(much_later)
        admitted = self.auto(allowed.decision, much_later + 1_000, _healthy)
        self.assertEqual(admitted.result.outcome, OUTCOME_ALLOW)
        self.assertTrue(admitted.candidate_created)
        self.assertFalse(admitted.facts.candidate_stale)
        self.assertFalse(self.auto(allowed.decision, much_later + 2_000,
                                   _healthy).candidate_created)

    def test_invalidated_wait_is_rejected_instead_of_resumed(self):
        db = self.db
        envelope = _wedge(db.candidates, "w")
        db.observe("w", now=T0)
        record, _created = db.store.create_robot_candidate(
            candidate_id="w", trading_account_id=ACCOUNT, symbol=Symbol(envelope["symbol"]),
            status="APPROVED", signal_snapshot=envelope["signal_snapshot"],
            approved_at_ms=T0 + 1_000, updated_at_ms=T0 + 1_000)
        db.store.save_robot_candidate_state(
            "w", status="INVALIDATED", robot_state={"phase": "INVALIDATED"},
            expected_revision=record.state_revision, updated_at_ms=T0 + 2_000)

        result = db.observe("w", health=_healthy, now=T0 + MINUTE)
        self.assertEqual((result.result.outcome, result.result.reason_code),
                         (OUTCOME_REJECT, REASON_CANDIDATE_INVALIDATED))
        self.assertFalse(db.observe("w", health=_healthy, now=T0 + 2 * MINUTE).created)
        self.assertNotIn(OUTCOME_ALLOW, [outcome for outcome, _ in self.outcomes("w")])


if __name__ == "__main__":
    unittest.main()
