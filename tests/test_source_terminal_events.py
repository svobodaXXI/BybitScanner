"""A3-R3b focused tests: sidecar source-terminal events and SHADOW reservation release.

Disposable SQLite files only; no producers, services, network or orders submitted.
"""
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import OrderId, OrderSide, Symbol
from terminal.persistence.source_terminal_events import (
    SourceTerminalEvent, SourceTerminalEventError, append_source_terminal_event,
    load_terminal_identities, source_terminal_events_path,
)
from tests.test_robot_autopilot_shadow import _Db, _wedge, ACCOUNT


def _event(ref, sha, *, account="paper", source="SCANNER", status="EXPIRED", rule="WEDGE_APEX_NO_BREAKOUT"):
    return SourceTerminalEvent(
        trading_account_id=account, candidate_ref=ref, snapshot_sha256=sha, source=source,
        terminal_status=status, rule=rule, rule_version="1",
        evidence_json=json.dumps({"apex_index": 780.875}), observed_at_ms=7000,
    )


class SourceTerminalEventStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = source_terminal_events_path(Path(self.tmp.name) / "paper.sqlite3")

    def test_path_follows_paper_db_like_live_accounts(self):
        self.assertEqual(self.path.name, "paper.source_terminal_events.sqlite3")

    def test_missing_store_proves_nothing_and_is_not_created(self):
        self.assertIsNone(load_terminal_identities(self.path, "paper"))
        self.assertFalse(self.path.exists())

    def test_append_is_idempotent_and_never_overwrites(self):
        event = _event("ref", "a" * 64)
        self.assertEqual(append_source_terminal_event(self.path, event), (event, True))
        self.assertEqual(append_source_terminal_event(self.path, event), (event, False))
        with self.assertRaises(SourceTerminalEventError):
            append_source_terminal_event(self.path, _event("ref", "a" * 64, status="INVALIDATED"))
        self.assertEqual(load_terminal_identities(self.path, "paper"), frozenset({("ref", "a" * 64)}))

    def test_source_and_status_are_validated(self):
        for source, status in (("BOX_PLAN", "INVALIDATED"), ("SCANNER", "CLOSED"), ("OTHER", "EXPIRED")):
            with self.subTest(source=source, status=status), self.assertRaises(SourceTerminalEventError):
                append_source_terminal_event(self.path, _event("ref", "a" * 64, source=source, status=status))
        append_source_terminal_event(self.path, _event("box", "b" * 64, source="BOX_PLAN"))

    def test_rows_cannot_be_updated_or_deleted(self):
        append_source_terminal_event(self.path, _event("ref", "a" * 64))
        connection = sqlite3.connect(self.path)
        self.addCleanup(connection.close)
        for statement in ("UPDATE source_terminal_events SET terminal_status = 'INVALIDATED'",
                          "DELETE FROM source_terminal_events"):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                connection.execute(statement)

    def test_foreign_file_is_rejected(self):
        sqlite3.connect(self.path).close()  # empty SQLite without our application_id
        with self.assertRaises(SourceTerminalEventError):
            load_terminal_identities(self.path, "paper")


class ShadowReservationReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = _Db(self.root)
        self.store = self.db.store
        self.addCleanup(self.store.close)
        self.events = source_terminal_events_path(self.store.path)

    def allow(self, ref, symbol):
        _wedge(self.db.candidates, ref, symbol=symbol)
        result = self.db.observe(ref, health=lambda: True).result
        self.assertEqual((result.outcome, result.reason_code), ("ALLOW", "ELIGIBLE"))
        return next(d for d in self.db.decisions() if d.candidate_ref == ref and d.outcome == "ALLOW")

    def facts(self):
        with self.store.autopilot_decision_transaction():
            return collect_portfolio_facts(self.store, ACCOUNT)

    def test_exact_identity_releases_only_that_reservation(self):
        released = self.allow("done", "DONEUSDT")
        kept = self.allow("live", "LIVEUSDT")
        append_source_terminal_event(self.events, _event(released.candidate_ref, released.snapshot_sha256))
        facts = self.facts()
        self.assertEqual(facts["source_terminal_events"], "AVAILABLE")
        self.assertEqual(facts["occupied_ro"], 1)
        self.assertEqual([r["identity"] for r in facts["reservations"]], ["shadow:" + kept.candidate_ref])
        self.assertEqual(facts["released_shadow_reservations"], [{
            "candidate_ref": "done", "snapshot_sha256": released.snapshot_sha256, "symbol": "DONEUSDT"}])

    def test_other_sha_or_account_releases_nothing(self):
        decision = self.allow("done", "DONEUSDT")
        append_source_terminal_event(self.events, _event("done", "f" * 64))
        append_source_terminal_event(self.events, _event("done", decision.snapshot_sha256, account="other"))
        facts = self.facts()
        self.assertEqual((facts["occupied_ro"], facts["released_shadow_reservations"]), (1, []))

    def test_physical_obligation_on_symbol_keeps_reservation(self):
        decision = self.allow("done", "DONEUSDT")
        self.store.create_paper_limit(client_action_id="o", request_fingerprint="o", order_id=OrderId("o"),
            order_link_id="o", trading_account_id=ACCOUNT, symbol=Symbol("DONEUSDT"), side=OrderSide.BUY,
            price=Decimal(1), quantity=Decimal(125), created_at_ms=1)
        append_source_terminal_event(self.events, _event("done", decision.snapshot_sha256))
        facts = self.facts()
        self.assertIn("shadow:done", [r["identity"] for r in facts["reservations"]])
        self.assertEqual(facts["released_shadow_reservations"], [])

    def test_unreadable_store_keeps_every_reservation(self):
        decision = self.allow("done", "DONEUSDT")
        append_source_terminal_event(self.events, _event("done", decision.snapshot_sha256))
        connection = sqlite3.connect(self.events)
        connection.execute("PRAGMA user_version = 99")
        connection.close()
        facts = self.facts()
        self.assertEqual(facts["source_terminal_events"], "UNAVAILABLE")
        self.assertEqual((facts["available"], facts["occupied_ro"]), (True, 1))
        self.assertEqual(facts["released_shadow_reservations"], [])

    def test_absent_store_keeps_reservation_and_creates_nothing(self):
        self.allow("done", "DONEUSDT")
        facts = self.facts()
        self.assertEqual((facts["source_terminal_events"], facts["occupied_ro"]), ("ABSENT", 1))
        self.assertFalse(self.events.exists())


if __name__ == "__main__":
    unittest.main()
