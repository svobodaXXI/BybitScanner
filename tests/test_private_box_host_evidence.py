"""Synthetic exact-host and private L2 receipt tests; no IO or trading."""
import unittest
from types import SimpleNamespace as NS

from terminal.market_data.private_box_host_evidence import inspect_private_box_receipts


def setup():
    source = dict(
        identity={"symbol": "BTCUSDT", "direction": "LONG"},
        plan={"direction": "LONG"}, decision_time_ms=900,
        pattern="IKIGAI_BOX", environment="PAPER", execution_authorized=False,
    )
    host = NS(candidate_id="box-robot-123", trading_account_id=NS(value="paper"),
              symbol=NS(value="BTCUSDT"), status="APPROVED",
              signal_snapshot={**source, "source_box_candidate_id": "box-plan-123"},
              robot_state={"phase": "BOX_ENTRY_READY",
                           "source_box_candidate_id": "box-plan-123"},
              state_revision=1, snapshot_sha256="a" * 64, approved_at_ms=1000)
    parent = NS(candidate_id="box-plan-123", trading_account_id=NS(value="paper"),
                symbol=NS(value="BTCUSDT"), status="BOX_PLAN_ONLY",
                robot_state=None, signal_snapshot=source)
    store = {"box-robot-123": host, "box-plan-123": parent}

    def frame(kind, uid, received):
        return (received, {"type": kind, "topic": "orderbook.1000.BTCUSDT",
                           "cts": received - 1, "ts": received - 1,
                           "data": {"s": "BTCUSDT", "u": uid, "seq": uid}})
    evidence = {
        "book": {"symbol": "BTCUSDT", "depth": 1000, "active": True,
                 "source_complete": False, "trading_authorized": False,
                 "epoch": 2, "frames": (
                     frame("snapshot", 7, 2000), frame("delta", 8, 2001))},
        "trades": {"symbol": "BTCUSDT", "generation": 4,
                   "gap_or_truncation": True,  # never a complete tape
                   "prints": (NS(trade_id="t1", timestamp_ms=2000,
                                 received_at_ms=2002, sequence=9),)},
    }
    return store, evidence


class PrivateBoxReceiptTests(unittest.TestCase):
    def audit(self, store, data, *, now=2100):
        return inspect_private_box_receipts(
            store.get, lambda _symbol: data,
            candidate_id="box-robot-123", observed_at_ms=now,
        )

    def test_missing_host_cannot_trigger_capture(self):
        store, _ = setup()
        outcome = inspect_private_box_receipts(
            store.get,
            lambda _: (_ for _ in ()).throw(AssertionError("capture was accessed")),
            candidate_id="box-robot-other", observed_at_ms=2100,
        )
        self.assertEqual(outcome.status, "NO_PROVEN_HOST")

    def test_exact_host_without_witness_is_no_receipt(self):
        store, _ = setup()
        value = self.audit(store, None)
        self.assertEqual(value.status, "NO_RECEIPT")
        self.assertEqual(value.snapshot_sha256, "a" * 64)
        self.assertFalse(value.source_complete)
        self.assertFalse(value.trading_authorized)

    def test_receive_times_do_not_certify_source_or_trade_authority(self):
        store, evidence = setup()
        value = self.audit(store, evidence)
        self.assertEqual(value.status, "RECEIPTS_OBSERVED_UNATTESTED")
        self.assertEqual((value.observed_book_frames, value.observed_prints), (2, 1))
        self.assertFalse(value.source_complete)
        self.assertFalse(value.trading_authorized)

    def test_unapproved_or_wrong_parent_is_not_a_proven_host(self):
        store, evidence = setup()
        record = store["box-robot-123"]
        for changes in (
            {"status": "BOX_PLAN_ONLY"},
            {"approved_at_ms": None},
            {"trading_account_id": NS(value="main")},
            {"state_revision": 0},
            {"signal_snapshot": {**record.signal_snapshot,
                                 "source_box_candidate_id": "box-plan-other"}},
        ):
            store["box-robot-123"] = NS(**{**vars(record), **changes})
            self.assertEqual(self.audit(store, evidence).status, "NO_PROVEN_HOST")
        store["box-robot-123"] = record
        store["box-plan-123"].signal_snapshot = {}
        self.assertEqual(self.audit(store, evidence).status, "NO_PROVEN_HOST")

    def test_mismatched_l2_and_backdated_trade_receipts_fail_closed(self):
        store, good = setup()
        frame0, frame1 = good["book"]["frames"]
        for replacement in (
            (frame0, (2001, {**frame1[1], "data": {
                "s": "BTCUSDT", "u": 11, "seq": 12}})),
            (frame0, (2001, {**frame1[1], "topic":
                              "orderbook.1000.ETHUSDT"})),
            ((500, frame0[1]), frame1),
        ):
            bad = {**good, "book": {**good["book"], "frames": replacement}}
            self.assertEqual(self.audit(store, bad).status, "UNKNOWN")
        for received, expected in ((500, "NO_RECEIPT"), (2500, "UNKNOWN")):
            bad = {**good, "trades": {**good["trades"], "prints": (
                NS(trade_id="t1", timestamp_ms=2000,
                   received_at_ms=received, sequence=9),)}}
            self.assertEqual(self.audit(store, bad).status, expected)

    def test_missing_or_reset_tape_never_claims_reconstruction(self):
        store, good = setup()
        for replacement in ((), (good["book"]["frames"][1],)):
            bad = {**good, "book": {**good["book"], "frames": replacement}}
            self.assertNotEqual(self.audit(store, bad).status,
                                "RECEIPTS_OBSERVED_UNATTESTED")
        bad = {**good, "book": {**good["book"], "active": False}}
        self.assertEqual(self.audit(store, bad).status, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
