"""Synthetic exact-host and private L2 receipt tests; no IO or trading."""
import unittest
import json
import tempfile
from pathlib import Path
from decimal import Decimal

from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import TradingAccountId
from types import SimpleNamespace as NS

from terminal.market_data.private_box_host_evidence import (
    PrivateBoxCapture, inspect_private_box_receipts, save_first_private_box_receipt,
)


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

    def test_snapshot_only_has_no_observed_delta_continuity(self):
        store, good = setup()
        bad = {**good, "book": {**good["book"],
                 "frames": (good["book"]["frames"][0],)}}
        self.assertEqual(self.audit(store, bad).status, "NO_RECEIPT")

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

    def test_stale_complete_looking_tape_is_not_fresh_evidence(self):
        store, good = setup()
        # Frames and prints are internally contiguous but were received long ago.
        self.assertEqual(self.audit(store, good, now=5000).status, "UNKNOWN")

    def test_robot_owned_private_inspector_start_stop_and_error_isolation(self):
        events = []
        monitor = RobotBreakoutMonitor(
            lambda: None, TradingAccountId("paper"),
            get_closed_candle=lambda _: None,
            action_executor=object(),
            tick_size_provider=lambda _: Decimal("0.01"),
            clock_ms=lambda: 2100,
            tick_interval_s=3600,
        )
        monitor.bind_private_box_inspector(
            lambda identity: events.append(identity)
            or self.audit(*setup()),
        )
        self.assertEqual(monitor.inspect_private_box("box-robot-123").status, "UNKNOWN")
        self.assertEqual(events, [])
        try:
            monitor.start()
            # Start alone cannot read a book, call the inspector, or trade.
            self.assertEqual(events, [])
            result = monitor.inspect_private_box("box-robot-123")
            self.assertEqual(result.status, "RECEIPTS_OBSERVED_UNATTESTED")
            self.assertFalse(result.source_complete)
            self.assertFalse(result.trading_authorized)
            self.assertEqual(events, ["box-robot-123"])
            with self.assertRaises(RuntimeError):
                monitor.bind_private_box_inspector(lambda _: None)
        finally:
            monitor.close()
        self.assertEqual(monitor.inspect_private_box("box-robot-123").status, "UNKNOWN")
        self.assertEqual(events, ["box-robot-123"])
        with self.assertRaises(RuntimeError):
            monitor.bind_private_box_inspector(lambda _: None)

        broken = RobotBreakoutMonitor(
            lambda: None, TradingAccountId("paper"),
            get_closed_candle=lambda _: None,
            action_executor=object(),
            tick_size_provider=lambda _: Decimal("0.01"),
            clock_ms=lambda: 2100, tick_interval_s=3600,
        )
        broken.bind_private_box_inspector(
            lambda _: (_ for _ in ()).throw(RuntimeError("research failed")))
        try:
            broken.start()
            self.assertEqual(broken.inspect_private_box("box-robot-123").status, "UNKNOWN")
        finally:
            broken.close()

    def test_optional_private_box_binding_failure_does_not_block_robot_start(self):
        from terminal.runtime.paper_runtime import PaperRuntime

        started = []
        runtime = PaperRuntime.__new__(PaperRuntime)
        runtime._robot_command_dispatcher = None
        runtime._robot_breakout_monitor = NS(
            start=lambda: started.append("started"),
        )
        runtime.bind_robot_private_box_inspector = (
            lambda _: (_ for _ in ()).throw(RuntimeError("optional research failure"))
        )
        dispatcher = lambda _: None
        runtime.start_robot_monitor(
            dispatcher, private_box_research_snapshot=lambda _: None,
        )
        self.assertEqual(started, ["started"])
        self.assertIs(runtime._robot_command_dispatcher, dispatcher)

    def test_private_box_durable_robot_stop_pause_and_reconciliation_are_inert(self):
        from terminal.runtime.paper_runtime import PaperRuntime
        from terminal.market_data.private_box_host_evidence import PrivateBoxReceiptEvidence

        runtime = PaperRuntime.__new__(PaperRuntime)
        runtime._paper_account_id = TradingAccountId("paper")
        calls = []
        valid = PrivateBoxReceiptEvidence("RECEIPTS_OBSERVED_UNATTESTED")
        runtime._robot_breakout_monitor = NS(
            inspect_private_box=lambda cid: calls.append(cid) or valid,
        )
        state = NS(mode="ROBOT_RUNNING", recovery_status="READY")
        runtime.store = NS(
            is_owned_by_current_thread=lambda: True,
            get_robot_runtime_state=lambda _: state,
        )
        for mode, recovery in (
            ("ROBOT_STOPPED", "ROBOT_STOPPED"),
            ("ROBOT_RUNNING", "PAUSED"),
            ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
            ("ROBOT_STOPPED", "RECONCILIATION_REQUIRED"),
        ):
            state.mode, state.recovery_status = mode, recovery
            self.assertEqual(
                runtime.inspect_robot_private_box_receipts("box-robot-123").status,
                "UNKNOWN",
            )
        self.assertEqual(calls, [])
        state.mode, state.recovery_status = "ROBOT_RUNNING", "READY"
        self.assertIs(runtime.inspect_robot_private_box_receipts("box-robot-123"), valid)
        self.assertEqual(calls, ["box-robot-123"])
        runtime.store.is_owned_by_current_thread = lambda: False
        self.assertEqual(
            runtime.inspect_robot_private_box_receipts("box-robot-123").status,
            "UNKNOWN",
        )
        self.assertEqual(calls, ["box-robot-123"])

    def test_missing_or_reset_tape_never_claims_reconstruction(self):
        store, good = setup()
        for replacement in ((), (good["book"]["frames"][1],)):
            bad = {**good, "book": {**good["book"], "frames": replacement}}
            self.assertNotEqual(self.audit(store, bad).status,
                                "RECEIPTS_OBSERVED_UNATTESTED")
        bad = {**good, "book": {**good["book"], "active": False}}
        self.assertEqual(self.audit(store, bad).status, "UNKNOWN")


class PrivateBoxCaptureTests(unittest.TestCase):
    def test_exact_host_rotation_and_robot_stop(self):
        store, data = setup()
        calls = []
        token = None
        witness = None

        def begin(symbol, *, owner_token):
            nonlocal token, witness
            calls.append(("begin", symbol))
            if witness is None:
                token, witness = owner_token, object()
            self.assertIs(owner_token, token)
            return witness

        def end(symbol, *, owner_token):
            nonlocal witness
            calls.append(("end", symbol))
            self.assertIs(owner_token, token)
            witness = None
            return True

        def snapshot(symbol, *, expected_witness):
            self.assertIs(expected_witness, witness)
            return data

        capture = PrivateBoxCapture(NS(
            begin_protected_research_capture=begin,
            end_protected_research_capture=end,
            private_protected_research_snapshot=snapshot,
        ))
        ids = ("box-robot-123",)
        self.assertEqual(capture.sync(store.get, ids, robot_ready=False,
                                      observed_at_ms=2100).status, "UNKNOWN")
        self.assertEqual(calls, [])
        self.assertEqual(capture.sync(store.get, ids, robot_ready=True,
                                      observed_at_ms=2100).status, "NO_RECEIPT")
        self.assertEqual(capture.observe(store.get, robot_ready=True,
                                         observed_at_ms=2100).status,
                         "RECEIPTS_OBSERVED_UNATTESTED")
        store[ids[0]].state_revision = 2
        self.assertEqual(capture.observe(store.get, robot_ready=True,
                                         observed_at_ms=2100).status, "UNKNOWN")
        self.assertEqual(calls, [("begin", "BTCUSDT"), ("end", "BTCUSDT")])
        capture.sync(store.get, ids, robot_ready=True, observed_at_ms=2100)
        capture.sync(store.get, ids, robot_ready=False, observed_at_ms=2100)
        self.assertEqual(calls[-2:], [("begin", "BTCUSDT"), ("end", "BTCUSDT")])
        capture.close()
        self.assertEqual(len(calls), 4)

    def test_missing_context_and_invalid_host_do_not_subscribe(self):
        store, _ = setup()
        calls = []
        capture = PrivateBoxCapture(NS(
            begin_protected_research_capture=lambda symbol, **_k: calls.append(symbol),
            end_protected_research_capture=lambda *_a, **_k: False,
        ))
        self.assertEqual(capture.sync(store.get, ("box-robot-other",),
                                      robot_ready=True, observed_at_ms=2100).status,
                         "NO_PROVEN_HOST")
        self.assertEqual(calls, [])
        capture.sync(store.get, ("box-robot-123",),
                     robot_ready=True, observed_at_ms=2100)
        self.assertEqual(calls, ["BTCUSDT"])
        self.assertEqual(capture.observe(store.get, robot_ready=True,
                                         observed_at_ms=2100).status, "NO_RECEIPT")
        capture.close()


    def test_only_validated_detached_receipts_reach_private_sink(self):
        store, data = setup()
        witness = object()
        snapshots = []
        saved = []
        old = NS(trade_id="old", timestamp_ms=900,
                 received_at_ms=950, sequence=1)
        data["trades"]["prints"] = (old, *data["trades"]["prints"])

        def snapshot(symbol, *, expected_witness):
            snapshots.append(symbol)
            self.assertIs(expected_witness, witness)
            return data

        capture = PrivateBoxCapture(NS(
            begin_protected_research_capture=lambda *_a, **_k: witness,
            end_protected_research_capture=lambda *_a, **_k: True,
            private_protected_research_snapshot=snapshot,
        ))
        capture.sync(store.get, ("box-robot-123",),
                     robot_ready=True, observed_at_ms=2100)
        result = capture.observe(store.get, robot_ready=True,
                                 observed_at_ms=2100,
                                 save=lambda *args: saved.append(args))
        self.assertEqual(result.status, "RECEIPTS_OBSERVED_UNATTESTED")
        self.assertEqual(snapshots, ["BTCUSDT"])
        self.assertEqual(len(saved), 1)
        self.assertIs(saved[0][1]["book"], data["book"])
        self.assertEqual(saved[0][1]["trades"]["prints"],
                         (data["trades"]["prints"][1],))
        self.assertFalse(saved[0][0].trading_authorized)
        self.assertFalse(saved[0][0].source_complete)
        capture.observe(store.get, robot_ready=False, observed_at_ms=2100,
                        save=lambda *args: saved.append(args))
        self.assertEqual(len(saved), 1)


    def test_private_sink_is_single_sample_and_never_overwrites(self):
        from terminal.market_data.impulse_observation import ObservedPrint

        store, data = setup()
        data["trades"]["prints"] = (ObservedPrint(
            "t1", 2000, 9, "Buy", Decimal("100"), Decimal("1"), 2002,
        ),)
        result = inspect_private_box_receipts(
            store.get, lambda _: data, candidate_id="box-robot-123",
            observed_at_ms=2100,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.json"
            self.assertFalse(save_first_private_box_receipt(
                path, result, data, allow_write=lambda: False))
            self.assertFalse(path.exists())
            self.assertTrue(save_first_private_box_receipt(
                path, result, data, allow_write=lambda: True))
            original = path.read_bytes()
            parsed = json.loads(original)
            self.assertFalse(parsed["source_complete"])
            self.assertFalse(parsed["trading_authorized"])
            self.assertEqual(parsed["trades"]["prints"][0]["received_at_ms"], 2002)
            self.assertFalse(save_first_private_box_receipt(
                path, result, data, allow_write=lambda: True))
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
