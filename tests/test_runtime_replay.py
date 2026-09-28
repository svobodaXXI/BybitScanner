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
    run_coverage_manager_replay,
    run_manager_stall_replay,
    run_owner_stall_replay,
    run_runtime_replay,
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
    """RVL-R2 RED: pre-LIMIT candidates under a bounded reconcile stall, via the manager.

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
        # Target contract (RED on current code): events of symbols that have no
        # fill-capable resting LIMIT are not protection-critical, so none of them may
        # enter protection ingress, overflow it, or turn any symbol unhealthy. This is
        # NOT "all 80 events processed": they should not belong to protection ingress.
        self.assertEqual(result.admitted_event_ids + result.overflow_event_ids, (), evidence)
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

                # Any fill (partial, full, or a filled-then-cancelled remainder) stays
                # ENTRY_PENDING until finalization; a cancelled unfilled LIMIT drops out.
                self.assertEqual(runtime.robot_protection_coverage_roles(), {
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
    """RVL-R3 (C): where a resting entry LIMIT and its protection coverage start.

    Freezes the production call order that any R4 change of the ENTRY_PENDING start
    boundary has to respect:

      robot-breakout-monitor tick (DEFAULT_TICK_INTERVAL_S = 60 s), no limit_order_id yet
        1. owner task    _robot_create_limit -> durable 'open' paper_limit_orders row
        2. monitor thread _persist_execution -> save_robot_candidate_state (limit_order_id)
      robot-protection-coverage thread (resync_interval_s = 5 s)
        3. resync() -> owner call(role discovery) -> hub.subscribe / add_update_listener
      hub -> _on_update -> enqueue -> owner process_robot_market_event, which fills only
         LIMITs named by a persisted limit_order_id.

    Nothing orders 3 before 1. Today the symbol is normally covered before the LIMIT
    exists only because the pre-LIMIT clause (RETEST_DETECTED without limit_order_id ->
    ENTRY_PENDING) is discovered a monitor tick (60 s) ahead of LIMIT creation.
    Simply removing that clause is therefore unsafe: the R2 fix (pre-LIMIT traffic must
    leave protection ingress) needs a synchronous coverage-arm barrier first:

      monitor thread: arm coverage for the symbol; WAIT until the hub listener is active
                      -> create the durable resting LIMIT -> persist limit_order_id
                      -> the durable ENTRY_PENDING role takes over from the arm.

    Constraints proven below: coverage is never established by lifecycle commits, only
    by resync(); resync() drops any subscription that has no durable role behind it, so
    an arm must survive resync until the hand-over; and the barrier may only be called
    from a non-owner thread (a nested SerializedPaperRuntime.call() from the owner
    thread deadlocks, see _DirectRobotActionExecutor). W1 (create -> link) is not shown
    to lose a first fill: the LIMIT stays open and unlinked-window events do not fill it.
    """

    def test_production_topology_creates_limit_on_owner_then_links_it_from_monitor_thread(self):
        events: list[tuple[str, str, str]] = []
        probes: dict[str, dict[str, object]] = {}
        sequence = iter(range(1, 100))

        def entry_only_book(event_id: str, limit_price: Decimal):
            # Ask exactly at the resting BUY price fills it; the bid one tick lower
            # stays far above the not-yet-existing trade's STOP.
            number = next(sequence)
            now_ms = int(time.time() * 1000)
            return RuntimeReplayEvent(
                event_id=event_id, symbol=TOPOLOGY_SYMBOL, coverage_role="ENTRY_PENDING",
                bid=limit_price - Decimal("0.1"), ask=limit_price, bid_size=Decimal("1000"),
                ask_size=Decimal("1000"), received_at_ms=now_ms,
                source_generation=0, source_sequence=number, source_update_id=number,
                source_event_at_ms=now_ms,
            ).book()

        def observe(owner: PaperRuntime, order_id: str, event_id: str) -> dict[str, object]:
            # Runs on the owner thread: durable state, coverage role, then one
            # fill-capable book event through the production protection path.
            before = owner.store.get_paper_limit(order_id, TOPOLOGY_ACCOUNT_ID)
            candidate = owner.store.get_robot_candidate("candidate-1")
            linked = ((candidate.robot_state or {}).get("execution") or {}).get("limit_order_id")
            roles = owner.robot_protection_coverage_roles()
            owner.process_robot_market_event(
                TOPOLOGY_SYMBOL, entry_only_book(event_id, before.price), event_id=event_id,
                received_at_ms=int(time.time() * 1000),
            )
            after = owner.store.get_paper_limit(order_id, TOPOLOGY_ACCOUNT_ID)
            return {
                "status_before": before.status, "filled_before": before.filled_quantity,
                "linked_order_id": linked, "roles": roles,
                "filled_after": after.filled_quantity,
            }

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
            original_create = PaperRuntime._robot_create_limit
            original_save = SQLiteStore.save_robot_candidate_state

            def create_limit(owner, request):
                result = original_create(owner, request)
                events.append(("limit_created", threading.current_thread().name, result.order_id))
                return result

            def save_state(store, *args, **kwargs):
                order_id = ((kwargs.get("robot_state") or {}).get("execution") or {}).get("limit_order_id")
                if (
                    order_id and "before_link" not in probes
                    and threading.current_thread().name == "robot-breakout-monitor"
                ):
                    events.append(("link_begins", threading.current_thread().name, order_id))
                    probes["before_link"] = runtime.call(
                        lambda owner: observe(owner, order_id, f"{TOPOLOGY_SYMBOL}:evt-before-link"),
                    )
                return original_save(store, *args, **kwargs)

            try:
                _seed_retest_detected_candidate(runtime, "candidate-1", TOPOLOGY_SYMBOL)
                with patch.object(PaperRuntime, "_robot_create_limit", create_limit), patch.object(
                    SQLiteStore, "save_robot_candidate_state", save_state,
                ):
                    runtime.start_robot_monitor()

                    def linked():
                        current = runtime.call(lambda owner: owner.store.get_robot_candidate("candidate-1"))
                        execution = (current.robot_state or {}).get("execution") or {}
                        return execution.get("limit_order_id")

                    order_id = _wait_until(linked)
                    probes["after_link"] = runtime.call(
                        lambda owner: observe(owner, order_id, f"{TOPOLOGY_SYMBOL}:evt-after-link"),
                    )
            finally:
                runtime.close()

        # Call order and thread ownership: two separate commits on two threads.
        self.assertEqual(
            [(label, thread) for label, thread, _ in events],
            [("limit_created", "paper-runtime-owner"), ("link_begins", "robot-breakout-monitor")],
        )
        self.assertEqual({detail for _, _, detail in events}, {order_id})

        # Window between the commits: a durable resting LIMIT that a fill-capable
        # protection-grade event cannot reach, although the symbol reads as covered
        # (only through the pre-LIMIT clause: the LIMIT is not linked yet).
        window = probes["before_link"]
        self.assertEqual((window["status_before"], window["filled_before"]), ("open", Decimal("0")))
        self.assertIsNone(window["linked_order_id"])
        self.assertEqual(window["roles"], {TOPOLOGY_SYMBOL: "ENTRY_PENDING"})
        self.assertEqual(window["filled_after"], Decimal("0"))

        # After the link commit the same kind of event does fill it.
        linked_probe = probes["after_link"]
        self.assertEqual(linked_probe["linked_order_id"], order_id)
        self.assertGreater(linked_probe["filled_after"], Decimal("0"))

    def test_coverage_is_only_established_by_resync_never_by_lifecycle_commits(self):
        symbol = "STARTUSDT"
        account = TradingAccountId("paper")
        with tempfile.TemporaryDirectory() as temp:
            owner = SerializedPaperRuntime(lambda: _make_runtime(Path(temp) / "paper_runtime.sqlite3"))
            hub = _ReplayHub()
            manager = RobotProtectionCoverageManager(
                hub, owner, resync_interval_s=3600.0, recovery_session=_OfflineRecoverySession(),
            )
            try:
                manager.resync()
                self.assertEqual(manager.health()["covered_symbols"], ())

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

                for step in (retest_detected, resting_limit_linked):
                    owner.call(step, timeout=30.0)
                    # Durable ENTRY_PENDING role exists at both steps ...
                    self.assertEqual(
                        owner.call(lambda runtime: runtime.robot_protection_coverage_roles(), timeout=30.0),
                        {symbol: "ENTRY_PENDING"},
                    )
                    # ... but no subscription: nothing is delivered until the next poll.
                    self.assertEqual(manager.health()["covered_symbols"], ())
                    self.assertEqual(hub.contexts, {})

                manager.resync()
                self.assertEqual(manager.health()["covered_symbols"], (symbol,))
                self.assertEqual(manager.health()["coverage_roles"], {symbol: "ENTRY_PENDING"})
                self.assertEqual(tuple(hub.contexts), (symbol,))

                # A subscription is only ever as durable as its role: once the durable
                # state stops wanting the symbol, the next resync() drops it. An arm
                # that precedes the durable role would be dropped the same way.
                def invalidate(runtime: PaperRuntime) -> None:
                    revision = runtime.store.get_robot_candidate("c-start").state_revision
                    runtime.store.save_robot_candidate_state(
                        "c-start", status="INVALIDATED", robot_state={"phase": "INVALIDATED"},
                        expected_revision=revision, updated_at_ms=1_004,
                    )

                owner.call(invalidate, timeout=30.0)
                self.assertEqual(manager.health()["covered_symbols"], (symbol,))
                manager.resync()
                self.assertEqual(manager.health()["covered_symbols"], ())
                self.assertEqual(hub.contexts, {})
            finally:
                manager.close()
                owner.close()


if __name__ == "__main__":
    unittest.main()
