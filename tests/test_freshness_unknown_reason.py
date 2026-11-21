"""#608: CANDIDATE_FRESHNESS_UNKNOWN keeps WAIT but records a stable reason class.

In the 24.10.2026 PAPER run 9 Wedge decisions waited with ``candidate_fresh=None``
and the cause was lost with the console log. The decision audit now carries
``candidate_fresh_unknown_reason``; the admission outcome is unchanged.
Temporary SQLite only.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from terminal.application import robot_autopilot_shadow as shadow
from terminal.runtime.closed_candle_cache import (
    EVIDENCE_EXPIRED, EVIDENCE_FETCH_FAILED, EVIDENCE_NOT_PREPARED,
    CatchupEvidenceUnavailable, PreparedCatchupEvidence,
)
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_box_plan_persistence import snapshot
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db

NOW = 1792116000000
SNAP = {"pattern": "Falling Wedge", "id": "x"}


class PreparedEvidenceReasonTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.calls = []

        def fetch(symbol, snap):
            self.calls.append(symbol)
            if symbol == "BADUSDT":
                raise TimeoutError("kline timeout")
            return ("candle",)

        self.evidence = PreparedCatchupEvidence(fetch, max_age_s=90, clock=lambda: self.now[0])

    def reason(self, symbol):
        with self.assertRaises(CatchupEvidenceUnavailable) as caught:
            self.evidence(symbol, SNAP)
        self.assertIsInstance(caught.exception, RuntimeError)       # old contract kept
        self.assertIn("was not prepared off the owner thread", str(caught.exception))
        return caught.exception.reason

    def test_not_prepared_fetch_failed_and_expired_are_distinguished(self):
        self.assertEqual(self.reason("ONGUSDT"), EVIDENCE_NOT_PREPARED)
        self.evidence.prepare([("BADUSDT", SNAP)])
        self.assertEqual(self.reason("BADUSDT"), EVIDENCE_FETCH_FAILED)
        self.evidence.prepare([("ONGUSDT", SNAP)])
        self.now[0] += 91
        self.assertEqual(self.reason("ONGUSDT"), EVIDENCE_EXPIRED)

    def test_success_is_consumed_once_and_clears_an_earlier_failure(self):
        self.evidence.prepare([("ONGUSDT", SNAP)])
        self.assertEqual(self.evidence("ONGUSDT", SNAP), ("candle",))
        self.assertEqual(self.reason("ONGUSDT"), EVIDENCE_NOT_PREPARED)


class RuntimeProverReasonTests(unittest.TestCase):
    def classify(self, evidence, snap=SNAP):
        fake = SimpleNamespace(robot_catchup_evidence=evidence)
        with self.assertRaises(shadow.FreshnessUnknown) as caught:
            PaperRuntime._autopilot_candidate_fresh_classified(fake, "ONGUSDT", snap)
        self.assertIsNone(PaperRuntime._autopilot_candidate_fresh(fake, "ONGUSDT", snap))
        return caught.exception.reason

    def test_each_unproven_branch_has_its_own_class(self):
        self.assertEqual(self.classify(None), "EVIDENCE_PROVIDER_MISSING")
        self.assertEqual(self.classify(lambda *_: (), snap=["not", "a", "mapping"]),
                         "UNSUPPORTED_SNAPSHOT")

        def unavailable(*_):
            raise CatchupEvidenceUnavailable("ONGUSDT", EVIDENCE_FETCH_FAILED)

        self.assertEqual(self.classify(unavailable), EVIDENCE_FETCH_FAILED)

        def broken(*_):
            raise ValueError("boom")

        self.assertEqual(self.classify(broken), "EVIDENCE_ERROR")
        self.assertEqual(self.classify(lambda *_: ("not-a-candle",)), "WEDGE_REPLAY_FAILED")


class AuditReasonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _Db(Path(self.tmp.name), autopilot="PAPER_AUTO")
        self.addCleanup(self.db.store.close)

    def arrive(self, prover, index):
        data = snapshot()
        data["identity"]["a_time_ms"] += index
        source = self.db.store.save_box_plan_only(snapshot=data, created_at_ms=3001)[0]
        result = shadow.admit_arrived_auto_candidate(
            self.db.store, ACCOUNT, source=shadow.SOURCE_BOX_PLAN,
            candidate_ref=source.candidate_id, candidate_store_dir=self.db.candidates,
            clock_ms=lambda: NOW, protection_healthy=lambda: True, candidate_fresh=prover)
        facts = json.loads(result.decision.facts_json)
        return result.decision, facts

    def test_reason_is_recorded_and_outcome_stays_wait(self):
        def unknown(*_):
            raise shadow.FreshnessUnknown(EVIDENCE_NOT_PREPARED)

        def crash(*_):
            raise RuntimeError("unexpected")

        cases = ((unknown, EVIDENCE_NOT_PREPARED), (crash, shadow.FRESHNESS_PROVER_ERROR),
                 (lambda *_: None, shadow.FRESHNESS_UNPROVEN))
        for index, (prover, reason) in enumerate(cases, start=1):
            with self.subTest(reason=reason):
                decision, facts = self.arrive(prover, index)
                self.assertEqual((decision.outcome, decision.reason_code),
                                 ("WAIT", "CANDIDATE_FRESHNESS_UNKNOWN"))
                self.assertIsNone(facts["candidate_fresh"])
                self.assertEqual(facts["candidate_fresh_unknown_reason"], reason)

    def test_proven_freshness_records_no_reason(self):
        decision, facts = self.arrive(lambda *_: True, 9)
        self.assertTrue(facts["candidate_fresh"])
        self.assertIsNone(facts["candidate_fresh_unknown_reason"])
        self.assertNotEqual(decision.reason_code, "CANDIDATE_FRESHNESS_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
