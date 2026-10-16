"""FIX-2: bounded PAPER_AUTO reads preserve full-history admission and latch semantics."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal.application import robot_autopilot as ap
from terminal.application import robot_autopilot_shadow as shadow
from terminal.domain.models import Symbol
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db, _wedge
from tests.test_robot_autopilot_daily_gate import D0, _equity
from tests import test_robot_autopilot_concurrency as concurrency

NOW = D0 + 1_000_000
DATE = "2026-10-14"


def seed(db):
    _wedge(db.candidates, "seed", symbol="SEEDUSDT")
    original = db.observe("seed", now=D0, health=lambda: True).decision
    state = db.store.get_robot_autopilot_state(ACCOUNT)
    db.store.update_robot_autopilot_state(
        ACCOUNT, mode="PAPER_AUTO", expected_version=state.version, updated_at_ms=D0 + 500)
    # The informative latch is neither the first nor the last row of this idea.
    with db.store.autopilot_decision_transaction():
        for index in range(300):
            gate = {"business_date_msk": DATE, "latched": None}
            if index == 0:
                gate["latched"] = False
            if index == 150:
                gate["latched"] = True
            if index == 298:
                gate = {"business_date_msk": "2026-10-13", "latched": False}
            facts = json.loads(original.facts_json)
            facts.update(autopilot_mode="PAPER_AUTO", daily_loss_gate=gate,
                         padding="x" * 4096)
            db.store.append_robot_auto_decision(replace(
                original, decision_id=f"history-{index:04d}", candidate_ref="history",
                mode="PAPER_AUTO", outcome="WAIT", reason_code="DAILY_LOSS_LIMIT",
                evaluated_at_ms=D0 + index + 1, facts_json=json.dumps(facts)))
    return original


def bounded(store, ref="fresh", identity="fresh"):
    return store.load_robot_auto_decisions_for_admission(
        ACCOUNT, candidate_ref=ref, source_identity=identity,
        policy_version=ap.POLICY_VERSION, business_date_msk=DATE)


def admit(db, store=None, ref="fresh", **kwargs):
    return shadow.admit_arrived_auto_candidate(
        store or db.store, ACCOUNT, source=shadow.SOURCE_SCANNER, candidate_ref=ref,
        candidate_store_dir=db.candidates, clock_ms=lambda: NOW,
        protection_healthy=lambda: True, candidate_fresh=lambda *_: True, **kwargs)


def footprint(store):
    # Includes audit, canonical candidates, ownership, balances and all trading rows.
    tables = [r[0] for r in store._connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: sorted(tuple(r) for r in store._connection.execute('SELECT * FROM "' + t + '"'))
            for t in tables}


class BoundedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _Db(Path(self.tmp.name))
        self.addCleanup(lambda: self.db.store.close())
        self.original = seed(self.db)

    def test_long_history_keeps_latest_idea_shadow_allow_and_middle_latch(self):
        store = self.db.store
        full = store.load_robot_auto_decisions(ACCOUNT)
        rows = bounded(store, "history", self.original.source_identity)
        self.assertEqual(len(full), 301)
        self.assertEqual(len(rows), 3)
        self.assertEqual(store.count_robot_auto_decisions(ACCOUNT), 301)
        self.assertEqual(ap._previous_latch(rows, DATE), ap._previous_latch(full, DATE))
        self.assertIs(ap._previous_latch(rows, DATE), True)
        self.assertEqual(shadow._latest_decision(rows, "history", self.original.source_identity,
                                                "PAPER_AUTO"),
                         shadow._latest_decision(full, "history", self.original.source_identity,
                                                "PAPER_AUTO"))
        for pct, available in (("-10", True), ("-8", True), ("-7", True),
                               ("-6.99", True), (None, False)):
            for enabled in (False, True):
                equity = _equity(pct, available=available)
                self.assertEqual(ap.daily_loss_gate_facts(equity, rows, enabled=enabled),
                                 ap.daily_loss_gate_facts(equity, full, enabled=enabled))

    def test_malformed_latest_latch_is_not_silently_discarded(self):
        store = self.db.store
        _wedge(self.db.candidates, "fresh", symbol="FRESHUSDT")
        for index, value in enumerate(("yes", 0, [], {})):
            with self.subTest(value=value):
                store.append_robot_auto_decision(replace(
                    self.original, decision_id=f"malformed-{len(str(value))}-{type(value).__name__}",
                    mode="PAPER_AUTO", evaluated_at_ms=NOW + index,
                    facts_json=json.dumps({"daily_loss_gate": {
                        "business_date_msk": DATE, "latched": value}})))
                for rows in (bounded(store), store.load_robot_auto_decisions(ACCOUNT)):
                    with self.assertRaises(ValueError):
                        ap._previous_latch(rows, DATE)
                before = footprint(store)
                with self.assertRaises(ValueError):
                    admit(self.db)
                self.assertEqual(before, footprint(store))

    def test_tied_timestamp_uses_decision_id_and_ignores_null_latch(self):
        store = self.db.store
        for suffix, latch in (("a", False), ("z", True), ("zz", None)):
            store.append_robot_auto_decision(replace(
                self.original, decision_id="tie-" + suffix, mode="PAPER_AUTO",
                evaluated_at_ms=NOW, facts_json=json.dumps({"daily_loss_gate": {
                    "business_date_msk": DATE, "latched": latch}})))
        self.assertIs(ap._previous_latch(bounded(store), DATE), True)
        tomorrow = store.load_robot_auto_decisions_for_admission(
            ACCOUNT, candidate_ref="absent", source_identity="absent",
            policy_version=ap.POLICY_VERSION, business_date_msk="2026-10-15")
        self.assertIsNone(ap._previous_latch(tomorrow, "2026-10-15"))

    def test_full_and_bounded_admissions_have_identical_audit_and_side_effects(self):
        for scenario in ("allow", "wait", "reject", "ambiguous", "cap", "latch"):
            outcomes = []
            for full in (True, False):
                with self.subTest(scenario=scenario, full=full), tempfile.TemporaryDirectory() as tmp:
                    db = _Db(Path(tmp))
                    try:
                        seed(db)
                        _wedge(db.candidates, "fresh", symbol="FRESHUSDT",
                               timeframe="invalid" if scenario == "reject" else "1")
                        if scenario == "ambiguous":
                            db.store._connection.execute(
                                "INSERT INTO trading_commands VALUES ('stuck','stuck','paper',"
                                "'linear','STUCKUSDT',0,'create_market','Buy','250',NULL,'1',"
                                "'terminal_manual','manual','submitting',2,NULL,1,2)")
                        if scenario == "cap":
                            for i in range(19):
                                db.store.create_robot_candidate(
                                    candidate_id=f"physical-{i}", trading_account_id=ACCOUNT,
                                    symbol=Symbol(f"PH{i}USDT"), status="APPROVED",
                                    signal_snapshot={"id":i}, approved_at_ms=1, updated_at_ms=1)
                        loader = (lambda account, **kw: db.store.load_robot_auto_decisions(account)
                                  ) if full else db.store.load_robot_auto_decisions_for_admission
                        with patch.object(db.store, "load_robot_auto_decisions_for_admission", loader), \
                             patch.object(shadow, "paper_daily_equity_facts_in_transaction",
                                          return_value=_equity("-8" if scenario == "latch" else "0")):
                            if scenario == "wait":
                                with patch.object(shadow, "_proven_source_terminal", return_value=False):
                                    first = shadow.admit_arrived_auto_candidate(
                                        db.store, ACCOUNT, source=shadow.SOURCE_SCANNER,
                                        candidate_ref="fresh", candidate_store_dir=db.candidates,
                                        clock_ms=lambda: NOW, protection_healthy=lambda: True)
                            else:
                                first = admit(db)
                            snapshot = footprint(db.store)
                            repeated = admit(db)
                        self.assertEqual(first.decision, repeated.decision)
                        self.assertFalse(repeated.decision_created)
                        self.assertEqual(snapshot, footprint(db.store))
                        self.assertEqual(json.loads(first.decision.facts_json)["portfolio_facts"]
                                         ["audit_sequence"], 302)
                        expected = {"allow":"ALLOW", "reject":"REJECT"}.get(scenario, "WAIT")
                        self.assertEqual(first.result.outcome, expected)
                        outcomes.append((first.result, first.decision, snapshot))
                    finally:
                        db.store.close()
            self.assertEqual(outcomes[0], outcomes[1], scenario)

    def test_two_connections_serialize_last_ro_and_audit_sequence(self):
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        for i in range(18):
            self.db.store.create_robot_candidate(
                candidate_id=f"physical-{i}", trading_account_id=ACCOUNT,
                symbol=Symbol(f"PH{i}USDT"), status="APPROVED",
                signal_snapshot={"id":i}, approved_at_ms=1, updated_at_ms=1)
        for ref in ("a", "b"):
            _wedge(self.db.candidates, ref, symbol=ref.upper() + "USDT")
        with patch.object(SQLiteStore, "load_robot_auto_decisions",
                          side_effect=AssertionError("full history read")):
            first, second = concurrency.AdmissionConcurrencyTests.race(
                self, lambda s: admit(self.db, s, "a"), lambda s: admit(self.db, s, "b"))
        self.assertEqual((first.result.outcome, second.result.reason_code),
                         ("ALLOW", "PORTFOLIO_AGGREGATE_CAP"))
        self.assertEqual([json.loads(r.decision.facts_json)["portfolio_facts"]["audit_sequence"]
                          for r in (first, second)], [302, 303])
        self.assertIsNone(self.db.store.get_robot_candidate("b"))
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), 303)


if __name__ == "__main__":
    unittest.main()
