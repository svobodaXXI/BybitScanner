"""Issue #645: prove the real Scanner-child-process -> PAPER_AUTO route, not a simulation of it.

The existing ``tests/test_mirror_standalone_paper_e2e.py`` proves the admission
functions and the full PAPER lifecycle (R0 gate, LIMIT, fill, STOP/TAKE, fees,
restart-no-repeat) are correct, but calls ``admit_arrived_auto_candidate``
directly from the test body. That never exercises the actual relay a
production Scanner pass uses: a spawned child process (PROCESS-ISOLATION-1)
sends the persisted candidate id over a pipe, the backend answers it on its
own (non-owner) thread, and only that dispatch -- never the test -- decides
to call into PAPER_AUTO admission.

This test drives exactly that relay, for real:

    real Scanner child process (multiprocessing spawn)
      -> pipe
      -> scanner_process._serve / _answer (backend, non-owner thread)
      -> PaperRuntime._dispatch_autopilot_shadow_scanner_candidate
      -> ShadowDeferredObserver.observe -> DEFERRED_HANDOVER (mode already PAPER_AUTO)
      -> owner thread: observe_autopilot_candidate(handover=True)
      -> admit_arrived_auto_candidate -> admit_robot_candidate
      -> real PAPER_AUTO LIMIT / fill / STOP or TAKE, exactly as the owner's manual tap

No admission function (``observe_shadow_candidate``, ``admit_paper_auto_candidate``,
``admit_arrived_auto_candidate``) is called directly by this test; only the
dispatch entry point the production Scanner pass itself calls
(``PaperRuntime._dispatch_autopilot_shadow_scanner_candidate``) is invoked, and
only because the real pipe relay delivered a real persisted candidate id to it.

Synthetic market/candle inputs only: no network, no runtime outside the temp
dir, no production DB, no VPS/AKEUSDT.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import os
import time
import unittest
from unittest import mock

from terminal.application.robot_autopilot import OUTCOME_ALLOW
from terminal.application.robot_control import start_robot
from terminal.domain.models import OrderId, Symbol
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.runtime.scanner_process import run_scan_pass_in_child_process
from tests.test_mirror_standalone_paper_e2e import (
    ACCOUNT, FIVE, LEVEL, SYMBOL, MirrorStandaloneHarness, Timeline,
)
from tests.test_robot_paper_acceptance import _MutableBookProvider, _start_robot_monitor, _wait_until

ME = "tests.test_mirror_scanner_child_process_paper_auto_e2e"


# ---- runs for real in the spawned Scanner child process (PROCESS-ISOLATION-1) ----
def _mirror_scanner_child_pass(
    *, box_plan_preparer=None, control_checkpoint=None,
    robot_candidate_observer=None, progress_observer=None,
):
    """Reconstruct the MIRROR breakout/confirmation deterministically and run the
    real production handoff/observer boundary exactly as ``main.run_scan_pass`` does.

    A spawned child (``multiprocessing`` ``spawn`` context) is a fresh
    interpreter: nothing mocked in the parent test process is visible here.
    Only inherited ``os.environ`` (standard OS process inheritance) crosses
    the boundary, so every path this needs travels through it.
    """
    from mirror_levels.levels import SOURCE_SWING_ZONE, horizontal_level
    from pattern_robot_integration import robot_candidate_observer as observe
    import mirror_scanner as ms
    import robot_candidate_store

    robot_candidate_store.DEFAULT_STORE_DIR = Path(os.environ["MIRROR_E2E_CANDIDATES_DIR"])
    mirror_root = Path(os.environ["MIRROR_E2E_MIRROR_ROOT"])
    tl = Timeline(t=int(os.environ["MIRROR_E2E_TIMELINE_T"]))
    level = horizontal_level(
        symbol=SYMBOL, timeframe="5", source=SOURCE_SWING_ZONE, pattern=None, side="lower",
        price=LEVEL, anchor_time_ms=tl.level_confirmed - FIVE, confirmed_at_ms=tl.level_confirmed,
    )

    with observe(robot_candidate_observer), \
            mock.patch.object(ms, "collect_levels", lambda *a, **k: [level]):
        # Same two-scan shape as MirrorStandaloneHarness.scan(): the breakout
        # candle first (tracked, no entry yet), then the confirming close
        # that hands the standalone entry off -- for real, in this process.
        ms.observe_mirror_levels(SYMBOL, tl.frame(tl.breakout_open + 2 * FIVE), timeframe="5",
                                  root=mirror_root, now_ms=tl.breakout_open + 2 * FIVE)
        ms.observe_mirror_levels(SYMBOL, tl.frame(tl.t), timeframe="5",
                                  root=mirror_root, now_ms=tl.t)

    if progress_observer is not None:
        progress_observer({"symbols_done": 1, "symbols_total": 1, "symbol": SYMBOL})


class MirrorScannerChildProcessPaperAutoE2E(MirrorStandaloneHarness):
    def test_scanner_child_process_candidate_reaches_paper_auto_admission_and_fill(self):
        tl = self.timeline
        book = _MutableBookProvider()
        book.set(SYMBOL, bid=Decimal("105.3"), ask=Decimal("105.4"))
        # A real CachedClosedCandleProvider (fetch=latest_scanner_closed_candle by
        # default) is required for PaperRuntime to prepare any catch-up freshness
        # evidence at all; a bare test stub (as the sibling e2e uses) leaves
        # robot_catchup_evidence unset, so admission could never prove this real
        # MIRROR candidate fresh without a test double standing in for admission
        # itself. Only the network call it would make is replaced below.
        runtime, instrument = self.runtime(CachedClosedCandleProvider(), book)
        try:
            started = start_robot(database_path=self.db)
            self.assertEqual((started.mode, started.recovery_status), ("ROBOT_RUNNING", "READY"))

            # PAPER_AUTO is already the durable mode *before* the candidate
            # arrives: the real "arrived candidate" handover route, matching
            # the already-PAPER_AUTO state on VPS, not a SHADOW-first promote.
            store = SQLiteStore.open(self.db)
            try:
                autopilot = store.get_robot_autopilot_state(ACCOUNT)
                store.update_robot_autopilot_state(
                    ACCOUNT, mode="PAPER_AUTO", expected_version=autopilot.version,
                    updated_at_ms=int(time.time() * 1000))
            finally:
                store.close()

            # Bind the cross-thread dispatcher before any candidate can arrive,
            # exactly as production starts the Robot monitor before Scanner runs.
            _start_robot_monitor(runtime)
            # Production binds this from the real protection ingress; this test
            # has no protection traffic of its own, so it reports healthy the
            # same way the sibling e2e's direct admission calls stub it.
            runtime.call(lambda owner: owner.bind_autopilot_protection_health(lambda: True))
            dispatch_candidate = runtime.call(
                lambda owner: owner._dispatch_autopilot_shadow_scanner_candidate)
            deferred_before = runtime.call(lambda owner: owner.autopilot_shadow_deferred_metrics())

            # The real catch-up/freshness evidence fetch (pattern_freshness ->
            # analyzer.candles.load_candles) is the one piece of this chain that
            # would otherwise reach the network; it is given the same closed
            # candles the MIRROR signal itself was built from, nothing invented.
            # Kept active for the whole test: the background RobotBreakoutMonitor
            # keeps polling it on its own thread for as long as the candidate
            # is live, independent of the one-shot Scanner pass below.
            def fake_load_candles(symbol, timeframe, limit, minimum=2):
                return tl.frame(tl.t)

            with mock.patch("analyzer.candles.load_candles", fake_load_candles):
                # The one and only call this test makes into the automatic
                # chain: the real scanner_process relay, with the real backend
                # dispatch method as its observer -- never an admission function.
                with mock.patch.dict(os.environ, {
                    "MIRROR_E2E_CANDIDATES_DIR": str(self.candidates),
                    "MIRROR_E2E_MIRROR_ROOT": str(self.mirror_root),
                    "MIRROR_E2E_TIMELINE_T": str(tl.t),
                }):
                    run_scan_pass_in_child_process(
                        robot_candidate_observer=dispatch_candidate,
                        target=f"{ME}:_mirror_scanner_child_pass",
                    )

                # 1. The real relay ran, and nothing was silently dropped.
                # ShadowDeferredObserver.committed only counts a completed
                # SHADOW evaluation; under PAPER_AUTO this candidate takes the
                # HANDOVER branch instead (by design neither committed nor
                # dropped -- the owner decides it directly next).
                deferred_after = runtime.call(lambda owner: owner.autopilot_shadow_deferred_metrics())
                self.assertEqual(deferred_after["dropped"], deferred_before["dropped"])
                self.assertIsNone(deferred_after["last_drop"])

                entry = self.state()["standalone_entries"][0]
                self.assertEqual(entry["handoff"], "HANDED")
                candidate_id = entry["candidate_id"]
                self.assertIsNotNone(candidate_id)

                def candidate():
                    return runtime.call(lambda owner: owner.store.get_robot_candidate(candidate_id))

                # 2. candidate_id -> decision_id: the durable decision this
                # exact relay produced, ALLOW, linked back to this candidate_id.
                record = _wait_until(lambda: candidate())
                self.assertEqual((record.status, record.robot_state["pattern"]), ("APPROVED", "MIRROR"))
                decisions = [
                    d for d in runtime.call(lambda owner: owner.store.load_robot_auto_decisions(ACCOUNT))
                    if d.resulting_candidate_id == candidate_id
                ]
                self.assertEqual(len(decisions), 1, "expected exactly one decision for this candidate_id")
                decision = decisions[0]
                self.assertEqual(decision.outcome, OUTCOME_ALLOW)
                self.assertEqual(decision.resulting_candidate_id, candidate_id)
                self.assertTrue(decision.decision_id)

                # 3. candidate_id -> execution_id: the real PAPER matcher fills
                # the LIMIT this exact candidate created.
                _wait_until(lambda: mirror_record_attached(candidate()))
                order_id = _wait_until(
                    lambda: (candidate().robot_state.get("execution") or {}).get("limit_order_id"))
                book.set(SYMBOL, bid=Decimal("105.2") + instrument.tick_size,
                         ask=Decimal("105.2") + 2 * instrument.tick_size)
                fills = _wait_until(lambda: runtime.call(
                    lambda owner: owner.store.load_executions_for_order(ACCOUNT, OrderId(order_id))) or None)
                self.assertTrue(fills, "no execution recorded for this candidate's own LIMIT order")
                trade = _wait_until(lambda: runtime.call(
                    lambda owner: owner.store.get_open_robot_trade_for_symbol(ACCOUNT, Symbol(SYMBOL))))
                self.assertEqual(trade.candidate_id, candidate_id)
                self.assertEqual(
                    (trade.pattern, trade.direction, trade.entry_path), ("MIRROR", "LONG", "LIMIT"))

                # 4. STOP/TAKE protection armed from the same candidate's frozen terms.
                prot = _wait_until(lambda: runtime.call(
                    lambda owner: owner.store.get_protection_projection(trade_key(ACCOUNT, SYMBOL))))
                self.assertIsNotNone(prot.stop_loss)
                self.assertEqual(prot.take_profit, Decimal("110.0"))
        finally:
            runtime.close()


def mirror_record_attached(candidate):
    import mirror_retest_robot as mirror

    if candidate is None:
        return False
    return mirror.mirror_record((candidate.robot_state or {}).get("execution"))


def trade_key(account, symbol):
    from terminal.domain.models import Category, PositionKey

    return PositionKey(account, Category.LINEAR, Symbol(symbol), 0)


if __name__ == "__main__":
    unittest.main()
