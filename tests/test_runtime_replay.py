from decimal import Decimal
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from terminal.domain.models import OrderId, OrderSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_http_server import (
    RobotProtectionCoverageManager,
    SerializedPaperRuntime,
)
from terminal.runtime.paper_runtime import PaperRuntime
from tests.runtime_replay import (
    RuntimeReplayEvent,
    RuntimeReplayFixture,
    _make_runtime,
    _OfflineRecoverySession,
    _ReplayHub,
    _seed_pre_limit_candidates,
    box_candidate_facts,
    run_coverage_manager_replay,
    run_manager_stall_replay,
    run_owner_stall_replay,
    run_runtime_replay,
    seed_unowned_box_candidates,
    tick_box_monitor,
)
from tests.test_robot_paper_execution_threading import (
    ACCOUNT_ID as TOPOLOGY_ACCOUNT_ID,
    SYMBOL as TOPOLOGY_SYMBOL,
    _build_runtime as _build_topology_runtime,
    _candle_at,
    _FixedCandleProvider,
    _MutableBookProvider,
    _PoisonLiveAdapterFactory,
    _publish_live_snapshot,
    _seed_retest_detected_candidate,
    _wait_until,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "runtime_replays"
    / "smoke_ordered_entry_pending_v1.json"
)
OVERFLOW_FIXTURE = FIXTURE.with_name("entry_pending_overflow_20260927_v1.json")
INCIDENT_SYMBOLS = ("2ZUSDT", "ARBUSDT", "ARIAUSDT", "ARKUSDT", "CFGUSDT")


class RuntimeReplayContractTests(unittest.TestCase):
    def test_smoke_fixture_is_deterministic_and_preserves_fifo(self):
        fixture = RuntimeReplayFixture.load(FIXTURE)

        first = run_runtime_replay(fixture)
        second = run_runtime_replay(fixture)

        expected = tuple(event.event_id for event in fixture.events)
        self.assertEqual(first.processed_event_ids, expected)
        self.assertEqual(second.processed_event_ids, expected)
        self.assertEqual(first.overflow_event_ids, ())
        self.assertEqual(second.overflow_event_ids, ())
        self.assertEqual(first.event_errors, ())
        self.assertEqual(second.event_errors, ())
        self.assertEqual(first.continuity_loss, None)
        self.assertEqual(second.continuity_loss, None)

        # Timing values are intentionally not compared: scheduling is not a
        # correctness oracle. The stable contract is the metric surface plus
        # deterministic event order and final drained state.
        self.assertEqual(first.metric_keys, second.metric_keys)
        self.assertEqual(first.metrics["capacity"], 64)
        self.assertEqual(second.metrics["capacity"], 64)
        self.assertEqual(first.metrics["current_pending"], 0)
        self.assertEqual(second.metrics["current_pending"], 0)
        self.assertGreaterEqual(first.metrics["high_watermark"], 1)
        self.assertGreaterEqual(second.metrics["high_watermark"], 1)
        self.assertLessEqual(first.metrics["high_watermark"], len(fixture.events))
        self.assertLessEqual(second.metrics["high_watermark"], len(fixture.events))
        self.assertEqual(first.metrics["last_symbol"], "2ZUSDT")
        self.assertEqual(first.metrics["last_role"], "ENTRY_PENDING")
        self.assertIsNone(first.metrics["last_overflow_symbol"])


class RuntimeReplayEntryPendingOverflowTests(unittest.TestCase):
    """RVL-R2: pre-LIMIT candidates under a bounded reconcile stall, via the manager.

    RED before RVL-R4 (pre-LIMIT RETEST_DETECTED was ENTRY_PENDING-subscribed and the
    stall overflowed the 64 ingress); GREEN since RVL-R4 moved ENTRY_PENDING to the
    durable resting-LIMIT boundary.

    Lifecycle state: five APPROVED / RETEST_DETECTED candidates, NO limit_order_id, no
    resting LIMIT -- nothing a book event could fill. The production path under test is
    RobotProtectionCoverageManager (role discovery -> hub subscription -> _on_update)
    -> SerializedPaperRuntime.enqueue -> process_robot_market_event, with the
    production robot_reconcile() owner call stalled at its five per-candidate lookups.

    The fixture is RECONSTRUCTED from the 2026-09-27 incident envelope (not a raw
    capture). RECONSTRUCTED ASSUMPTION: 13 stream events per lookup is the smallest whole
    stall for which one reconcile spans capacity + 1 events (5 x 13 = 65); at the
    orderbook.1000 cadence (~25 events/s for five symbols) that is ~2.6 s, inside the
    recorded pre-#293 reconcile (9065 ms) and above the post-#293 ~1.4 s. Saved evidence
    does not prove the post-#293 64/64 came from reconcile alone.
    """

    CAPACITY = 64
    STALL_EVENTS_PER_LOOKUP = 13

    def test_pre_limit_traffic_during_bounded_reconcile_stall_never_enters_protection_ingress(self):
        fixture = RuntimeReplayFixture.load(OVERFLOW_FIXTURE)
        ids = tuple(event.event_id for event in fixture.events)
        self.assertIn("RECONSTRUCTED", fixture.name.upper())
        self.assertEqual(sorted({event.symbol for event in fixture.events}), list(INCIDENT_SYMBOLS))

        result = run_manager_stall_replay(
            fixture,
            stall_events_per_lookup=self.STALL_EVENTS_PER_LOOKUP,
            protection_ingress_capacity=self.CAPACITY,
        )

        # Replay invariants, valid now and after a lifecycle fix: the incident's
        # lifecycle state, the bounded stall itself, and event accounting.
        self.assertTrue(result.seeded_pre_limit)
        step = self.STALL_EVENTS_PER_LOOKUP
        span = len(INCIDENT_SYMBOLS) * step
        self.assertEqual(
            result.stall_event_ids, tuple(ids[start:start + step] for start in range(0, span, step)),
        )
        self.assertEqual(result.lookup_threads, ("paper-runtime-owner",) * len(INCIDENT_SYMBOLS))
        self.assertGreater(len(ids), span)
        self.assertEqual(set(result.unsubscribed_event_ids) | set(result.delivered_event_ids), set(ids))
        self.assertFalse(set(result.unsubscribed_event_ids) & set(result.delivered_event_ids))
        self.assertEqual(result.processed_event_ids, result.admitted_event_ids)
        self.assertEqual(result.event_errors, ())
        self.assertEqual(result.final_health["ingress"]["current_pending"], 0)

        health = result.health_after_producer
        evidence = (
            f"roles={dict(result.covered_roles)} delivered={len(result.delivered_event_ids)} "
            f"unsubscribed={len(result.unsubscribed_event_ids)} "
            f"admitted={len(result.admitted_event_ids)} overflow={result.overflow_event_ids} "
            f"suppressed_after_unhealthy={len(result.suppressed_event_ids)} "
            f"fence_overflows={result.fence_overflows} "
            f"pending_at_stall_release={result.pending_at_stall_release}/{self.CAPACITY} "
            f"high_watermark={health['ingress']['high_watermark']} "
            f"unhealthy={dict(health['unhealthy_symbols'])} "
            f"reconcile={result.reconcile_outcome}"
        )
        # Target contract: events of symbols that have no fill-capable resting LIMIT are
        # not protection-critical, so none of them may enter protection ingress,
        # overflow it, or turn any symbol unhealthy. This is NOT "all 80 events
        # processed": they do not belong to protection ingress at all.
        self.assertEqual(dict(result.covered_roles), {}, evidence)
        self.assertEqual(result.unsubscribed_event_ids, ids, evidence)
        self.assertEqual(result.admitted_event_ids + result.overflow_event_ids, (), evidence)
        self.assertEqual(result.fence_overflows, 0, evidence)
        self.assertEqual(health["ingress"]["high_watermark"], 0, evidence)
        self.assertEqual(health["ingress"]["capacity"], self.CAPACITY, evidence)
        self.assertEqual(health["unhealthy_symbols"], {}, evidence)
        self.assertTrue(health["healthy"], evidence)


class RuntimeReplayEntryPendingIngressBoundaryTests(unittest.TestCase):
    """RVL-R3 (A): ingress overload boundary, characterized under a fully held owner.

    Holding the owner for the whole stream is a saturation characterization, not a
    product scenario: it freezes where admission stops and that every later event
    becomes observable, fail-closed continuity loss. GREEN on current code, and it
    stays GREEN after a lifecycle fix because the ingress itself is unchanged.
    """

    CAPACITY = 64
    LAST_ADMITTED = "ARKUSDT:163:5063"
    FIRST_LOST = "CFGUSDT:164:5064"

    def test_direct_protection_traffic_overflows_at_capacity_during_the_bounded_stall(self):
        # Lower-level characterization of the RVL-R2 stall, events offered DIRECTLY to
        # enqueue(): if these events reach protection ingress at all, a 5 x 13 stall
        # fills it. No lifecycle fix can turn this one RED, so it is not the R2 contract;
        # it shows R4 must keep the stream out of ingress rather than rely on capacity.
        fixture = RuntimeReplayFixture.load(OVERFLOW_FIXTURE)
        ids = tuple(event.event_id for event in fixture.events)
        result = run_owner_stall_replay(
            fixture, stall_events_per_lookup=13, protection_ingress_capacity=self.CAPACITY,
        )

        self.assertEqual(result.lookup_threads, ("paper-runtime-owner",) * len(INCIDENT_SYMBOLS))
        self.assertEqual(
            result.stall_event_ids,
            tuple(ids[start:start + 13] for start in range(0, 5 * 13, 13)),
        )
        self.assertEqual(result.pending_at_stall_release, self.CAPACITY)
        # Deterministic: the owner runs no protection task until the stall ends, so the
        # first 64 events are admitted in FIFO order and event 65 is the first refused.
        self.assertEqual(result.processed_event_ids[:self.CAPACITY], ids[:self.CAPACITY])
        self.assertEqual(result.overflow_event_ids[0], self.FIRST_LOST)
        processed = set(result.processed_event_ids)
        self.assertEqual(result.processed_event_ids, tuple(i for i in ids if i in processed))
        self.assertEqual(result.overflow_event_ids, tuple(i for i in ids if i not in processed))
        self.assertEqual(result.event_errors, ())
        self.assertEqual(result.metrics["high_watermark"], self.CAPACITY)
        self.assertEqual(result.metrics["current_pending"], 0)

    def test_owner_boundary_admits_exact_fifo_prefix_and_signals_every_later_event(self):
        fixture = RuntimeReplayFixture.load(OVERFLOW_FIXTURE)
        ids = tuple(event.event_id for event in fixture.events)
        result = run_runtime_replay(
            fixture, protection_ingress_capacity=self.CAPACITY, owner_held_during_production=True,
        )

        self.assertEqual(ids[self.CAPACITY - 1:self.CAPACITY + 1], (self.LAST_ADMITTED, self.FIRST_LOST))
        self.assertEqual(result.processed_event_ids, ids[:self.CAPACITY])
        # No silent drop: every event past the boundary raised ProtectionIngressOverflow.
        self.assertEqual(result.overflow_event_ids, ids[self.CAPACITY:])
        self.assertEqual(result.event_errors, ())
        self.assertEqual(result.saturated_metrics["current_pending"], self.CAPACITY)
        self.assertEqual(result.metrics["high_watermark"], self.CAPACITY)
        self.assertEqual(
            (result.metrics["last_overflow_symbol"], result.metrics["last_overflow_role"]),
            ("CFGUSDT", "ENTRY_PENDING"),
        )
        # The owner never fences by itself; fail-closed is owned by the admission caller.
        self.assertIsNone(result.continuity_loss)

    def test_coverage_manager_turns_every_lost_entry_pending_event_into_continuity_loss(self):
        fixture = RuntimeReplayFixture.load(OVERFLOW_FIXTURE)
        ids = tuple(event.event_id for event in fixture.events)
        result = run_coverage_manager_replay(fixture, protection_ingress_capacity=self.CAPACITY)
        entry_pending = {symbol: "ENTRY_PENDING" for symbol in INCIDENT_SYMBOLS}
        lost_by_symbol = {symbol: "ingress_overflow" for symbol in INCIDENT_SYMBOLS}

        self.assertEqual(result.covered_roles, entry_pending)
        self.assertEqual(result.admitted_event_ids, ids[:self.CAPACITY])
        self.assertEqual(result.processed_event_ids, ids[:self.CAPACITY])
        self.assertEqual(result.admitted_event_ids[-1], self.LAST_ADMITTED)
        # The first lost event of every symbol (possible first-fill evidence) overflows loudly...
        self.assertEqual(result.overflow_event_ids, (
            self.FIRST_LOST, "2ZUSDT:165:5065", "ARBUSDT:166:5066",
            "ARIAUSDT:167:5067", "ARKUSDT:168:5068",
        ))
        # ...and every later one is suppressed only after its symbol is already unhealthy.
        self.assertEqual(result.overflow_event_ids + result.suppressed_event_ids, ids[self.CAPACITY:])
        for event_id in result.suppressed_event_ids:
            symbol = event_id.split(":", 1)[0]
            first = next(e for e in result.overflow_event_ids if e.startswith(f"{symbol}:"))
            self.assertLess(ids.index(first), ids.index(event_id))
        # While saturated the durable fence itself cannot be admitted (one refusal per
        # symbol); the in-memory unhealthy state is the only immediate fail-closed signal.
        self.assertEqual(result.fence_overflows, len(INCIDENT_SYMBOLS))
        # DIAGNOSTIC DEFECT (evidence only, not fixed here): the refused fence enqueue
        # (symbol="") overwrites last_overflow_symbol/role, so the ingress metrics logged
        # and served during the incident hide which protection symbol overflowed.
        self.assertEqual(
            (result.health_during_overflow["ingress"]["last_overflow_symbol"],
             result.health_during_overflow["ingress"]["last_overflow_role"]),
            (None, "UNKNOWN"),
        )

        for health in (result.health_during_overflow, result.health_after_resync):
            self.assertFalse(health["healthy"])
            self.assertEqual(health["unhealthy_symbols"], lost_by_symbol)
            # Coverage stays ENTRY_PENDING / protection-critical; loss never drops it.
            self.assertEqual(health["coverage_roles"], entry_pending)
            self.assertEqual(health["covered_symbols"], tuple(sorted(INCIDENT_SYMBOLS)))
        # Watchdog resync durably fences at the first lost symbol; without an
        # authoritative REST snapshot nothing is ever reported healthy again.
        self.assertEqual(result.durable_continuity_loss, ("CFGUSDT", "ingress_overflow"))
        self.assertEqual(
            sorted(params["symbol"] for _url, params in result.recovery_requests),
            sorted(INCIDENT_SYMBOLS),
        )


class RuntimeReplayEntryPendingLifecycleBoundaryTests(unittest.TestCase):
    """RVL-R3 (B): current ENTRY_PENDING role derivation around the entry fill.

    Characterizes PaperRuntime.robot_protection_coverage_roles(), which is
    pattern-agnostic (Wedge and L-shape RETEST_DETECTED behave identically), for the
    durable fill/finalization states not already frozen by the mixed coverage fixture
    in test_terminal_paper_runtime (active LIMIT, pre-LIMIT, missing LIMIT,
    WAITING_BREAKOUT, EXPIRED/INVALIDATED, EXPOSURE/OBLIGATION).
    """

    def test_entry_pending_covers_every_fill_state_until_atomic_exposure_handover(self):
        account = TradingAccountId("paper")
        with tempfile.TemporaryDirectory() as temp:
            runtime = _make_runtime(Path(temp) / "paper_runtime.sqlite3")
            try:
                def candidate(candidate_id, symbol, order_id, status, filled):
                    runtime.store.create_paper_limit(
                        client_action_id=f"seed-{order_id}", request_fingerprint=f"fp-{order_id}",
                        order_id=OrderId(order_id), order_link_id=f"link-{order_id}",
                        trading_account_id=account, symbol=Symbol(symbol), side=OrderSide.BUY,
                        price=Decimal("1"), quantity=Decimal("1"), created_at_ms=1_000,
                    )
                    runtime.store._connection.execute(
                        "UPDATE paper_limit_orders SET status=?, filled_quantity=? WHERE order_id=?",
                        (status, filled, order_id),
                    )
                    record, _ = runtime.store.create_robot_candidate(
                        candidate_id=candidate_id, trading_account_id=account, symbol=Symbol(symbol),
                        status="APPROVED",
                        signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge", "case": candidate_id},
                        approved_at_ms=1_000, updated_at_ms=1_000,
                    )
                    runtime.store.save_robot_candidate_state(
                        candidate_id, status="APPROVED",
                        robot_state={"phase": "RETEST_DETECTED",
                                     "execution": {"limit_order_id": order_id}},
                        expected_revision=record.state_revision, updated_at_ms=1_001,
                    )

                candidate("c-partial", "PARTUSDT", "o-partial", "partially_filled", "0.4")
                candidate("c-filled", "FILLUSDT", "o-filled", "filled", "1")
                candidate("c-cancel-filled", "CXLFUSDT", "o-cancel-filled", "cancelled", "0.4")
                candidate("c-cancel", "CXLUSDT", "o-cancel", "cancelled", "0")
                # Two approved lifecycles on one symbol: any live one keeps coverage.
                candidate("c-dup-dead", "DUPUSDT", "o-dup-dead", "cancelled", "0")
                candidate("c-dup-live", "DUPUSDT", "o-dup-live", "open", "0")

                def unlinked(candidate_id, symbol, robot_state):
                    record, _ = runtime.store.create_robot_candidate(
                        candidate_id=candidate_id, trading_account_id=account, symbol=Symbol(symbol),
                        status="APPROVED",
                        signal_snapshot={"symbol": symbol, "pattern": "IKIGAI_BOX", "case": candidate_id},
                        approved_at_ms=1_000, updated_at_ms=1_000,
                    )
                    runtime.store.save_robot_candidate_state(
                        candidate_id, status="APPROVED", robot_state=robot_state,
                        expected_revision=record.state_revision, updated_at_ms=1_001,
                    )

                # RVL-R4 start boundary: pre-LIMIT RETEST_DETECTED is not ENTRY_PENDING.
                unlinked("c-pre", "PREUSDT", {"phase": "RETEST_DETECTED", "execution": {}})
                # Ikigai Box grid: the same resting-LIMIT rule over its four linked LIMITs.
                def grid(prefix, symbol, statuses):
                    for index, status in enumerate(statuses):
                        runtime.store.create_paper_limit(
                            client_action_id=f"seed-{prefix}-{index}",
                            request_fingerprint=f"fp-{prefix}-{index}",
                            order_id=OrderId(f"{prefix}-{index}"),
                            order_link_id=f"link-{prefix}-{index}",
                            trading_account_id=account, symbol=Symbol(symbol), side=OrderSide.BUY,
                            price=Decimal("1"), quantity=Decimal("1"), created_at_ms=1_000,
                        )
                        runtime.store._connection.execute(
                            "UPDATE paper_limit_orders SET status=? WHERE order_id=?",
                            (status, f"{prefix}-{index}"),
                        )

                grid("o-box", "BOXUSDT", ("open", "cancelled", "cancelled", "cancelled"))
                grid("o-boxc", "BOXCUSDT", ("cancelled",) * 4)
                unlinked("c-box", "BOXUSDT", {"phase": "BOX_ENTRY_READY", "execution": {
                    "limit_order_ids": [f"o-box-{index}" for index in range(4)]}})
                unlinked("c-box-dead", "BOXCUSDT", {"phase": "BOX_ENTRY_READY", "execution": {
                    "limit_order_ids": [f"o-boxc-{index}" for index in range(4)]}})

                # Any fill (partial, full, or a filled-then-cancelled remainder) stays
                # ENTRY_PENDING until finalization; a cancelled unfilled LIMIT drops out.
                self.assertEqual(runtime.robot_protection_coverage_roles(), {
                    "BOXUSDT": "ENTRY_PENDING",
                    "CXLFUSDT": "ENTRY_PENDING",
                    "DUPUSDT": "ENTRY_PENDING",
                    "FILLUSDT": "ENTRY_PENDING",
                    "PARTUSDT": "ENTRY_PENDING",
                })

                # Finalization: create_robot_trade inserts the trade and flips the
                # candidate APPROVED -> OPEN in one transaction, so ENTRY_PENDING hands
                # over directly to EXPOSURE with no uncovered state in between.
                runtime.store.create_robot_trade(
                    trade_id="t-filled", trading_account_id=account, candidate_id="c-filled",
                    symbol=Symbol("FILLUSDT"), direction="LONG", pattern="Falling Wedge",
                    source_timeframe="1", signal_time_ms=1_000, entry_time_ms=2_000,
                    entry_path="LIMIT", actual_wv=Decimal("1"), average_entry=Decimal("1"),
                    stop_price=Decimal("0.9"), take_price=Decimal("1.2"),
                    entry_quantity=Decimal("1"), entry_position_version=1, created_at_ms=2_000,
                )
                self.assertEqual(runtime.robot_protection_coverage_roles()["FILLUSDT"], "EXPOSURE")
            finally:
                runtime.close()


class RuntimeReplayEntryPendingCoverageStartBoundaryTests(unittest.TestCase):
    """RVL-R3 (C) / RVL-R4: where a resting entry LIMIT and its protection coverage start.

    Before RVL-R4 nothing ordered coverage before LIMIT creation: coverage came only
    from resync() polling, and pre-LIMIT RETEST_DETECTED stayed ENTRY_PENDING-subscribed
    purely as a timing margin. Since RVL-R4 the production order is:

      robot-breakout-monitor thread (RETEST_DETECTED, no limit_order_id)
        1. arm_entry_coverage(symbol): hub subscribe + listeners attached, no owner call
           (fail closed: unbound arm, arm failure or owner thread -> no LIMIT this tick)
        2. owner task      _robot_create_limit -> durable 'open' LIMIT          [txn #1]
        3. monitor thread  _persist_execution  -> limit_order_id                [txn #2]
      robot-protection-coverage resync(): wanted = durable roles | arms; an arm ends in
        the same pass that first sees its durable ENTRY_PENDING role (gap-free hand-over).

    W1 (between txn #1 and #2) remains: its events are admitted but cannot fill the
    not-yet-linked LIMIT; the orphan-on-crash case is separate debt.
    """

    def test_production_monitor_arms_coverage_before_creating_the_resting_limit(self):
        events: list[tuple[str, str, bool]] = []
        probes: dict[str, object] = {}
        sequence = iter(range(1, 100))

        def book_event(limit_price: Decimal) -> RuntimeReplayEvent:
            # Ask exactly at the resting BUY price fills it; the bid one tick lower
            # stays far above the future trade's STOP.
            number = next(sequence)
            now_ms = int(time.time() * 1000)
            return RuntimeReplayEvent(
                event_id=f"{TOPOLOGY_SYMBOL}:{number}:{number}", symbol=TOPOLOGY_SYMBOL,
                coverage_role="ENTRY_PENDING", bid=limit_price - Decimal("0.1"), ask=limit_price,
                bid_size=Decimal("1000"), ask_size=Decimal("1000"), received_at_ms=now_ms,
                source_generation=0, source_sequence=number, source_update_id=number,
                source_event_at_ms=now_ms,
            )

        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "paper.sqlite3"
            _publish_live_snapshot(database_path)
            book = _MutableBookProvider()
            book.set(TOPOLOGY_SYMBOL, bid=Decimal("1000000"), ask=Decimal("1000001"))  # far: no poll fill
            runtime = _build_topology_runtime(
                database_path, book_provider=book,
                candle_provider=_FixedCandleProvider(
                    TOPOLOGY_SYMBOL, _candle_at(150, high=99, low=97, close=98),
                ),
                live_adapter_factory=_PoisonLiveAdapterFactory(),
            )
            hub = _ReplayHub()
            manager = RobotProtectionCoverageManager(
                hub, runtime, resync_interval_s=3600.0, recovery_session=_OfflineRecoverySession(),
            )

            def listening() -> bool:
                context = hub.contexts.get(TOPOLOGY_SYMBOL)
                return context is not None and "robot-protection" in context._update_listeners

            def arm(symbol: str) -> bool:
                armed = manager.arm_entry_coverage(symbol)
                events.append(("arm", threading.current_thread().name, armed and listening()))
                return armed

            original_create = PaperRuntime._robot_create_limit
            original_save = SQLiteStore.save_robot_candidate_state

            def create_limit(owner, request):
                listener_active = listening()
                result = original_create(owner, request)
                events.append(("limit_created", threading.current_thread().name, listener_active))
                return result

            def save_state(store, *args, **kwargs):
                order_id = ((kwargs.get("robot_state") or {}).get("execution") or {}).get("limit_order_id")
                if (
                    order_id and "window_roles" not in probes
                    and threading.current_thread().name == "robot-breakout-monitor"
                ):
                    events.append(("link_begins", threading.current_thread().name, listening()))
                    probes["window_roles"] = runtime.call(
                        lambda owner: owner.robot_protection_coverage_roles(),
                    )
                    probes["window_health"] = manager.health()
                    price = runtime.call(
                        lambda owner: owner.store.get_paper_limit(order_id, TOPOLOGY_ACCOUNT_ID).price,
                    )
                    hub.contexts[TOPOLOGY_SYMBOL].publish(book_event(price))
                    probes["window_last_symbol"] = runtime.protection_ingress_metrics()["last_symbol"]
                return original_save(store, *args, **kwargs)

            try:
                _seed_retest_detected_candidate(runtime, "candidate-1", TOPOLOGY_SYMBOL)
                manager.resync()
                probes["pre_limit_health"] = manager.health()
                runtime.call(lambda owner: owner.bind_robot_entry_coverage(
                    arm, manager.release_entry_coverage,
                ))
                with patch.object(PaperRuntime, "_robot_create_limit", create_limit), patch.object(
                    SQLiteStore, "save_robot_candidate_state", save_state,
                ):
                    runtime.start_robot_monitor()

                    def linked():
                        current = runtime.call(lambda owner: owner.store.get_robot_candidate("candidate-1"))
                        execution = (current.robot_state or {}).get("execution") or {}
                        return execution.get("limit_order_id")

                    order_id = _wait_until(linked)
                    context = hub.contexts[TOPOLOGY_SYMBOL]
                    manager.resync()
                    probes["handoff_health"] = manager.health()
                    probes["handoff_same_listener"] = (
                        hub.contexts.get(TOPOLOGY_SYMBOL) is context and listening()
                    )
                    price = runtime.call(
                        lambda owner: owner.store.get_paper_limit(order_id, TOPOLOGY_ACCOUNT_ID).price,
                    )
                    hub.contexts[TOPOLOGY_SYMBOL].publish(book_event(price))
                    runtime.call(lambda owner: None)
                    probes["filled_after_link"] = runtime.call(
                        lambda owner: owner.store.get_paper_limit(
                            order_id, TOPOLOGY_ACCOUNT_ID,
                        ).filled_quantity,
                    )
            finally:
                manager.close()
                runtime.close()

        # Pre-LIMIT RETEST_DETECTED has no durable role and no subscription.
        self.assertEqual(probes["pre_limit_health"]["covered_symbols"], ())
        # Order and thread ownership: arm (listener live) -> LIMIT on owner -> link.
        self.assertEqual(events[:3], [
            ("arm", "robot-breakout-monitor", True),
            ("limit_created", "paper-runtime-owner", True),
            ("link_begins", "robot-breakout-monitor", True),
        ])
        # W1: no durable role yet, but the arm covers the symbol and a fill-capable
        # event is admitted to protection ingress.
        self.assertEqual(probes["window_roles"], {})
        window = probes["window_health"]
        self.assertEqual(window["covered_symbols"], (TOPOLOGY_SYMBOL,))
        self.assertEqual(window["armed_symbols"], (TOPOLOGY_SYMBOL,))
        self.assertEqual(window["coverage_roles"], {TOPOLOGY_SYMBOL: "ENTRY_PENDING"})
        self.assertEqual(probes["window_last_symbol"], TOPOLOGY_SYMBOL)
        # Hand-over: the durable role takes over in one resync pass, same listener.
        handoff = probes["handoff_health"]
        self.assertEqual(handoff["armed_symbols"], ())
        self.assertEqual(handoff["covered_symbols"], (TOPOLOGY_SYMBOL,))
        self.assertEqual(handoff["coverage_roles"], {TOPOLOGY_SYMBOL: "ENTRY_PENDING"})
        self.assertTrue(probes["handoff_same_listener"])
        # First fill-capable event after the link is observed and fills the LIMIT.
        self.assertGreater(probes["filled_after_link"], Decimal("0"))

    def test_arm_survives_resync_and_hands_over_to_the_durable_role_without_gap(self):
        symbol = "STARTUSDT"
        account = TradingAccountId("paper")
        with tempfile.TemporaryDirectory() as temp:
            owner = SerializedPaperRuntime(lambda: _make_runtime(Path(temp) / "paper_runtime.sqlite3"))
            hub = _ReplayHub()
            manager = RobotProtectionCoverageManager(
                hub, owner, resync_interval_s=3600.0, recovery_session=_OfflineRecoverySession(),
            )
            try:
                runtime = owner.call(lambda owned: owned, timeout=30.0)
                # Fail closed: unbound, and never from the owner thread even when bound.
                self.assertFalse(runtime._arm_robot_entry_coverage(symbol))
                owner.call(lambda owned: owned.bind_robot_entry_coverage(
                    manager.arm_entry_coverage, manager.release_entry_coverage,
                ), timeout=30.0)
                self.assertFalse(owner.call(
                    lambda owned: owned._arm_robot_entry_coverage(symbol), timeout=30.0,
                ))
                self.assertEqual(manager.health()["armed_symbols"], ())

                def retest_detected(runtime: PaperRuntime) -> None:
                    record, _ = runtime.store.create_robot_candidate(
                        candidate_id="c-start", trading_account_id=account, symbol=Symbol(symbol),
                        status="APPROVED", signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge"},
                        approved_at_ms=1_000, updated_at_ms=1_000,
                    )
                    runtime.store.save_robot_candidate_state(
                        "c-start", status="APPROVED",
                        robot_state={"phase": "RETEST_DETECTED", "execution": {}},
                        expected_revision=record.state_revision, updated_at_ms=1_001,
                    )

                def resting_limit_linked(runtime: PaperRuntime) -> None:
                    runtime.store.create_paper_limit(
                        client_action_id="seed-o-start", request_fingerprint="fp-o-start",
                        order_id=OrderId("o-start"), order_link_id="link-o-start",
                        trading_account_id=account, symbol=Symbol(symbol), side=OrderSide.BUY,
                        price=Decimal("1"), quantity=Decimal("1"), created_at_ms=1_002,
                    )
                    revision = runtime.store.get_robot_candidate("c-start").state_revision
                    runtime.store.save_robot_candidate_state(
                        "c-start", status="APPROVED",
                        robot_state={"phase": "RETEST_DETECTED",
                                     "execution": {"limit_order_id": "o-start"}},
                        expected_revision=revision, updated_at_ms=1_003,
                    )

                def roles() -> dict[str, str]:
                    return owner.call(lambda runtime: runtime.robot_protection_coverage_roles(), timeout=30.0)

                # Pre-LIMIT: no durable role, and resync() does not subscribe it.
                owner.call(retest_detected, timeout=30.0)
                self.assertEqual(roles(), {})
                manager.resync()
                self.assertEqual(manager.health()["covered_symbols"], ())

                # The arm subscribes synchronously and survives resync() without a role.
                self.assertTrue(runtime._arm_robot_entry_coverage(symbol))
                context = hub.contexts[symbol]
                self.assertIn("robot-protection", context._update_listeners)
                manager.resync()
                health = manager.health()
                self.assertEqual(health["armed_symbols"], (symbol,))
                self.assertEqual(health["covered_symbols"], (symbol,))
                self.assertEqual(health["coverage_roles"], {symbol: "ENTRY_PENDING"})

                # Durable role appears: one resync pass ends the arm, same listener stays.
                owner.call(resting_limit_linked, timeout=30.0)
                self.assertEqual(roles(), {symbol: "ENTRY_PENDING"})
                manager.resync()
                health = manager.health()
                self.assertEqual(health["armed_symbols"], ())
                self.assertEqual(health["covered_symbols"], (symbol,))
                self.assertIs(hub.contexts[symbol], context)
                self.assertIn("robot-protection", context._update_listeners)

                # A released arm (LIMIT proven not created) is dropped by the next pass.
                self.assertTrue(manager.arm_entry_coverage("OTHERUSDT"))
                manager.release_entry_coverage("OTHERUSDT")
                manager.resync()
                self.assertEqual(manager.health()["covered_symbols"], (symbol,))

                # The subscription lasts only as long as its durable role.
                def invalidate(runtime: PaperRuntime) -> None:
                    revision = runtime.store.get_robot_candidate("c-start").state_revision
                    runtime.store.save_robot_candidate_state(
                        "c-start", status="INVALIDATED", robot_state={"phase": "INVALIDATED"},
                        expected_revision=revision, updated_at_ms=1_004,
                    )

                owner.call(invalidate, timeout=30.0)
                manager.resync()
                self.assertEqual(manager.health()["covered_symbols"], ())
                self.assertEqual(hub.contexts, {})
            finally:
                manager.close()
                owner.close()


BOX_ARM_LEAK_SYMBOLS = ("AKEUSDT", "ARKMUSDT", "BATUSDT", "BLASTUSDT", "BOMEUSDT", "BRETTUSDT")

# A missing projection is admissible only for a provably never-traded symbol
# (P0 BOX-PRISTINE-FLAT-1), so the failing fixture adds an orphan journal row.
BOX_OWNERSHIP_ERROR = (
    "Box ownership requires reconciled FLAT position and journal: "
    "missing projection is ambiguous with executions"
)


def seed_failing_box_candidates(database_path: Path, symbols: tuple[str, ...]) -> None:
    """Box candidates whose ownership must fail closed: lost projection, not pristine.

    Each symbol gets one immutable execution and no position-projection row. An
    execution creates no protection coverage role, so it cannot mask an arm leak.
    """
    from terminal.domain.models import (
        Category, Execution, ExecutionDedupKey, ExecutionId, Price, Quantity,
    )

    account = TradingAccountId("paper")
    store = SQLiteStore.open(database_path)
    try:
        for symbol in symbols:
            with store._transaction():
                store._insert_execution(Execution(
                    ExecutionDedupKey(account, Category.LINEAR, ExecutionId(f"orphan-{symbol}")),
                    OrderId(f"orphan-order-{symbol}"), Symbol(symbol), OrderSide.BUY,
                    Price(Decimal("94")), Quantity(Decimal("1")), Decimal("0"), 2_000,
                ))
    finally:
        store.close()
    seed_unowned_box_candidates(database_path, symbols)


class RuntimeReplayBoxArmLeakTests(unittest.TestCase):
    """RVL-R6 RED: a failed Box pre-creation attempt must not keep its temporary arm.

    Incident (2026-09-28 owner PAPER): six APPROVED / BOX_ENTRY_READY Box candidates with
    no position-projection row kept failing ``begin_box_attempt_ownership`` ("Box
    ownership requires reconciled FLAT position and journal", up to 48 attempts) while
    staying subscribed as ENTRY_PENDING arms, restoring the pre-LIMIT ingress load that
    RVL-R4 removed until protection ingress overflowed.

    A never-traded symbol is now a valid pristine FLAT base, so the fixture keeps the
    ownership failure real with an orphan execution and no projection. The invariant is
    unchanged: any failed pre-creation attempt must release its temporary arm.

    Production ordering in RobotBreakoutMonitor._advance_box_entry_ready():
    arm_entry_coverage -> begin_box_attempt_ownership raises -> tick() catches it ->
    no LIMIT/grid exists, the arm is never released, and resync() covers
    durable roles UNION arms. Product code is not changed here; these tests are RED.
    """

    CAPACITY = 64

    def test_failed_box_pre_creation_attempt_releases_its_temporary_coverage_arm(self):
        symbol = "AKEUSDT"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper_runtime.sqlite3"
            owner = SerializedPaperRuntime(lambda: _make_runtime(path))
            hub = _ReplayHub()
            manager = RobotProtectionCoverageManager(
                hub, owner, resync_interval_s=3600.0, recovery_session=_OfflineRecoverySession(),
            )
            try:
                seed_failing_box_candidates(path, (symbol,))
                self.assertEqual(manager.health()["armed_symbols"], ())

                advanced = tick_box_monitor(path, manager)
                facts = box_candidate_facts(path, (symbol,))[symbol]
                after_tick = manager.health()
                manager.resync()  # the production watchdog pass
                after_resync = manager.health()
                contexts = tuple(hub.contexts)
            finally:
                manager.close()
                owner.close()

        # Replay invariants, valid before and after a fix: the tick hit the production
        # ownership failure before any LIMIT/grid could exist.
        self.assertEqual(advanced, ())
        self.assertEqual(facts["phase"], "BOX_ENTRY_READY")
        self.assertEqual(facts["error"], BOX_OWNERSHIP_ERROR)
        self.assertEqual(facts["attempts"], 1)
        self.assertIsNone(facts["grid_ids"])
        self.assertEqual(facts["active_limits"], 0)

        evidence = (
            f"no LIMIT/grid (active_limits={facts['active_limits']}, grid_ids={facts['grid_ids']}); "
            f"after tick: armed={after_tick['armed_symbols']} covered={after_tick['covered_symbols']}; "
            f"after resync: armed={after_resync['armed_symbols']} covered={after_resync['covered_symbols']} "
            f"roles={dict(after_resync['coverage_roles'])} hub_contexts={contexts}"
        )
        # Target contract (RED on current code): once the attempt is proven to have
        # created no resting LIMIT/grid, the symbol has no independent durable protection
        # role, so it must be neither armed nor covered -- immediately and after resync.
        violations = []
        for label, health in (("after tick", after_tick), ("after resync", after_resync)):
            if health["armed_symbols"]:
                violations.append(f"{label}: temporary arm leaked {health['armed_symbols']}")
            if health["covered_symbols"]:
                violations.append(f"{label}: symbol still covered {health['covered_symbols']}")
        if contexts:
            violations.append(f"hub still subscribed {contexts}")
        self.assertEqual(violations, [], evidence)

    def test_leaked_box_arms_put_pre_limit_traffic_into_ingress_and_break_real_coverage(self):
        # Incident class: six failed Box arms + one legitimate linked ENTRY_PENDING
        # symbol (ARUSDT), continuous round-robin traffic across a bounded owner stall.
        # ARUSDT sits at cycle index 1 of 7, so stream event 65 (index 64), the first one
        # past capacity while the owner is stalled, is ARUSDT's own event.
        legit = "ARUSDT"
        cycle = ("BATUSDT", legit, "BLASTUSDT", "BOMEUSDT", "BRETTUSDT", "AKEUSDT", "ARKMUSDT")
        events = tuple(
            RuntimeReplayEvent(
                event_id=f"{cycle[i % 7]}:{100 + i}:{5000 + i}", symbol=cycle[i % 7],
                coverage_role="ENTRY_PENDING", bid=Decimal("0.5000"), ask=Decimal("0.5001"),
                bid_size=Decimal("100"), ask_size=Decimal("100"),
                received_at_ms=1_790_524_000_000 + i, source_generation=0,
                source_sequence=100 + i, source_update_id=5000 + i,
                source_event_at_ms=1_790_524_000_000 + i,
            )
            for i in range(84)
        )
        fixture = RuntimeReplayFixture(name="leaked_box_arms_round_robin_generated", events=events)
        ids = tuple(event.event_id for event in events)
        self.assertEqual(events[self.CAPACITY].symbol, legit)

        def setup(owner, manager, database_path):
            seed_failing_box_candidates(database_path, BOX_ARM_LEAK_SYMBOLS)
            advanced = tick_box_monitor(database_path, manager)
            box = box_candidate_facts(database_path, BOX_ARM_LEAK_SYMBOLS)
            # The one legitimate durable ENTRY_PENDING: a linked, open, unfilled LIMIT;
            # also leaves the Robot runtime at RECONCILIATION_REQUIRED for the stall.
            owner.call(
                lambda runtime: _seed_pre_limit_candidates(
                    runtime, (legit,), fixture.name,
                    recovery_status="RECONCILIATION_REQUIRED",
                    reason="maintenance reconciliation requested", resting_limit=True,
                ),
                timeout=30.0,
            )
            return {"advanced": advanced, "box": box}

        # One reconcile lookup (the only non-Box candidate), held for capacity + 1 events.
        result = run_manager_stall_replay(
            fixture, stall_events_per_lookup=self.CAPACITY + 1,
            protection_ingress_capacity=self.CAPACITY, setup=setup,
        )

        # Replay invariants, valid before and after a fix.
        facts = result.setup_facts
        self.assertEqual(facts["advanced"], ())
        self.assertEqual(set(facts["box"]), set(BOX_ARM_LEAK_SYMBOLS))
        for symbol, box in facts["box"].items():
            self.assertEqual(
                (box["phase"], box["error"], box["grid_ids"], box["active_limits"]),
                ("BOX_ENTRY_READY", BOX_OWNERSHIP_ERROR, None, 0), symbol,
            )
        self.assertEqual(result.stall_event_ids, (ids[:self.CAPACITY + 1],))
        self.assertEqual(result.lookup_threads, ("paper-runtime-owner",))
        self.assertEqual(set(result.unsubscribed_event_ids) | set(result.delivered_event_ids), set(ids))
        self.assertEqual(result.processed_event_ids, result.admitted_event_ids)
        self.assertEqual(result.event_errors, ())
        self.assertEqual(result.health_after_producer["ingress"]["capacity"], self.CAPACITY)
        self.assertEqual(result.final_health["ingress"]["current_pending"], 0)

        before = result.health_before_stream
        after = result.health_after_producer
        box_ids = {event_id for event_id in ids if event_id.split(":", 1)[0] in BOX_ARM_LEAK_SYMBOLS}
        box_in_ingress = sorted(box_ids & set(result.admitted_event_ids + result.overflow_event_ids))
        evidence = (
            f"armed={before['armed_symbols']} covered={before['covered_symbols']} "
            f"delivered={len(result.delivered_event_ids)}/{len(ids)} "
            f"box_events_in_ingress={len(box_in_ingress)} admitted={len(result.admitted_event_ids)} "
            f"pending_at_stall_release={result.pending_at_stall_release}/{self.CAPACITY} "
            f"first_overflow={result.overflow_event_ids[:1]} unhealthy={dict(after['unhealthy_symbols'])} "
            f"fence_overflows={result.fence_overflows} reconcile={result.reconcile_outcome}"
        )
        # Target contract (RED on current code): the failed Box candidates contribute zero
        # protection-ingress events, only the legitimate ARUSDT stays subscribed, nothing
        # overflows, and no symbol is unhealthy. Capacity stays 64 and no event is dropped
        # to get there: those events are simply not protection-critical.
        violations = []
        if before["armed_symbols"]:
            violations.append(f"temporary arms leaked {before['armed_symbols']}")
        if before["covered_symbols"] != (legit,):
            violations.append(f"covered {before['covered_symbols']} != {(legit,)}")
        if box_in_ingress:
            violations.append(f"{len(box_in_ingress)} pre-LIMIT Box events entered protection ingress")
        if result.overflow_event_ids:
            violations.append(f"ingress overflow starting at {result.overflow_event_ids[0]}")
        if after["unhealthy_symbols"]:
            violations.append(f"unhealthy symbols {dict(after['unhealthy_symbols'])}")
        self.assertEqual(violations, [], evidence)


if __name__ == "__main__":
    unittest.main()
