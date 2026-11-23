"""Durable Robot v0.1 breakout/retest lifecycle monitor over APPROVED candidates.

Mode-agnostic coordinator, structurally mirroring
``terminal.application.robot_recovery.RobotRecoveryCoordinator``: it accepts a
``trading_account_id`` and dependency-injected functions rather than a
concrete PaperRuntime, so a future live implementation can reuse it with
live-bound dependencies instead of a duplicated cycle. It never refits
geometry and never invents entry/pattern/protection strategy: it only calls
the existing public functions of robot_state_machine.py, robot_entry_limit.py,
robot_protection.py,
in the order CR-ROBOT-BREAKOUT-MONITOR-001 approved, driving each APPROVED
candidate all the way to ``create_robot_trade``.

POST-CLOSURE FIX (see DOCUMENTS/ROBOT_RUN_INDEX.md): SQLiteStore binds to its
opening thread and rejects every call from any other thread. This coordinator
therefore never accepts a pre-opened SQLiteStore -- it takes a store_factory
and opens its own connection lazily, from whichever thread first calls into
it, cached per-thread. The real background thread opens and owns its own
connection; a caller driving .tick() synchronously (e.g. tests) gets its own
separate connection on the calling thread.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
import threading
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Callable, Mapping, Protocol

import mirror_retest_robot as mirror
import robot_entry_limit
from robot_entry_limit import IMPULSE_ENTRY_LIMIT_MAX_AGE_MS
from robot_entry_flow_evidence import (
    CandidateBoundFlowEvidence, existing_pattern_entry_scope,
    match_existing_pattern_flow,
)
import robot_l_shape
import robot_protection
import robot_state_machine
from robot_failure_diagnostics import record_robot_incident
from robot_market_confirmation import risk_reward_ratio
from scanner_geometry_cursor import (
    ScannerGeometryCursorError,
    latest_scanner_closed_candle,
    load_scanner_catchup_closed_candles,
    project_latest_geometry_index,
)
from terminal.api.models import (
    ClientActionId, CommandResultStatus, MarketCommandRequest, PaperLimitCancelRequest,
    PaperStopMutationRequest,
)
from terminal.application.command_identity import (
    CommandIdentityCandidate, robot_emergency_close_identity,
)
from terminal.application.ikigai_box_first_grid import build_box_first_grid_specs
from terminal.application.ikigai_box_catchup import (
    build_box_emergency_close_market_plan,
    build_box_exit_specs,
    build_box_market_ownership_specs,
    build_box_market_plans,
    classify_box_catchup_slots,
    durable_box_market_intent,
    ready_box_exit_slots,
    restore_box_market_plan,
)
from terminal.application.robot_recovery import RobotRecoveryCoordinator
from terminal.application.robot_admission import active_robot_owner_candidate_ids
from terminal.application.robot_admission_catchup import (
    LATE_ADMISSION_MARKET,
    replay_admission_catchup,
)
from terminal.application.robot_late_admission import (
    DECISION_APEX_REACHED as LATE_DECISION_APEX_REACHED,
    DECISION_MARKET_ENTRY as LATE_DECISION_MARKET_ENTRY,
    evaluate_late_admission,
)
from terminal.application.robot_late_admission_market import (
    build_late_admission_market_plan,
    durable_late_admission_market_intent,
    restore_late_admission_market_plan,
)
from terminal.domain.models import (
    Category, CommandId, ExecutionDedupKey, OrderId, OrderSide,
    PositionKey, PositionSide, Quantity,
    Symbol, TradingAccountId,
)
from terminal.market_data.models import NormalizedOrderBook
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    RobotCandidateRecord,
    SQLiteStore,
)

DEFAULT_TICK_INTERVAL_S = 60.0
DEFAULT_LATE_MARKET_MAX_BOOK_AGE_MS = 1000
IMPULSE_EARLY_LIMIT_ENTRY_MODE = "IMPULSE_EARLY_LIMIT"
PAPER_CANDIDATE_ERROR_QUARANTINE_THRESHOLD = 3

INACTIVE_LIMIT_STATUSES = {"filled", "cancelled"}
PHASE_INVALIDATED_UNSUPPORTED_PATTERN = "INVALIDATED_UNSUPPORTED_PATTERN"
ENTRY_RR_SKIP_POOR_RR = "SKIPPED_POOR_RR"  # same name as the late-admission decision
ENTRY_RR_SKIP_UNAVAILABLE = "SKIPPED_RR_UNAVAILABLE"


class ActionExecutor(Protocol):
    """Unified execution port. PaperRuntime already satisfies this today; a
    future live_runtime.py can satisfy it with live-bound implementations
    without duplicating this coordinator's cycle."""

    def create_limit(self, request): ...
    def amend_limit(self, request): ...
    def cancel_limit(self, request): ...
    def create_stop(self, request): ...
    def amend_stop(self, request): ...
    def create_take(self, request): ...
    def amend_take(self, request): ...
    def full_close(self, request): ...


class RobotBreakoutMonitorError(RuntimeError):
    """Raised when the breakout/retest monitor cannot safely advance a candidate."""


@dataclass(frozen=True, slots=True)
class EmergencyClosePath:
    """Owner-thread close callbacks, used ONLY when a Box fill cannot be protected.

    The regular book/preflight/submit callbacks hop through the serialized owner
    queue, which would deadlock when the monitor itself runs on the owner thread.
    These run in place, never fetch from the network, and must not raise.
    """

    get_market_book: Callable[[str], NormalizedOrderBook | None]
    market_preflight: Callable[[MarketCommandRequest, CommandIdentityCandidate], object]
    submit_market: Callable[[MarketCommandRequest, CommandIdentityCandidate], object]


@dataclass(frozen=True, slots=True)
class _EntryEvidence:
    order_ids: tuple[OrderId, ...]
    quantity: Decimal
    average_entry: Decimal
    position_version: int
    first_execution_at_ms: int


def _cancel_partial_remainder_action_id(candidate_id: str) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-partial-remainder".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-partial-{digest}")


def _cancel_blocked_entry_action_id(candidate_id: str) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-blocked-entry".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-blocked-{digest}")


def _cancel_l_shape_invalid_action_id(candidate_id: str) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-l-shape-invalid".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-lshape-invalid-{digest}")


def _cancel_apex_entry_action_id(candidate_id: str) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-entry-at-apex".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-apex-{digest}")


def _frozen_robot_apex_index(signal_snapshot: Mapping[str, object]) -> Decimal:
    geometry = signal_snapshot.get("robot_geometry")
    if geometry is None:
        geometry = signal_snapshot.get("geometry")
    apex = geometry.get("apex") if isinstance(geometry, Mapping) else None
    raw = apex.get("index") if isinstance(apex, Mapping) else None
    try:
        value = Decimal(str(raw))
    except Exception as exc:
        raise RobotBreakoutMonitorError("frozen Robot apex is invalid") from exc
    if not value.is_finite() or value < 0:
        raise RobotBreakoutMonitorError("frozen Robot apex is invalid")
    return value


def robot_entry_order_ids(
    store,
    account_id: TradingAccountId,
    record: RobotCandidateRecord,
    execution: Mapping[str, object],
    *,
    entry_path: str,
) -> tuple[OrderId, ...]:
    """Durable order identities of one Robot candidate's own entry (LIMIT or late MARKET)."""
    if entry_path == "LIMIT":
        raw_order_ids = execution.get("limit_order_ids")
        if raw_order_ids is not None:
            if (
                not isinstance(raw_order_ids, (tuple, list))
                or not raw_order_ids
                or any(not isinstance(item, str) or not item.strip() for item in raw_order_ids)
            ):
                raise RobotBreakoutMonitorError("Robot LIMIT entry identities are invalid")
            normalized = tuple(OrderId(item.strip()) for item in raw_order_ids)
            if len({item.value for item in normalized}) != len(normalized):
                raise RobotBreakoutMonitorError("Robot LIMIT entry identities contain duplicates")
            return normalized

        raw_order_id = execution.get("limit_order_id")
        if not isinstance(raw_order_id, str) or not raw_order_id.strip():
            return ()
        return (OrderId(raw_order_id.strip()),)

    if entry_path != "MARKET":
        raise RobotBreakoutMonitorError(f"unsupported Robot entry path: {entry_path}")
    intent = execution.get("late_market_intent")
    if not isinstance(intent, Mapping):
        return ()
    raw_command_id = intent.get("command_id")
    if not isinstance(raw_command_id, str) or not raw_command_id.strip():
        raise RobotBreakoutMonitorError("late Market intent lacks command identity")
    command = store.get_command(CommandId(raw_command_id.strip()))
    if command is None or command.exchange_order_id is None:
        return ()
    if (
        command.trading_account_id != account_id
        or command.symbol != record.symbol
    ):
        raise RobotBreakoutMonitorError(
            "late Market command identity does not match Robot candidate scope"
        )
    return (command.exchange_order_id,)


class RobotBreakoutMonitor:
    """Advance durable APPROVED Robot candidates through breakout/retest on each closed 1m candle."""

    def __init__(
        self,
        store_factory: Callable[[], SQLiteStore],
        trading_account_id: TradingAccountId,
        *,
        get_closed_candle: Callable[[str], Mapping[str, object] | None],
        action_executor: ActionExecutor,
        tick_size_provider: Callable[[str], Decimal],
        clock_ms: Callable[[], int],
        tick_interval_s: float = DEFAULT_TICK_INTERVAL_S,
        match_resting_orders: Callable[[str], object] | None = None,
        get_admission_catchup_candles: Callable[
            [str, Mapping[str, object]], tuple[Mapping[str, object], ...]
        ] | None = None,
        get_market_book: Callable[[str], NormalizedOrderBook | None] | None = None,
        market_preflight: Callable[[MarketCommandRequest, CommandIdentityCandidate], object] | None = None,
        submit_market: Callable[[MarketCommandRequest, CommandIdentityCandidate], object] | None = None,
        late_market_max_book_age_ms: int = DEFAULT_LATE_MARKET_MAX_BOOK_AGE_MS,
        arm_entry_coverage: Callable[[str], bool] | None = None,
        release_entry_coverage: Callable[[str], None] | None = None,
        incident_dir=None,
        emergency_close_path: EmergencyClosePath | None = None,
        mirror_policy: "mirror.MirrorRobotPolicy | None" = None,
        wedge_be_auto_paper_enabled: bool = False,
        impulse_fade_paper_enabled: bool = False,
        impulse_early_paper_enabled: bool = False,
        impulse_l_shape_paper_enabled: bool = False,
        get_pattern_flow_evidence: Callable[
            [RobotCandidateRecord], CandidateBoundFlowEvidence | None
        ] | None = None,
    ) -> None:
        self._emergency_close_path = emergency_close_path
        # MIRROR RETEST overlay for Box attempts (OFF unless a policy is bound; see mirror_retest_robot).
        self._mirror_policy = mirror_policy
        if type(wedge_be_auto_paper_enabled) is not bool:
            raise ValueError("Wedge BE PAPER auto gate must be explicit bool")
        self._wedge_be_auto_paper_enabled = wedge_be_auto_paper_enabled
        if type(impulse_fade_paper_enabled) is not bool:
            raise ValueError("Impulse fade PAPER gate must be explicit bool")
        self._impulse_fade_paper_enabled = impulse_fade_paper_enabled
        if type(impulse_early_paper_enabled) is not bool:
            raise ValueError("Impulse early PAPER gate must be explicit bool")
        self._impulse_early_paper_enabled = impulse_early_paper_enabled
        # The first release is Wedge-only. Keep the L-shape implementation
        # separately gated, with no production activation wiring yet.
        if type(impulse_l_shape_paper_enabled) is not bool:
            raise ValueError("L-shape impulse PAPER gate must be explicit bool")
        self._impulse_l_shape_paper_enabled = impulse_l_shape_paper_enabled
        self._get_pattern_flow_evidence = get_pattern_flow_evidence
        # Resting entry LIMITs become fill-capable the moment they are durable, so
        # protection coverage for the symbol must already be listening. Without a
        # bound arm this monitor never creates a resting entry LIMIT (fail closed).
        self._arm_entry_coverage_callback = arm_entry_coverage
        self._release_entry_coverage_callback = release_entry_coverage
        self._incident_dir = incident_dir
        self._store_factory = store_factory
        self._local = threading.local()
        self._account_id = trading_account_id
        self._get_closed_candle = get_closed_candle
        if (
            get_admission_catchup_candles is None
            and get_closed_candle is latest_scanner_closed_candle
        ):
            get_admission_catchup_candles = load_scanner_catchup_closed_candles
        self._get_admission_catchup_candles = get_admission_catchup_candles
        self._action_executor = action_executor
        self._tick_size_provider = tick_size_provider
        self._clock_ms = clock_ms
        self._tick_interval_s = tick_interval_s
        self._match_resting_orders = match_resting_orders
        self._get_market_book = get_market_book
        self._market_preflight = market_preflight
        self._submit_market = submit_market
        self._late_market_max_book_age_ms = late_market_max_book_age_ms
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="robot-breakout-monitor", daemon=True,
        )
        self._started = False
        self._tick_lock = threading.Lock()

    def _store(self) -> SQLiteStore:
        store = getattr(self._local, "store", None)
        if store is None:
            store = self._store_factory()
            self._local.store = store
        return store

    def bind_pattern_flow_observer(
        self,
        observer: Callable[[RobotCandidateRecord], CandidateBoundFlowEvidence | None],
    ) -> None:
        """One in-process read-only overlay, bound before the Robot tick starts."""
        if self._started or self._get_pattern_flow_evidence is not None:
            raise RuntimeError("Robot pattern flow observer is already bound or running")
        if not callable(observer):
            raise TypeError("pattern flow observer must be callable")
        self._get_pattern_flow_evidence = observer

    def _pattern_flow_allows_entry(self, record: RobotCandidateRecord) -> bool:
        """Fail closed at an unowned entry boundary when PAPER flow is enabled.

        With the opt-in observer absent, retain the original Robot route.
        With it bound, a fresh, exact-owner, directionally supportive and
        independently source-complete receipt is mandatory for Wedge only
        in the first release. L-shape requires a separate explicit opt-in;
        MIRROR and Box retain their native entry behavior. Missing/foreign/stale
        evidence cannot silently bypass impulse timing and submit the old
        entry. This gate never touches an already-owned entry, fill, STOP,
        TAKE, cancel or recovery lifecycle.
        """
        pattern = record.signal_snapshot.get("pattern")
        if pattern not in ("Falling Wedge", "Rising Wedge") and not (
            pattern == "L-shape" and self._impulse_l_shape_paper_enabled
        ):
            return True  # only the optional overlay is absent; native gates remain
        observer = self._get_pattern_flow_evidence
        if observer is None:
            return True
        scope = existing_pattern_entry_scope(record)
        if scope is None:
            return False
        try:
            receipt = observer(record)
        except Exception:
            return False  # uncertainty is not a trading authorization
        return match_existing_pattern_flow(
            scope, receipt, now_ms=self._now_ms(),
        )

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._started and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        self._close_local_store()

    def _close_local_store(self) -> None:
        store = getattr(self._local, "store", None)
        if store is not None:
            store.close()
            self._local.store = None

    def _run(self) -> None:
        try:
            while not self._stop.wait(self._tick_interval_s):
                try:
                    self.tick()
                except Exception as error:
                    print(
                        "[ROBOT BREAKOUT MONITOR LOOP ERROR] "
                        f"error={error}"
                    )
        finally:
            self._close_local_store()

    @contextmanager
    def shutdown_idle_guard(self):
        """Exclude an in-flight pre-entry tick; called outside the PAPER owner thread."""
        if not self._tick_lock.acquire(blocking=False):
            raise RuntimeError("robot_entry_tick_busy")
        try:
            yield
        finally:
            self._tick_lock.release()

    def tick(self) -> tuple[str, ...]:
        """Advance every durable APPROVED candidate by at most one step."""
        with self._tick_lock:
            return self._tick()

    def _tick(self) -> tuple[str, ...]:
        advanced: list[str] = []
        for record in self._store().load_robot_candidates_by_status(
            self._account_id, ("APPROVED", "OPEN"),
        ):
            try:
                if record.status == "OPEN":
                    if (
                        record.robot_state is not None
                        and record.signal_snapshot.get("pattern") == "IKIGAI_BOX"
                        and record.robot_state.get("phase") == "BOX_ENTRY_READY"
                        and (
                            self._advance_mirror_box(record)
                            or self._sync_box_trade(
                                record, record.robot_state.get("execution") or {},
                            )
                        )
                    ):
                        advanced.append(record.candidate_id)
                    if (
                        self._wedge_be_auto_paper_enabled
                        and record.robot_state is not None
                        and record.signal_snapshot.get("pattern")
                        in ("Falling Wedge", "Rising Wedge")
                        and self._advance_open_wedge_be(record)
                    ):
                        advanced.append(record.candidate_id)
                    continue
                if self._advance_one(record):
                    advanced.append(record.candidate_id)
            except Exception as error:
                print(
                    "[ROBOT CANDIDATE ERROR] "
                    f"candidate_id={record.candidate_id} error={error}"
                )
                self._record_execution_error(record, error)
                continue
        return tuple(advanced)

    def _advance_open_wedge_be(self, record: RobotCandidateRecord) -> bool:
        """Run Wedge-only PAPER BE through the canonical owner; never locally mutate.

        First invocation requires a recent, fully CLOSED Scanner M1.
        If a prior partial was latched, recovery does not need a candle and
        never makes a fresh partial-entry decision from a later quote.
        The owner independently revalidates ALL trade/position/protection
        evidence and handles the only durable MARKET/STOP mutations.
        """
        step = getattr(self._action_executor, "wedge_be_step", None)
        if not callable(step):
            raise RobotBreakoutMonitorError("enabled BE has no serialized owner execution port")
        state = record.robot_state or {}
        execution = state.get("execution") or {}
        if not isinstance(execution, Mapping):
            raise RobotBreakoutMonitorError("Wedge BE execution state is malformed")
        candle = None
        fade_receipt = None
        if ("wedge_be_partial_intent" not in execution
                and self._impulse_fade_paper_enabled
                and self._get_pattern_flow_evidence is not None):
            # Only certified, same-candidate evidence may be evaluated by
            # the canonical owner. A disconnected observer is never authority.
            try:
                fade_receipt = self._get_pattern_flow_evidence(record)
            except Exception:
                fade_receipt = None
        if "wedge_be_partial_intent" not in execution:
            # Keep the legacy +2R candle available even with a candidate
            # fade source, so an unqualified fade never masks the old exit.
            try:
                source = self._get_closed_candle(record.symbol.value)
            except Exception:
                if fade_receipt is None:
                    raise
                source = None
            if isinstance(source, Mapping):
                timestamp = source.get("time_ms")
                if type(timestamp) is int and timestamp > 0 and timestamp % 60_000 == 0:
                    end_ms = timestamp + 60_000
                    age_ms = self._clock_ms() - end_ms
                    if 0 <= age_ms <= 90_000:
                        try:
                            high = Decimal(str(source["high"]))
                            low = Decimal(str(source["low"]))
                            if (high.is_finite() and low.is_finite()
                                    and low > 0 and high >= low):
                                candle = {"time_ms": timestamp, "high": high, "low": low}
                        except (KeyError, ValueError, TypeError, ArithmeticError):
                            pass
            if candle is None and fade_receipt is None:
                return False
        if fade_receipt is not None:
            result = step(
                record.candidate_id, record.symbol.value, candle,
                fade_receipt=fade_receipt,
            )
        else:
            result = step(record.candidate_id, record.symbol.value, candle)
        return getattr(result, "status", None) is CommandResultStatus.COMPLETED

    def process_authoritative_fill(self, symbol: str) -> tuple[str, ...]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must be non-empty")

        advanced: list[str] = []
        symbol_value = Symbol(normalized)
        for record in self._store().load_robot_candidates_for_symbol(
            self._account_id, symbol_value,
        ):
            if record.status == "OPEN":
                if record.robot_state is None:
                    continue
                execution = record.robot_state.get("execution") or {}
                try:
                    if record.signal_snapshot.get("pattern") == "IKIGAI_BOX":
                        if self._sync_box_trade(record, execution):
                            advanced.append(record.candidate_id)
                        # Exposure proven owned and protected in this epoch: the
                        # remaining ENTRY slots of its grid are confirmed too.
                        self._confirm_entry_admission(record)
                    elif self._refresh_open_trade_entry_attestation(record, execution):
                        advanced.append(record.candidate_id)
                except Exception as error:
                    print(
                        "[ROBOT CANDIDATE ERROR] "
                        f"candidate_id={record.candidate_id} error={error}"
                    )
                    self._escalate_reconciliation(
                        "ROBOT_ENTRY_ATTESTATION_REFRESH_FAILED "
                        f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                        f"reason={error}"
                    )
                continue
            if record.status != "APPROVED" or record.robot_state is None:
                continue
            phase = record.robot_state.get("phase")
            execution = record.robot_state.get("execution") or {}

            if phase == "BOX_ENTRY_READY":
                try:
                    # The authoritative-fill shortcut must use the same frozen
                    # source/ownership check as the normal Box entry path.
                    source = self._box_source(record, execution)
                    proof = self._store().prove_box_owned_position(source.candidate_id)
                    if proof.entry_quantity <= 0:
                        continue
                    if self._advance_box_entry_ready(record, match_resting_orders=False):
                        advanced.append(record.candidate_id)
                except Exception as error:
                    print(
                        "[ROBOT CANDIDATE ERROR] "
                        f"candidate_id={record.candidate_id} error={error}"
                    )
                    self._record_execution_error(record, error)
                continue

            if (phase != robot_state_machine.PHASE_RETEST_DETECTED
                    and not (
                        phase in (robot_state_machine.PHASE_WAITING_RETEST,
                                  robot_l_shape.PHASE_WAITING_RETEST)
                        and isinstance(execution, Mapping)
                        and execution.get("entry_mode") == IMPULSE_EARLY_LIMIT_ENTRY_MODE
                        and execution.get("limit_order_id")
                    )):
                continue
            order_id = execution.get("limit_order_id")
            if not order_id:
                continue
            order = self._store().get_paper_limit(order_id, self._account_id)
            if order is None or order.quantity <= 0 or order.filled_quantity <= 0:
                continue
            try:
                if self._advance_retest_detected(record, match_resting_orders=False):
                    advanced.append(record.candidate_id)
            except Exception as error:
                print(
                    "[ROBOT CANDIDATE ERROR] "
                    f"candidate_id={record.candidate_id} error={error}"
                )
                self._record_execution_error(record, error)
        return tuple(advanced)

    def _refresh_open_trade_entry_attestation(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
    ) -> bool:
        trade = self._store().get_open_robot_trade_for_symbol(
            self._account_id, record.symbol,
        )
        if trade is None or trade.candidate_id != record.candidate_id:
            raise RobotBreakoutMonitorError(
                "OPEN Robot candidate lacks its matching OPEN trade"
            )
        if trade.entry_path != "LIMIT":
            return False

        evidence = self._prove_entry_evidence(
            record, execution, entry_path="LIMIT",
        )
        if evidence is None:
            return False

        _updated, changed = self._store().refresh_open_robot_trade_entry_attestation(
            trade.trade_id,
            trading_account_id=self._account_id,
            candidate_id=record.candidate_id,
            symbol=record.symbol,
            average_entry=evidence.average_entry,
            entry_quantity=evidence.quantity,
            entry_position_version=evidence.position_version,
            updated_at_ms=self._now_ms(),
        )
        return changed

    def _record_execution_error(self, record: RobotCandidateRecord, error: Exception) -> None:
        """Count repeat faults durably; quarantine only a proven inert PAPER candidate.

        The error path may run after an execution callback has committed a
        simulated fill. Never infer that APPROVED means pre-execution.
        """
        if record.robot_state is None:
            return
        try:
            fresh = self._store().get_robot_candidate(record.candidate_id)
            if fresh is None or fresh.status != "APPROVED" or fresh.robot_state is None:
                return
            state = dict(fresh.robot_state)
            execution = dict(state.get("execution") or {})
            fingerprint = f"{type(error).__name__}:{error}"
            previous = execution.get("paper_candidate_error")
            repeated = (
                int(previous.get("consecutive", 0)) + 1
                if isinstance(previous, Mapping) and previous.get("fingerprint") == fingerprint
                else 1
            )
            execution["paper_candidate_error"] = {
                "fingerprint": fingerprint, "consecutive": repeated,
            }
            execution["last_execution_error"] = str(error)
            execution["last_attempt_at_ms"] = self._now_ms()
            execution["attempt_count"] = int(execution.get("attempt_count", 0) or 0) + 1
            state["execution"] = execution

            if (
                repeated >= PAPER_CANDIDATE_ERROR_QUARANTINE_THRESHOLD
                and self._account_id.value == "paper"
                and self._paper_candidate_is_inert(fresh)
            ):
                state["paper_quarantine"] = {
                    "reason": "REPEATED_CANDIDATE_ERROR",
                    "error_type": type(error).__name__,
                    "consecutive": repeated,
                    "at_ms": self._now_ms(),
                }
                status = "INVALIDATED"
            else:
                status = "APPROVED"
            self._store().save_robot_candidate_state(
                fresh.candidate_id,
                status=status,
                robot_state=state,
                expected_revision=fresh.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except Exception:
            # A failed proof or persistence write never justifies quarantine.
            # Existing account-wide protection/admission authority is unchanged.
            pass

    def _paper_candidate_is_inert(self, record: RobotCandidateRecord) -> bool:
        """Require no candidate execution intent AND no durable trading lineage."""
        execution = (record.robot_state or {}).get("execution") or {}
        if not isinstance(execution, Mapping):
            return False
        # Every other execution field may be an order, fill, or entry intent.
        if set(execution) - {
            "last_execution_error", "last_attempt_at_ms",
            "attempt_count", "paper_candidate_error",
        }:
            return False
        if self._store().get_robot_trade(f"robot-trade-{record.candidate_id}") is not None:
            return False
        return RobotRecoveryCoordinator(
            self._store(), self._account_id, clock_ms=self._clock_ms,
        )._candidate_is_inert(record)

    def _cancelled_legacy_double_is_inert(
        self, record: RobotCandidateRecord, order_id: str,
    ) -> bool:
        """A cancelled, zero-filled legacy LIMIT is not proof of zero exposure.

        Verify the immutable fill ledger and all canonical owner-side
        order/command/position/protection reads before retiring the candidate.
        Unavailable or contradictory evidence fails closed.
        """
        store = self._store()
        if store.get_robot_trade(f"robot-trade-{record.candidate_id}") is not None:
            return False
        if store.load_executions_for_order(self._account_id, OrderId(order_id)):
            return False
        return RobotRecoveryCoordinator(
            store, self._account_id, clock_ms=self._clock_ms,
        )._candidate_is_inert(record)

    def _prepare_wedge_early_impulse_research(self, record: RobotCandidateRecord) -> bool:
        """Persist an early-entry proposal, NEVER a pending execution intent.

        This is a PAPER-only research side channel on the original APPROVED
        Wedge; protected entry ownership still belongs entirely to the
        legacy RETEST path until a separate idempotent executor is proven.
        No create/amend/cancel, position, stop or take operation is possible.
        """
        if (self._account_id.value != "paper"
                or self._get_pattern_flow_evidence is None
                or self._get_market_book is None
                or record.robot_state is None
                or record.status != "APPROVED"
                or record.signal_snapshot.get("pattern")
                    not in ("Falling Wedge", "Rising Wedge")
                or record.robot_state.get("phase") != "WAITING_RETEST"
                or "impulse_entry_research" in record.robot_state):
            return False
        if not self._read_admission_gate()[0]:
            return False
        if (self._active_other_owner_candidate_ids(record)
                or self._pre_entry_block_reason(record) is not None):
            return False
        try:
            receipt = self._get_pattern_flow_evidence(record)
            if receipt is None:
                return False
            book = self._get_market_book(record.symbol.value)
            if book is None:
                return False
            quote = robot_entry_limit.build_post_breakout_wedge_impulse_limit_research(
                record, receipt, book,
                tick_size=self._tick_size_provider(record.symbol.value),
                now_ms=self._now_ms(),
                max_book_age_ms=self._late_market_max_book_age_ms,
            )
            frozen = robot_entry_limit.freeze_post_breakout_impulse_quote(
                quote, receipt,
            )
        except Exception:
            # Optional market-data observation cannot quarantine a normally
            # executable pattern when a source/transport adapter is unavailable.
            return False
        # A research write is CAS-scoped, with no order submission or
        # owner coverage arm; a conflict is NOT a successful persistence.
        updated = dict(record.robot_state)
        updated["impulse_entry_research"] = frozen
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="APPROVED",
                robot_state=updated,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except Exception:
            # The optional evidence path cannot affect the original entry
            # lifecycle. Missing research persistence is not market authority.
            return False
        return True

    def _advance_impulse_early_limit(
        self, record: RobotCandidateRecord,
    ) -> bool:
        """Canonical Wedge/L-shape PAPER LIMIT owner with durable first intent.

        The only entry mechanism is the existing action executor. An uncertain
        submission is NEVER replayed. Recovery correlates the original create
        action to an actual Robot-owned LIMIT before enabling fills; the same
        native finalize/protection path handles any partial fill.
        """
        pattern = record.signal_snapshot.get("pattern")
        wedge = pattern in ("Falling Wedge", "Rising Wedge")
        if (self._account_id.value != "paper" or record.status != "APPROVED"
                or record.robot_state is None
                or not (wedge or pattern == "L-shape")):
            return False
        state = record.robot_state
        execution = dict(state.get("execution") or {})
        intent = execution.get("impulse_entry_intent")
        if intent is not None:
            verify = (robot_entry_limit.verify_frozen_post_breakout_impulse_quote
                      if wedge else robot_entry_limit.verify_frozen_post_breakout_l_shape_quote)
            if (execution.get("entry_mode") != IMPULSE_EARLY_LIMIT_ENTRY_MODE
                    or not verify(record, intent)):
                self._escalate_reconciliation(
                    "ROBOT_IMPULSE_ENTRY_INTENT_INVALID "
                    f"candidate_id={record.candidate_id}"
                )
                return False
            order = self._store().get_robot_paper_limit_by_create_action(
                self._account_id, record.symbol, intent["client_action_id"],
            )
            if order is None:
                # A durable intent is not proof that create_limit was sent.
                # Never resubmit: UNKNOWN transport must be reconciled.
                return False
            if (order.symbol != record.symbol
                    or order.side.value != intent["entry_side"]
                    or order.price != Decimal(intent["quoted_price"])
                    or order.quantity <= 0
                    or order.filled_quantity < 0
                    or order.filled_quantity > order.quantity
                    or (execution.get("limit_order_id") is not None
                        and execution["limit_order_id"] != order.order_id.value)):
                self._escalate_reconciliation(
                    "ROBOT_IMPULSE_ORDER_OWNERSHIP_CONFLICT "
                    f"candidate_id={record.candidate_id}"
                )
                return False
            if "limit_order_id" not in execution:
                execution["limit_order_id"] = order.order_id.value
                if wedge:
                    execution["last_limit_index"] = state["geometry_cursor"]
                new_state = dict(state)
                new_state["execution"] = execution
                try:
                    self._store().save_robot_candidate_state(
                        record.candidate_id,
                        status="APPROVED",
                        robot_state=new_state,
                        expected_revision=record.state_revision,
                        updated_at_ms=self._now_ms(),
                    )
                except ConcurrentUpdate:
                    return False
                return True
            # The original LIMIT-owned fill/STOP/TAKE logic is authoritative.
            # No separate impulse fill path or secondary protection plan.
            return self._advance_retest_detected(record)

        early_phase = ("WAITING_RETEST" if wedge
                       else robot_l_shape.PHASE_WAITING_RETEST)
        if (not self._impulse_early_paper_enabled
                or (not wedge and not self._impulse_l_shape_paper_enabled)
                or state.get("phase") != early_phase
                or self._get_pattern_flow_evidence is None
                or self._get_market_book is None
                or execution.get("limit_order_id")
                or execution.get("late_market_intent")):
            return False
        if not self._read_admission_gate()[0]:
            return False
        if (self._active_other_owner_candidate_ids(record)
                or self._pre_entry_block_reason(record) is not None):
            return False
        try:
            receipt = self._get_pattern_flow_evidence(record)
            if receipt is None:
                return False
            book = self._get_market_book(record.symbol.value)
            if book is None:
                return False
            build_quote = (
                robot_entry_limit.build_post_breakout_wedge_impulse_limit_research
                if wedge else
                robot_entry_limit.build_post_breakout_l_shape_impulse_limit_research
            )
            quote = build_quote(
                record, receipt, book,
                tick_size=self._tick_size_provider(record.symbol.value),
                now_ms=self._now_ms(),
                max_book_age_ms=self._late_market_max_book_age_ms,
            )
            frozen = robot_entry_limit.freeze_post_breakout_impulse_quote(
                quote, receipt,
            )
        except Exception:
            # No exception from optional market evidence grants an entry.
            return False
        if not self._arm_entry_coverage(record.symbol.value):
            return False
        durable = dict(execution)
        durable["entry_mode"] = IMPULSE_EARLY_LIMIT_ENTRY_MODE
        durable["impulse_entry_intent"] = frozen
        new_state = dict(state)
        new_state["execution"] = durable
        try:
            fresh = self._store().save_robot_candidate_state(
                record.candidate_id,
                status="APPROVED",
                robot_state=new_state,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            self._release_entry_coverage(record.symbol.value)
            return False
        if (not self._read_admission_gate()[0]
                or self._active_other_owner_candidate_ids(fresh)
                or self._pre_entry_block_reason(fresh) is not None):
            # The durable intent is deliberately retained for safe
            # correlation. No order will be sent from this ambiguous state.
            self._release_entry_coverage(record.symbol.value)
            return True
        try:
            result = self._action_executor.create_limit(quote.request)
        except Exception:
            # Durable intent prevents a second submit after transport failure.
            return True
        if (getattr(result, "status", None) != CommandResultStatus.COMPLETED
                or not getattr(result, "order_id", None)):
            return True
        # The order may already exist if this CAS fails: until the link is
        # recovered from the create action, PAPER's admission matcher fences it.
        linked = dict(durable)
        linked["limit_order_id"] = result.order_id
        if wedge:
            linked["last_limit_index"] = state["geometry_cursor"]
        completed_state = dict(new_state)
        completed_state["execution"] = linked
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="APPROVED",
                robot_state=completed_state,
                expected_revision=fresh.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            pass
        return True

    def _advance_one(self, record: RobotCandidateRecord) -> bool:
        if (
            record.signal_snapshot.get("pattern") == "IKIGAI_BOX"
            and record.robot_state is not None
            and record.robot_state.get("phase") == "BOX_ENTRY_READY"
        ):
            return self._advance_box_entry_ready(record)

        if robot_l_shape.is_l_shape_snapshot(record.signal_snapshot):
            return self._advance_l_shape(record)

        if record.robot_state is None:
            try:
                state, _event = robot_state_machine.initialize_state(
                    self._candidate_payload(record),
                )
            except robot_state_machine.RobotStateMachineError as error:
                pattern = (record.signal_snapshot or {}).get("pattern")
                if robot_state_machine.is_supported_pattern(pattern):
                    # Only canonical 1m Scanner-frozen input is an immutable
                    # Robot v0.1 initialization fault. Older/foreign APPROVED
                    # 5m Wedge records with a pending entry can legitimately
                    # lack geometry/cursor here (MIRROR account obligations);
                    # never reinterpret those as quarantine evidence.
                    snapshot = record.signal_snapshot or {}
                    geometry = snapshot.get("robot_geometry") or snapshot.get("geometry")
                    cursor = snapshot.get("scanner_geometry_cursor")
                    if (
                        self._account_id.value == "paper"
                        and isinstance(geometry, Mapping)
                        and isinstance(cursor, Mapping)
                        and cursor.get("timeframe") == "1"
                    ):
                        # Independently revalidate *source*, not merely the
                        # initializer exception: the same exception class
                        # can also reflect a transient adapter/state fault.
                        # Use the canonical pure frozen-geometry validator;
                        # never quarantine a valid snapshot from an error
                        # message, type, or failed non-frozen dependency.
                        try:
                            robot_state_machine._snapshot_geometry(snapshot)
                        except robot_state_machine.RobotStateMachineError:
                            return self._quarantine_unstarted_frozen_fault(record, error)
                    raise
                self._invalidate_unsupported_pattern(record, error)
                return True
            if (
                state.get("phase") != robot_state_machine.PHASE_EXPIRED_AT_APEX
                and self._get_admission_catchup_candles is not None
            ):
                candles = self._get_admission_catchup_candles(
                    record.symbol.value,
                    record.signal_snapshot,
                )
                state, _events = replay_admission_catchup(
                    record.signal_snapshot,
                    state,
                    candles,
                )
            self._persist_state(record, state)
            return True

        phase = record.robot_state.get("phase")
        execution = record.robot_state.get("execution") or {}
        if (isinstance(execution, Mapping)
                and execution.get("entry_mode") == IMPULSE_EARLY_LIMIT_ENTRY_MODE):
            return self._advance_impulse_early_limit(record)
        if (phase == robot_state_machine.PHASE_WAITING_RETEST
                and self._impulse_early_paper_enabled
                and self._advance_impulse_early_limit(record)):
            return True
        if phase == robot_state_machine.PHASE_RETEST_DETECTED:
            return self._advance_retest_detected(record)
        if (phase == robot_state_machine.PHASE_WAITING_RETEST
                and self._prepare_wedge_early_impulse_research(record)):
            return True
        if phase == robot_state_machine.PHASE_EXPIRED_AT_APEX:
            return False

        candle = self._get_closed_candle(record.symbol.value)
        if candle is None:
            return False

        try:
            geometry_index = project_latest_geometry_index(
                record.signal_snapshot,
                latest_closed_candle_time_ms=int(candle["time_ms"]),
            )
        except ScannerGeometryCursorError:
            return False

        state_candle = {
            "closed": True,
            "timeframe": "1",
            "geometry_index": geometry_index,
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
        }
        new_state, event = robot_state_machine.process_closed_candle(
            record.signal_snapshot, record.robot_state, state_candle,
        )
        if event in (
            robot_state_machine.EVENT_IGNORED_STALE,
            robot_state_machine.EVENT_TERMINAL,
        ):
            return False

        self._persist_state(record, new_state)
        return True

    def _advance_l_shape(self, record: RobotCandidateRecord) -> bool:
        if record.robot_state is None:
            state, _event = robot_l_shape.initialize_state(
                self._candidate_payload(record),
            )
            self._persist_state(record, state)
            return True

        phase = record.robot_state.get("phase")
        execution = record.robot_state.get("execution") or {}
        if (isinstance(execution, Mapping)
                and execution.get("entry_mode") == IMPULSE_EARLY_LIMIT_ENTRY_MODE):
            return self._advance_impulse_early_limit(record)
        if (phase == robot_l_shape.PHASE_WAITING_RETEST
                and record.signal_snapshot.get("pattern") == "L-shape"
                and self._impulse_l_shape_paper_enabled
                and self._impulse_early_paper_enabled
                and self._advance_impulse_early_limit(record)):
            return True
        if phase == robot_state_machine.PHASE_RETEST_DETECTED:
            return self._advance_l_shape_retest_detected(record)
        if phase == robot_l_shape.PHASE_INVALIDATED:
            return False
        if phase != robot_l_shape.PHASE_WAITING_RETEST:
            raise RobotBreakoutMonitorError(
                f"unsupported L-shape Robot phase: {phase!r}"
            )

        candle = self._get_closed_candle(record.symbol.value)
        if candle is None:
            return False
        new_state, event = robot_l_shape.process_closed_candle(
            record.signal_snapshot, record.robot_state, candle,
        )
        if event in {
            robot_l_shape.EVENT_IGNORED_STALE,
            robot_l_shape.EVENT_TERMINAL,
        }:
            return False
        if new_state.get("phase") == robot_l_shape.PHASE_INVALIDATED:
            self._persist_l_shape_invalidation(record, new_state, reason=event)
            return True
        self._persist_state(record, new_state)
        return True

    def _box_source(
        self, record: RobotCandidateRecord, execution: Mapping[str, object],
    ) -> RobotCandidateRecord:
        # The frozen candidate snapshot is the only authority for the source
        # Box plan. Durable phase/execution state is mutable and must not
        # redirect a recovered candidate to a different same-symbol Box.
        snapshot = record.signal_snapshot
        source_id = (snapshot.get("source_box_candidate_id")
                     if isinstance(snapshot, Mapping) else None)
        if not isinstance(source_id, str) or not source_id.strip():
            raise RobotBreakoutMonitorError("Box Robot handoff lacks source plan identity")
        for state_id in (
            (record.robot_state or {}).get("source_box_candidate_id"),
            execution.get("source_box_candidate_id"),
        ):
            if state_id is not None and state_id != source_id:
                raise RobotBreakoutMonitorError("Box source plan conflicts with frozen candidate identity")
        source = self._store().get_robot_candidate(source_id)
        if (
            source is None
            or source.status != "BOX_PLAN_ONLY"
            or source.trading_account_id != self._account_id
            or source.symbol != record.symbol
            or source.signal_snapshot.get("pattern") != "IKIGAI_BOX"
            or source.signal_snapshot.get("identity", {}).get("symbol") != record.symbol.value
        ):
            # Account, symbol, pattern and identity must match the exact source
            # frozen before admission; never construct orders from a foreign Box.
            raise RobotBreakoutMonitorError("Box source plan is unavailable or mismatched")
        return source

    def _write_box_catchup_plan(
        self,
        record: RobotCandidateRecord,
        source: RobotCandidateRecord,
        execution: dict[str, object],
    ) -> bool:
        if self._get_market_book is None:
            return False
        book = self._get_market_book(record.symbol.value)
        if book is None:
            return False
        slots = classify_box_catchup_slots(source, book)
        market_slots = tuple(item.slot for item in slots if item.entry_mode == "MARKET")
        market_plans = build_box_market_plans(source, book, slots=market_slots)
        if market_plans and (self._market_preflight is None or self._submit_market is None):
            return False
        for plan in market_plans:
            preflight = self._market_preflight(plan.request, plan.identity)
            if (
                not getattr(preflight, "admitted", False)
                or getattr(preflight, "normalized_quantity", None) != plan.quantity
            ):
                return False
        if market_plans:
            projected_quantity = sum(
                (plan.quantity for plan in market_plans), Decimal("0")
            )
            projected_notional = sum(
                (plan.quantity * plan.best_price for plan in market_plans),
                Decimal("0"),
            )
            if projected_quantity <= 0:
                return False
            try:
                robot_protection.box_stop_for_actual_entry(
                    source.signal_snapshot,
                    average_entry=projected_notional / projected_quantity,
                )
            except Exception:
                # Do not create any ownership when the immediately caught
                # MARKET exposure cannot own a valid Box STOP under RR/P4.
                return False

        all_limits = build_box_first_grid_specs(source, created_at_ms=self._now_ms())
        limit_slots = tuple(item.slot for item in slots if item.entry_mode == "LIMIT")
        limit_specs = tuple(item for item in all_limits if item.slot in limit_slots)
        execution["entry_mode"] = "BOX_CATCHUP"
        execution["source_box_candidate_id"] = source.candidate_id
        # Re-freeze is legal only before any durable Box order ownership
        # exists. Remove markers from an earlier pre-ownership plan so a
        # newer authoritative book cannot inherit stale dispatch identities.
        for key in ("box_ownership_ready", "limit_order_ids", "market_order_ids"):
            execution.pop(key, None)
        execution["box_catchup"] = {
            "market_slots": list(market_slots),
            "limit_slots": list(limit_slots),
            "market_intents": [
                durable_box_market_intent(plan) for plan in market_plans
            ],
            "limit_order_ids": [item.order_id.value for item in limit_specs],
            "book_received_at_ms": int(book.received_at_ms),
        }
        self._persist_execution(record, execution)
        return True

    def _advance_box_entry_ready(
        self, record: RobotCandidateRecord, *, match_resting_orders: bool = True,
    ) -> bool:
        # Leave unresolved-symbol recovery to the canonical protection owner,
        # never start a new Box/MIRROR entry from an ambiguous position.
        if self._store().robot_symbol_quarantine_candidate_ids(
            self._account_id, record.symbol,
        ):
            return False
        execution = dict(record.robot_state.get("execution") or {})
        source = self._box_source(record, execution)
        catchup = execution.get("box_catchup")
        if (
            record.robot_state.get("mirror_parent_candidate_id") is not None
            and self._linked_mirror_parent(record) is None
        ):
            # The linked admission is valid only while the exact parent Wedge
            # remains the sole same-direction exposure owner.  Cancel any
            # resting entry remnants before terminalising an unfilled child.
            self._mirror_cancel_owned_limits(record, source, roles={"ENTRY"})
            ownership = self._store().load_box_order_ownership(source.candidate_id)
            if ownership:
                proof = self._store().prove_box_owned_position(source.candidate_id)
                if proof.entry_quantity > 0:
                    return self._sync_box_trade(record, execution, create_trade=True)
            self._invalidate_pre_entry_candidate(
                record, reason="MIRROR linked parent is no longer active or compatible",
            )
            return True
        if isinstance(catchup, Mapping) and self._advance_mirror_box(record):
            return True

        new_entry_admitted, terminal_stop = self._read_admission_gate()
        existing_ownership = (
            self._store().load_box_order_ownership(source.candidate_id)
            if isinstance(catchup, Mapping)
            else ()
        )
        if existing_ownership:
            try:
                existing_proof = self._store().prove_box_owned_position(source.candidate_id)
            except Exception as error:
                self._escalate_reconciliation(
                    "ROBOT_BOX_OWNERSHIP_MISMATCH "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                    f"reason={error}"
                )
                return False
            if existing_proof.entry_quantity > 0 and existing_proof.remaining_quantity == 0:
                return self._sync_box_trade(record, execution, create_trade=False)
            if existing_proof.remaining_quantity > 0 and not new_entry_admitted:
                now_ms = self._now_ms()
                for owner in existing_ownership:
                    if owner.role != "ENTRY":
                        continue
                    limit = self._store().get_paper_limit(
                        owner.order_id.value, self._account_id,
                    )
                    if limit is None or limit.status in INACTIVE_LIMIT_STATUSES:
                        continue
                    digest = hashlib.sha256(
                        f"{source.candidate_id}\0admission-closed-cancel\0{owner.order_id.value}".encode("utf-8")
                    ).hexdigest()[:32]
                    self._store().cancel_paper_limit(
                        client_action_id=f"box-admission-cancel-{digest}",
                        request_fingerprint=hashlib.sha256(
                            f"{record.symbol.value}\0{owner.order_id.value}".encode("utf-8")
                        ).hexdigest(),
                        order_id=owner.order_id,
                        trading_account_id=self._account_id,
                        updated_at_ms=now_ms,
                    )
                return self._sync_box_trade(record, execution, create_trade=True)

        if not new_entry_admitted:
            if terminal_stop and not execution.get("box_catchup"):
                self._invalidate_pre_entry_candidate(
                    record, reason="ROBOT_STOPPED before Box entry ownership",
                )
                return True
            return False
        if self._active_other_owner_candidate_ids(record):
            return False

        if not isinstance(catchup, Mapping):
            block_reason = self._pre_entry_block_reason(record)
            if block_reason is not None:
                self._invalidate_pre_entry_candidate(record, reason=block_reason)
                return True
            if self._mirror_policy is not None and mirror.mirror_record(execution) is None:
                # Decide MIRROR membership once, before any Box order or ownership exists.
                execution["mirror"] = self._mirror_attachment(record)
                if execution["mirror"].get("decision") == mirror.DEFERRED:
                    # Temporary discovery/risk failures must neither create Box orders nor
                    # make a permanent decision. Retry from unchanged durable state next tick.
                    return False
                if execution["mirror"].get("decision") == mirror.BLOCKED:
                    # An explicit MIRROR attempt whose R0/gate/terms failed never trades as a plain Box.
                    self._invalidate_pre_entry_candidate(
                        replace(record, robot_state={**record.robot_state, "execution": execution}),
                        reason=f"MIRROR {execution['mirror'].get('reason')}",
                    )
                    return True
                if (
                    record.robot_state.get("mirror_parent_candidate_id") is not None
                    and execution["mirror"].get("decision") == mirror.NOT_ATTACHED
                ):
                    # A Box admitted only as a subordinate MIRROR attempt may
                    # never fall back to an independent plain-Box position.
                    self._invalidate_pre_entry_candidate(
                        replace(record, robot_state={**record.robot_state, "execution": execution}),
                        reason=f"MIRROR {execution['mirror'].get('reason')}",
                    )
                    return True
                self._save_execution_keep_status(record, execution)
                return True
            # Owner decision: leave the native Box grid independent of the
            # impulse overlay pending second-impulse reversal research.
            # Prove the immutable FLAT/journal baseline before deriving any
            # executable catch-up plan. This is not order ownership and does
            # not require a temporary coverage arm: no order can fill yet.
            # A bad baseline therefore fails visibly without leaking an arm.
            self._store().begin_box_attempt_ownership(source.candidate_id)
            return self._write_box_catchup_plan(record, source, execution)

        raw_market_intents = catchup.get("market_intents")
        raw_market_slots = catchup.get("market_slots")
        raw_limit_slots = catchup.get("limit_slots")
        raw_limit_order_ids = catchup.get("limit_order_ids")
        if (
            not isinstance(raw_market_intents, list)
            or not isinstance(raw_market_slots, list)
            or not isinstance(raw_limit_slots, list)
            or not isinstance(raw_limit_order_ids, list)
        ):
            raise RobotBreakoutMonitorError("durable Box catch-up plan is malformed")
        market_plans = tuple(
            restore_box_market_plan(item)
            for item in raw_market_intents
            if isinstance(item, Mapping)
        )
        if len(market_plans) != len(raw_market_intents):
            raise RobotBreakoutMonitorError("durable Box MARKET intent is malformed")

        frozen_plan = source.signal_snapshot.get("plan")
        frozen_identity = source.signal_snapshot.get("identity")
        if not isinstance(frozen_plan, Mapping) or not isinstance(frozen_identity, Mapping):
            raise RobotBreakoutMonitorError("frozen Box plan is unavailable")
        frozen_quantities = frozen_plan.get("limit_quantities")
        direction = str(frozen_identity.get("direction", "")).strip().upper()
        expected_side = (
            OrderSide.BUY if direction == "LONG"
            else OrderSide.SELL if direction == "SHORT"
            else None
        )
        if (
            not isinstance(frozen_quantities, list)
            or len(frozen_quantities) != 4
            or expected_side is None
        ):
            raise RobotBreakoutMonitorError("frozen Box MARKET terms are invalid")
        for plan in market_plans:
            expected_quantity = Decimal(str(frozen_quantities[plan.slot - 1]))
            if (
                plan.slot not in {1, 2, 3, 4}
                or plan.request.symbol != source.symbol.value
                or plan.request.side is not expected_side
                or plan.quantity != expected_quantity
            ):
                raise RobotBreakoutMonitorError(
                    "durable Box MARKET intent conflicts with frozen slot"
                )

        market_slots = tuple(plan.slot for plan in market_plans)
        limit_slots = tuple(int(item) for item in raw_limit_slots)
        if tuple(int(item) for item in raw_market_slots) != market_slots:
            raise RobotBreakoutMonitorError("durable Box MARKET slots changed")
        if (
            set(market_slots) & set(limit_slots)
            or set(market_slots) | set(limit_slots) != {1, 2, 3, 4}
        ):
            raise RobotBreakoutMonitorError("durable Box catch-up slots are incomplete")

        ownership = self._store().load_box_order_ownership(source.candidate_id)
        if not ownership:
            if self._get_market_book is None:
                return False
            current_book = self._get_market_book(record.symbol.value)
            if current_book is None:
                return False
            current_market_slots = tuple(
                item.slot
                for item in classify_box_catchup_slots(source, current_book)
                if item.entry_mode == "MARKET"
            )
            if current_market_slots != market_slots:
                # No order exists yet, so re-freeze from the newer authoritative
                # book rather than turning a newly-crossed slot into a stale LIMIT.
                return self._write_box_catchup_plan(record, source, execution)

            self._store().begin_box_attempt_ownership(source.candidate_id)
            all_limits = build_box_first_grid_specs(source, created_at_ms=self._now_ms())
            limit_specs = tuple(item for item in all_limits if item.slot in set(limit_slots))
            if [item.order_id.value for item in limit_specs] != raw_limit_order_ids:
                raise RobotBreakoutMonitorError("durable Box LIMIT identities changed")
            if not self._arm_entry_coverage(record.symbol.value):
                return False
            self._store().create_box_mixed_entry_ownership(
                source.candidate_id,
                trading_account_id=self._account_id,
                symbol=record.symbol,
                market_orders=build_box_market_ownership_specs(market_plans),
                limit_orders=limit_specs,
            )
            execution["limit_order_ids"] = list(raw_limit_order_ids)
            execution["market_order_ids"] = [plan.order_id.value for plan in market_plans]
            execution["box_ownership_ready"] = True
            self._persist_execution(record, execution)
            return True

        # Crash-safe replay: ownership may already exist even if the candidate
        # state update immediately after it did not commit.
        if not execution.get("box_ownership_ready"):
            expected = {
                ("ENTRY", plan.slot, plan.order_id.value) for plan in market_plans
            }
            expected.update(
                ("ENTRY", slot, order_id)
                for slot, order_id in zip(limit_slots, raw_limit_order_ids)
            )
            actual = {(item.role, item.slot, item.order_id.value) for item in ownership}
            if actual != expected:
                raise RobotBreakoutMonitorError("durable Box entry ownership conflicts with plan")
            execution["limit_order_ids"] = list(raw_limit_order_ids)
            execution["market_order_ids"] = [plan.order_id.value for plan in market_plans]
            execution["box_ownership_ready"] = True
            self._persist_execution(record, execution)
            return True

        try:
            current_proof = self._store().prove_box_owned_position(source.candidate_id)
        except Exception as error:
            self._escalate_reconciliation(
                "ROBOT_BOX_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"reason={error}"
            )
            return False
        if current_proof.entry_quantity > 0 and current_proof.remaining_quantity == 0:
            return self._sync_box_trade(record, execution, create_trade=False)

        if current_proof.remaining_quantity > 0:
            # Proven exposure is protected before any pending MARKET slot is sent.
            # If the STOP cannot be confirmed (fail-closed close/reconciliation
            # already raised inside), no new entry exposure may be added.
            if not self._sync_box_trade(record, execution, create_trade=False):
                return False

        for plan in market_plans:
            command = self._store().get_command(plan.identity.command_id)
            if command is None:
                if self._market_preflight is None or self._submit_market is None:
                    return False
                preflight = self._market_preflight(plan.request, plan.identity)
                if (
                    not getattr(preflight, "admitted", False)
                    or getattr(preflight, "normalized_quantity", None) != plan.quantity
                ):
                    return False
            if self._submit_market is None:
                return False
            result = self._submit_market(plan.request, plan.identity)
            if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
                return True
            if not self._sync_box_trade(record, execution, create_trade=False):
                return True

        # Resting Box LIMITs are matched only on the ordered Robot market-event
        # path, which evaluates Box ownership and protection on the same event.
        # Do not call the legacy generic match_resting_orders path here.
        # Reaching this point means admission, ownership and protection hold in
        # this epoch, so the resting ENTRY grid is confirmed for matching.
        record = self._confirm_entry_admission(record, execution)
        return self._sync_box_trade(record, execution, create_trade=True)

    def _sync_box_trade(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        create_trade: bool = True,
    ) -> bool:
        source = self._box_source(record, execution)
        try:
            proof = self._store().prove_box_owned_position(source.candidate_id)
        except Exception as error:
            self._escalate_reconciliation(
                "ROBOT_BOX_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"reason={error}"
            )
            return False
        if proof.entry_quantity <= 0:
            return False
        if proof.remaining_quantity == 0:
            return self._finalize_box_take_if_flat(record, source, proof)

        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return False

        trade = self._store().get_open_robot_trade_for_symbol(
            self._account_id, record.symbol,
        )
        position_key = PositionKey(
            self._account_id, Category.LINEAR, record.symbol, 0,
        )
        projection = self._store().get_protection_projection(position_key)
        existing_stop = (
            trade.stop_price
            if trade is not None
            else projection.stop_loss
            if projection is not None
            else None
        )
        if proof.average_entry is None:
            raise RobotBreakoutMonitorError("Box open exposure lacks average entry")
        try:
            plan = robot_protection.build_box_stop_only_plan(
                self._candidate_payload(record),
                record.robot_state,
                average_entry=proof.average_entry,
                confirmed_position_quantity=proof.remaining_quantity,
                existing_stop=existing_stop,
            )
            current_stop = projection.stop_loss if projection is not None else None
            plan = self._mirror_adjust_stop(record, source, plan, proof, current_stop)
            if current_stop is None:
                stop_result = robot_protection.submit_box_stop_only(
                    self._action_executor, plan,
                )
            elif current_stop != plan.stop_price:
                stop_result = robot_protection.submit_stop_amend(
                    self._action_executor, plan,
                )
            else:
                stop_result = None
            if (
                stop_result is not None
                and getattr(stop_result, "status", None) != CommandResultStatus.COMPLETED
            ):
                raise RobotBreakoutMonitorError("Box STOP submission did not complete")
        except Exception as error:
            self._fail_closed_box_unprotected_fill(record, source, proof, error)
            return False

        try:
            confirmed = self._store().prove_box_owned_position(source.candidate_id)
        except Exception as error:
            self._escalate_reconciliation(
                "ROBOT_BOX_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"reason={error}"
            )
            return False
        if confirmed != proof:
            self._escalate_reconciliation(
                "ROBOT_BOX_OWNERSHIP_CHANGED "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return False

        quantities = source.signal_snapshot.get("plan", {}).get("limit_quantities")
        if not isinstance(quantities, list) or len(quantities) != 4:
            raise RobotBreakoutMonitorError("Box frozen grid quantities are unavailable")
        planned_quantity = sum((Decimal(str(item)) for item in quantities), Decimal("0"))
        if planned_quantity <= 0:
            raise RobotBreakoutMonitorError("Box frozen grid quantity is invalid")
        actual_wv = min(proof.entry_quantity / planned_quantity, Decimal("1"))

        market_slots = tuple(
            int(item)
            for item in (execution.get("box_catchup") or {}).get("market_slots", [])
        )
        entry_path = (
            "MARKET" if len(market_slots) == 4
            else "LIMIT" if not market_slots
            else "MIXED"
        )
        now_ms = self._now_ms()
        if trade is None and create_trade:
            if proof.average_entry is None or proof.first_execution_at_ms is None:
                raise RobotBreakoutMonitorError("Box entry proof lacks entry economics")
            trade, _created = self._store().create_robot_trade(
                trade_id=f"robot-trade-{record.candidate_id}",
                trading_account_id=self._account_id,
                candidate_id=record.candidate_id,
                symbol=record.symbol,
                direction=str(record.robot_state["direction"]),
                pattern="IKIGAI_BOX",
                source_timeframe=str(
                    record.signal_snapshot.get("identity", {}).get("timeframe", "5")
                ).strip() or "5",
                signal_time_ms=record.approved_at_ms,
                entry_time_ms=proof.first_execution_at_ms,
                entry_path=entry_path,
                actual_wv=actual_wv,
                average_entry=proof.average_entry,
                stop_price=plan.stop_price,
                take_price=plan.take_price,
                entry_quantity=proof.entry_quantity,
                entry_position_version=proof.position_version,
                created_at_ms=max(now_ms, proof.first_execution_at_ms),
            )
        elif (
            trade is not None
            and proof.entry_quantity > (trade.entry_quantity or Decimal("0"))
        ):
            if proof.average_entry is None:
                raise RobotBreakoutMonitorError("Box top-up proof lacks average entry")
            trade, _changed = self._store().refresh_open_box_trade_terms(
                trade.trade_id,
                trading_account_id=self._account_id,
                candidate_id=record.candidate_id,
                symbol=record.symbol,
                average_entry=proof.average_entry,
                entry_quantity=proof.entry_quantity,
                entry_position_version=proof.position_version,
                stop_price=plan.stop_price,
                updated_at_ms=now_ms,
            )
        self._record_box_first_fill_protection(record, plan, proof, now_ms)

        mirror_execution = record.robot_state.get("execution") or {}
        if mirror.retest_exit_requested(mirror_execution):
            exit_specs = ()                         # the MIRROR remainder close owns the exit now
        elif mirror.is_attached(mirror_execution):
            exit_specs = mirror.partial_exit_specs(
                source, mirror.mirror_record(mirror_execution),
                slots=ready_box_exit_slots(source, proof), created_at_ms=now_ms,
            )
        else:
            exit_specs = build_box_exit_specs(
                source,
                slots=ready_box_exit_slots(source, proof),
                created_at_ms=now_ms,
            )
        for spec in exit_specs:
            self._store().create_box_owned_paper_limit(
                source.candidate_id,
                role="EXIT",
                slot=spec.slot,
                client_action_id=spec.client_action_id,
                request_fingerprint=spec.request_fingerprint,
                order_id=spec.order_id,
                order_link_id=spec.order_link_id,
                trading_account_id=self._account_id,
                symbol=record.symbol,
                side=spec.side,
                price=spec.price,
                quantity=spec.quantity,
                created_at_ms=spec.created_at_ms,
            )
        return True

    def _record_box_first_fill_protection(
        self, record: RobotCandidateRecord, plan, proof, now_ms: int,
    ) -> None:
        """Keep the first armed Box STOP and its actual-fill net RR, once.

        Top-ups rewrite the trade's average entry, so the partial-fill RR is
        stored on the candidate state; a later pass never overwrites it.
        """
        fresh = self._store().get_robot_candidate(record.candidate_id)
        if fresh is None or fresh.status not in {"APPROVED", "OPEN"}:
            return
        state = dict(fresh.robot_state or {})
        execution = dict(state.get("execution") or {})
        if "box_first_fill_protection" in execution:
            return
        execution["box_first_fill_protection"] = {
            "stop_basis": plan.stop_basis,
            "stop_price": str(plan.stop_price),
            "take_price": str(plan.take_price),
            "average_entry": str(proof.average_entry),
            "entry_quantity": str(proof.entry_quantity),
            "actual_fill_net_rr": (
                str(plan.actual_fill_net_rr) if plan.actual_fill_net_rr is not None else None
            ),
            "recorded_at_ms": now_ms,
        }
        state["execution"] = execution
        try:
            self._store().save_robot_candidate_state(
                fresh.candidate_id,
                status=fresh.status,
                robot_state=state,
                expected_revision=fresh.state_revision,
                updated_at_ms=now_ms,
            )
        except ConcurrentUpdate:
            # The STOP is already armed; a concurrent writer only delays the record.
            return

    def _completed_box_stop_preempts_stale_take(
        self, record: RobotCandidateRecord, source: RobotCandidateRecord, proof,
        fresh: RobotCandidateRecord,
    ) -> bool:
        """Read-only, exact STOP witness. Never clear an existing recovery fence.

        An old OPEN snapshot may still reach the Box TAKE finalizer after
        the canonical STOP transaction closed both trade and candidate.
        Only the fully settled SAME candidate/source/execution/FLAT lot may
        be ignored. Absence or ambiguity is never treated as completion.
        """
        store = self._store()
        if (
            record.status != "OPEN" or fresh.status != "CLOSED"
            or record.trading_account_id != self._account_id
            or fresh.trading_account_id != self._account_id
            or source.trading_account_id != self._account_id
            or fresh.candidate_id != record.candidate_id
            or fresh.symbol != record.symbol or source.symbol != record.symbol
            or fresh.snapshot_sha256 != record.snapshot_sha256
            or record.signal_snapshot.get("pattern") != "IKIGAI_BOX"
            or fresh.signal_snapshot.get("pattern") != "IKIGAI_BOX"
            or source.status != "BOX_PLAN_ONLY"
            or source.signal_snapshot.get("pattern") != "IKIGAI_BOX"
            or record.signal_snapshot.get("source_box_candidate_id") != source.candidate_id
            or fresh.signal_snapshot.get("source_box_candidate_id") != source.candidate_id
            or fresh.updated_at_ms < record.updated_at_ms
            or proof.candidate_id != source.candidate_id
            or not (proof.entry_quantity > 0 and proof.exit_quantity > 0
                    and proof.remaining_quantity == 0
                    and proof.entry_quantity == proof.exit_quantity)
        ):
            return False
        # The canonical Box protection finalizer closes with this exact
        # immutable proof tuple. STOP identity and FLAT alone do not certify
        # the exit price, gross PnL, net percentage, or accumulated fees.
        if (
            not isinstance(proof.average_exit, Decimal)
            or not proof.average_exit.is_finite() or proof.average_exit <= 0
            or not isinstance(proof.entry_notional, Decimal)
            or not proof.entry_notional.is_finite() or proof.entry_notional <= 0
            or not isinstance(proof.realized_pnl, Decimal)
            or not proof.realized_pnl.is_finite()
            or not isinstance(proof.accumulated_fee, Decimal)
            or not proof.accumulated_fee.is_finite() or proof.accumulated_fee < 0
        ):
            return False
        realized_pct = (
            (proof.realized_pnl - proof.accumulated_fee)
            / proof.entry_notional
            * Decimal("100")
        )
        trade = store.get_robot_trade(f"robot-trade-{record.candidate_id}")
        if (
            trade is None or trade.candidate_id != record.candidate_id
            or trade.trading_account_id != self._account_id
            or trade.symbol != record.symbol or trade.pattern != "IKIGAI_BOX"
            or trade.exit_reason != "STOP" or trade.exit_time_ms is None
            or proof.last_execution_at_ms != trade.exit_time_ms
            or trade.exit_price != proof.average_exit
            or trade.realized_pnl_usdt != proof.realized_pnl
            or trade.realized_pnl_pct != realized_pct
            or trade.fees_costs_usdt != proof.accumulated_fee
        ):
            return False
        obligation = store.get_paper_protection_obligation_for_trade(trade.trade_id)
        if (
            obligation is None or obligation.trade_id != trade.trade_id
            or obligation.trading_account_id != self._account_id
            or obligation.symbol != record.symbol
            or obligation.status != "RESOLVED" or obligation.winning_leg != "STOP"
            or obligation.exec_id.value not in proof.execution_ids
        ):
            return False
        actual_stop = store.get_execution(ExecutionDedupKey(
            self._account_id, Category.LINEAR, obligation.exec_id,
        ))
        if (
            actual_stop is None or actual_stop.symbol != record.symbol
            or actual_stop.order_id != obligation.order_id
            or actual_stop.exchange_timestamp_ms != trade.exit_time_ms
        ):
            return False
        position = store.get_position_projection(PositionKey(
            self._account_id, Category.LINEAR, record.symbol, 0,
        ))
        if (
            position is None or position.side is not PositionSide.FLAT
            or position.quantity.value != 0 or position.sync_state != "synced"
            or position.version != proof.position_version
            or any(item.symbol == record.symbol
                   for item in store.load_open_robot_trades(self._account_id))
            or store.load_active_robot_candidates_for_symbol(
                self._account_id, record.symbol,
            )
            or store.load_active_paper_limits(self._account_id, record.symbol)
            or any(item.symbol == record.symbol
                   for item in store.load_unfinished_commands())
            or any(item.symbol == record.symbol
                   for item in store.load_unresolved_paper_protection_obligations(
                       self._account_id,
                   ))
        ):
            return False
        return True

    def _finalize_box_take_if_flat(
        self, record: RobotCandidateRecord, source: RobotCandidateRecord, proof,
    ) -> bool:
        if proof.exit_quantity <= 0:
            return False

        if record.status == "OPEN":
            # STOP may have durably CLOSED the canonical candidate after this
            # stale OPEN record was read. Check BEFORE any Box order cancels,
            # protection clears, or generic TAKE bookkeeping. Only an exact
            # settled STOP is a no-mutation success; all other terminal drift
            # remains fenced, never replays TAKE or overwrites STOP economics.
            fresh = self._store().get_robot_candidate(record.candidate_id)
            if fresh is None or fresh.status != "OPEN":
                if (fresh is not None and fresh.status == "CLOSED"
                        and self._completed_box_stop_preempts_stale_take(
                            record, source, proof, fresh,
                        )):
                    return True
                self._escalate_reconciliation(
                    "ROBOT_BOX_STALE_TAKE_TERMINAL_UNPROVEN "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
                )
                return False

        now_ms = self._now_ms()
        for owner in self._store().load_box_order_ownership(source.candidate_id):
            order = self._store().get_paper_limit(owner.order_id.value, self._account_id)
            if order is None or order.status in INACTIVE_LIMIT_STATUSES:
                continue
            digest = hashlib.sha256(
                f"{source.candidate_id}\0take-finalize\0{owner.order_id.value}".encode("utf-8")
            ).hexdigest()[:32]
            self._store().cancel_paper_limit(
                client_action_id=f"box-take-cancel-{digest}",
                request_fingerprint=hashlib.sha256(
                    f"{record.symbol.value}\0{owner.order_id.value}".encode("utf-8")
                ).hexdigest(),
                order_id=owner.order_id,
                trading_account_id=self._account_id,
                updated_at_ms=now_ms,
            )

        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        self._store().clear_paper_protection_for_flat(position_key)

        if record.status == "APPROVED":
            execution = dict(record.robot_state.get("execution") or {})
            execution["box_take_realized_before_open"] = True
            execution["box_take_realized_at_ms"] = (
                proof.last_execution_at_ms if proof.last_execution_at_ms is not None else now_ms
            )
            state = dict(record.robot_state)
            state["execution"] = execution
            try:
                self._store().save_robot_candidate_state(
                    record.candidate_id,
                    status="INVALIDATED",
                    robot_state=state,
                    expected_revision=record.state_revision,
                    updated_at_ms=now_ms,
                )
            except ConcurrentUpdate:
                return False
            self._release_entry_coverage(record.symbol.value)
            return True

        if record.status != "OPEN":
            return False
        trade = self._store().get_open_robot_trade_for_symbol(
            self._account_id, record.symbol,
        )
        # STOP/EMERGENCY_CLOSE evidence must win over Box's generic TAKE
        # finalizer when its own market execution has just made the lot FLAT.
        if trade is not None:
            obligation = self._store().get_paper_protection_obligation_for_trade(trade.trade_id)
            if obligation is not None and obligation.status != "RESOLVED":
                return False
        if trade is None or trade.candidate_id != record.candidate_id:
            self._escalate_reconciliation(
                "ROBOT_BOX_TAKE_TRADE_MISSING "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return False
        if (
            proof.average_exit is None
            or proof.last_execution_at_ms is None
            or proof.entry_notional <= 0
        ):
            raise RobotBreakoutMonitorError("Box TAKE proof lacks exit economics")
        realized_pct = (
            (proof.realized_pnl - proof.accumulated_fee)
            / proof.entry_notional
            * Decimal("100")
        )
        self._store().close_robot_trade(
            trade.trade_id,
            exit_time_ms=proof.last_execution_at_ms,
            exit_price=proof.average_exit,
            # A MIRROR remainder closed at the retest is the campaign TAKE (owner rule 6); its
            # MIRROR identity stays in robot_state.execution["mirror"]["exit"].
            exit_reason="TAKE",
            realized_pnl_usdt=proof.realized_pnl,
            realized_pnl_pct=realized_pct,
            fees_costs_usdt=proof.accumulated_fee,
            updated_at_ms=now_ms,
        )
        self._release_entry_coverage(record.symbol.value)
        return True

    def _advance_l_shape_retest_detected(
        self, record: RobotCandidateRecord, *, match_resting_orders: bool = True,
    ) -> bool:
        execution = dict(record.robot_state.get("execution") or {})
        if self._hold_unproven_emergency_close(record, execution):
            return False
        # Preserve legacy Double Top/Bottom cancellation/recovery before new
        # entry safety guards. New L-shape entries run _pre_entry_block_reason
        # and the owner-side LIMIT matcher independently fences the symbol.

        if "limit_order_id" not in execution:
            # Previously APPROVED standalone Double Top/Bottom candidates
            # from an older release must not place their first order.
            # Do not invalidate OPEN/filled trades or interrupt STOP/TAKE.
            if (record.status == "APPROVED"
                    and record.signal_snapshot.get("pattern") in robot_l_shape.DOUBLE_PATTERNS):
                # APPROVED alone does not prove that an earlier fill, trade or
                # protection obligation is absent. Only retire a proven inert
                # pre-entry candidate; preserve ambiguous/exposed lifecycles.
                if not self._paper_candidate_is_inert(record):
                    return False
                self._invalidate_pre_entry_candidate(
                    record, reason="Double Top/Bottom is auxiliary-only",
                )
                return True
            candle = self._get_closed_candle(record.symbol.value)
            if candle is not None:
                invalidation = robot_l_shape.invalidation_event(
                    record.signal_snapshot, candle,
                )
                if invalidation is not None:
                    state = dict(record.robot_state)
                    state["phase"] = robot_l_shape.PHASE_INVALIDATED
                    state["last_event"] = invalidation
                    state["last_candle_time_ms"] = int(candle["time_ms"])
                    self._persist_l_shape_invalidation(
                        record, state, reason=invalidation,
                    )
                    return True

            new_entry_admitted, terminal_stop = self._read_admission_gate()
            if not new_entry_admitted:
                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ROBOT_STOPPED before L-shape entry submission",
                    )
                    return True
                return False
            if self._active_other_owner_candidate_ids(record):
                return False
            block_reason = self._pre_entry_block_reason(record)
            if block_reason is not None:
                self._invalidate_pre_entry_candidate(record, reason=block_reason)
                return True

            plan = robot_l_shape.build_initial_retest_limit(
                self._candidate_payload(record),
                record.robot_state,
                tick_size=self._tick_size_provider(record.symbol.value),
            )
            rr_skip = self._l_shape_entry_rr_skip(record, plan)
            if rr_skip is not None:
                reason, details = rr_skip
                self._invalidate_pre_entry_candidate(
                    record, reason=reason, details=details,
                )
                return True
            if robot_l_shape.is_mirror_snapshot(record.signal_snapshot) and not mirror.is_attached(execution):
                # Standalone MIRROR: the campaign must still be live (no entry after the first retest) and the
                # attempt must fit the campaign's single R0 budget. The decision is made durable on its own
                # tick, before any order exists; the LIMIT follows on the next tick.
                if not robot_l_shape.mirror_standalone_enabled():
                    self._invalidate_pre_entry_candidate(
                        record, reason="MIRROR standalone Robot is not enabled",
                    )
                    return True
                decision = self._mirror_standalone_attachment(record, plan)
                if decision.get("decision") == mirror.DEFERRED:
                    # Keep transient failures retryable, but do not discard the only
                    # diagnostic explaining why an APPROVED MIRROR has no order.
                    # Persist only on reason changes to avoid a write per monitor tick.
                    reason = str(decision.get("reason") or "unknown")
                    if execution.get("mirror_deferred_reason") != reason:
                        execution["mirror_deferred_reason"] = reason
                        execution["mirror_deferred_at_ms"] = self._now_ms()
                        self._persist_execution(record, execution)
                    return False
                if decision.get("decision") != mirror.ATTACHED:
                    execution["mirror"] = decision
                    record = self._with_execution(record, execution)
                    self._invalidate_pre_entry_candidate(
                        record, reason=f"MIRROR {decision.get('reason')}",
                    )
                    return True
                execution["mirror"] = decision
                self._persist_execution(record, execution)
                return True
            if not self._pattern_flow_allows_entry(record):
                return False
            if not self._arm_entry_coverage(record.symbol.value):
                return False
            result = robot_entry_limit.submit_initial_retest_limit(
                self._action_executor, plan,
            )
            order_id = getattr(result, "order_id", None)
            if not order_id:
                self._release_entry_coverage(record.symbol.value)
                return False
            execution["limit_order_id"] = order_id
            execution["l_shape_retest_time_ms"] = plan.retest_time_ms
            self._persist_execution(record, execution)
            return True

        order = self._store().get_paper_limit(
            execution["limit_order_id"], self._account_id,
        )
        if order is None or order.quantity <= 0:
            return False

        if execution.get("entry_mode") == IMPULSE_EARLY_LIMIT_ENTRY_MODE:
            intent = execution.get("impulse_entry_intent")
            decision_ms = intent.get("decision_ms") if isinstance(intent, Mapping) else None
            if type(decision_ms) is not int:
                self._escalate_reconciliation(
                    f"ROBOT_LSHAPE_IMPULSE_CLOCK_UNPROVEN candidate_id={record.candidate_id}"
                )
                return False
            if self._now_ms() - decision_ms > IMPULSE_ENTRY_LIMIT_MAX_AGE_MS:
                if order.status not in INACTIVE_LIMIT_STATUSES:
                    digest = hashlib.sha256(
                        f"{record.candidate_id}\0impulse-expired-entry".encode("utf-8")
                    ).hexdigest()[:32]
                    cancelled = self._action_executor.cancel_limit(
                        PaperLimitCancelRequest(
                            ClientActionId(f"robot-impulse-expiry-{digest}"),
                            record.symbol.value, order.order_id.value,
                        )
                    )
                    if getattr(cancelled, "status", None) != CommandResultStatus.COMPLETED:
                        return False
                    refreshed = self._store().get_paper_limit(
                        order.order_id.value, self._account_id,
                    )
                    if refreshed is None or refreshed.status not in INACTIVE_LIMIT_STATUSES:
                        return False
                    order = refreshed

        # An old APPROVED standalone Double Top/Bottom may already own an
        # entry LIMIT from a previous release. Blocking fresh submissions is
        # insufficient: it could still match on the next owner tick.
        if (record.status == "APPROVED"
                and record.signal_snapshot.get("pattern") in robot_l_shape.DOUBLE_PATTERNS):
            # The durable execution ID must still name this candidate's symbol.
            # Never cancel a different symbol's PAPER order through stale state.
            if order.symbol != record.symbol:
                return False
            if order.status not in INACTIVE_LIMIT_STATUSES:
                cancellation = self._action_executor.cancel_limit(
                    PaperLimitCancelRequest(
                        _cancel_blocked_entry_action_id(record.candidate_id),
                        record.symbol.value, execution["limit_order_id"],
                    )
                )
                if getattr(cancellation, "status", None) != CommandResultStatus.COMPLETED:
                    return False
                order = self._store().get_paper_limit(
                    execution["limit_order_id"], self._account_id,
                )
                if order is None or order.quantity <= 0 or order.symbol != record.symbol:
                    return False
            if order.status not in INACTIVE_LIMIT_STATUSES:
                return False
            if order.filled_quantity <= 0:
                # Never claim an inert candidate from an absent/unknown order
                # or a contradictory FILLED state without an actual fill.
                if order.status != "cancelled":
                    return False
                if not self._cancelled_legacy_double_is_inert(
                    record, execution["limit_order_id"],
                ):
                    return False
                self._invalidate_pre_entry_candidate(
                    record, reason="Double Top/Bottom legacy LIMIT cancelled without fill",
                )
                return True
            # An actual partial/full fill must retain normal Robot trade,
            # protection and STOP/TAKE finalization, never be invalidated.

        filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
        inactive = order.status in INACTIVE_LIMIT_STATUSES

        if filled_fraction <= 0:
            block_reason = self._pre_entry_block_reason(
                record, allowed_limit_order_id=execution["limit_order_id"],
            )
            if block_reason is not None:
                if not inactive:
                    self._action_executor.cancel_limit(PaperLimitCancelRequest(
                        _cancel_blocked_entry_action_id(record.candidate_id),
                        record.symbol.value,
                        execution["limit_order_id"],
                    ))
                self._invalidate_pre_entry_candidate(record, reason=block_reason)
                return True

            new_entry_admitted, terminal_stop = self._read_admission_gate()
            if not new_entry_admitted:
                if not inactive:
                    self._action_executor.cancel_limit(PaperLimitCancelRequest(
                        _cancel_blocked_entry_action_id(record.candidate_id),
                        record.symbol.value,
                        execution["limit_order_id"],
                    ))
                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record,
                        reason="ROBOT_STOPPED with unfilled L-shape entry LIMIT",
                    )
                return True

            candle = self._get_closed_candle(record.symbol.value)
            if candle is not None:
                invalidation = robot_l_shape.invalidation_event(
                    record.signal_snapshot, candle,
                )
                if invalidation is not None:
                    if not inactive:
                        result = self._action_executor.cancel_limit(
                            PaperLimitCancelRequest(
                                _cancel_l_shape_invalid_action_id(record.candidate_id),
                                record.symbol.value,
                                execution["limit_order_id"],
                            )
                        )
                        if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
                            return False
                    state = dict(record.robot_state)
                    state["phase"] = robot_l_shape.PHASE_INVALIDATED
                    state["last_event"] = invalidation
                    state["last_candle_time_ms"] = int(candle["time_ms"])
                    self._persist_l_shape_invalidation(
                        record, state, reason=invalidation,
                    )
                    return True

            if inactive:
                self._invalidate_pre_entry_candidate(
                    record, reason="ENTRY_LIMIT_INACTIVE_BEFORE_FILL",
                )
                return True

            record = self._confirm_entry_admission(record, execution)
            if match_resting_orders and self._match_resting_orders is not None:
                self._match_resting_orders(record.symbol.value)
                order = self._store().get_paper_limit(
                    execution["limit_order_id"], self._account_id,
                )
                if order is None or order.quantity <= 0:
                    return False
                filled_fraction = min(
                    order.filled_quantity / order.quantity, Decimal("1"),
                )
                inactive = order.status in INACTIVE_LIMIT_STATUSES
            if filled_fraction <= 0:
                if inactive:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ENTRY_LIMIT_INACTIVE_BEFORE_FILL",
                    )
                    return True
                return False

        if not inactive:
            self._action_executor.cancel_limit(PaperLimitCancelRequest(
                _cancel_partial_remainder_action_id(record.candidate_id),
                record.symbol.value,
                execution["limit_order_id"],
            ))
            refreshed = self._store().get_paper_limit(
                execution["limit_order_id"], self._account_id,
            )
            if refreshed is not None:
                order = refreshed
                filled_fraction = min(
                    order.filled_quantity / order.quantity, Decimal("1"),
                )

        if filled_fraction <= 0:
            return True

        fresh_record = self._store().get_robot_candidate(record.candidate_id) or record
        self._finalize_trade(
            fresh_record,
            execution,
            entry_path="LIMIT",
            actual_wv=filled_fraction,
        )
        return True

    def _advance_retest_detected(
        self, record: RobotCandidateRecord, *, match_resting_orders: bool = True,
    ) -> bool:
        if robot_l_shape.is_l_shape_snapshot(record.signal_snapshot):
            return self._advance_l_shape_retest_detected(
                record, match_resting_orders=match_resting_orders,
            )
        execution = dict(record.robot_state.get("execution") or {})
        if self._hold_unproven_emergency_close(record, execution):
            return False
        # This covers already-resting, partial and late-Market entry paths:
        # no new dispatch or entry finalization on a quarantined symbol.
        if self._store().robot_symbol_quarantine_candidate_ids(
            self._account_id, record.symbol,
        ):
            return False

        if (
            execution.get("entry_mode") == LATE_ADMISSION_MARKET
            and "limit_order_id" not in execution
        ):
            return self._advance_late_admission(record, execution)

        if "limit_order_id" not in execution:
            candle = self._get_closed_candle(record.symbol.value)
            if candle is None:
                return False
            try:
                geometry_index = project_latest_geometry_index(
                    record.signal_snapshot,
                    latest_closed_candle_time_ms=int(candle["time_ms"]),
                )
            except ScannerGeometryCursorError:
                return False
            apex_index = _frozen_robot_apex_index(record.signal_snapshot)
            if Decimal(geometry_index) >= apex_index:
                expired_state = dict(record.robot_state)
                expired_state["phase"] = robot_state_machine.PHASE_EXPIRED_AT_APEX
                expired_state["last_event"] = robot_state_machine.EVENT_EXPIRED_AT_APEX
                expired_state["geometry_cursor"] = geometry_index
                self._persist_state(record, expired_state)
                return True

            new_entry_admitted, terminal_stop = self._read_admission_gate()
            if not new_entry_admitted:
                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ROBOT_STOPPED before entry order submission",
                    )
                    return True
                return False

            if self._active_other_owner_candidate_ids(record):
                return False

            block_reason = self._pre_entry_block_reason(record)
            if block_reason is not None:
                self._invalidate_pre_entry_candidate(record, reason=block_reason)
                return True

            plan = self._build_initial_retest_limit_plan(record, record.robot_state)
            rr_skip = self._entry_rr_skip(record, plan)
            if rr_skip is not None:
                reason, details = rr_skip
                self._invalidate_pre_entry_candidate(record, reason=reason, details=details)
                return True
            # The same approved-pattern timing overlay shared with L-shape,
            # and MIRROR. No second
            # strategy, candidate, order or STOP/TAKE is ever introduced.
            if not self._pattern_flow_allows_entry(record):
                return False
            if not self._arm_entry_coverage(record.symbol.value):
                return False
            result = robot_entry_limit.submit_initial_retest_limit(self._action_executor, plan)
            order_id = getattr(result, "order_id", None)
            if not order_id:
                self._release_entry_coverage(record.symbol.value)
                return False
            execution["limit_order_id"] = order_id
            execution["last_limit_index"] = geometry_index
            self._persist_execution(record, execution)
            return True

        if match_resting_orders and self._match_resting_orders is not None:
            self._match_resting_orders(record.symbol.value)

        order = self._store().get_paper_limit(execution["limit_order_id"], self._account_id)
        if order is None or order.quantity <= 0:
            return False

        if execution.get("entry_mode") == IMPULSE_EARLY_LIMIT_ENTRY_MODE:
            intent = execution.get("impulse_entry_intent")
            decision_ms = intent.get("decision_ms") if isinstance(intent, Mapping) else None
            if type(decision_ms) is not int:
                self._escalate_reconciliation(
                    f"ROBOT_IMPULSE_ENTRY_CLOCK_UNPROVEN candidate_id={record.candidate_id}"
                )
                return False
            if self._now_ms() - decision_ms > IMPULSE_ENTRY_LIMIT_MAX_AGE_MS:
                if order.status not in INACTIVE_LIMIT_STATUSES:
                    digest = hashlib.sha256(
                        f"{record.candidate_id}\0impulse-expired-entry".encode("utf-8")
                    ).hexdigest()[:32]
                    result = self._action_executor.cancel_limit(
                        PaperLimitCancelRequest(
                            ClientActionId(f"robot-impulse-expiry-{digest}"),
                            record.symbol.value, order.order_id.value,
                        )
                    )
                    if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
                        return False
                    refreshed = self._store().get_paper_limit(
                        order.order_id.value, self._account_id,
                    )
                    if refreshed is None or refreshed.status not in INACTIVE_LIMIT_STATUSES:
                        return False
                    order = refreshed

        filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
        inactive = order.status in INACTIVE_LIMIT_STATUSES

        if filled_fraction <= 0:
            block_reason = self._pre_entry_block_reason(
                record, allowed_limit_order_id=execution["limit_order_id"],
            )
            if block_reason is not None:
                if not inactive:
                    self._action_executor.cancel_limit(PaperLimitCancelRequest(
                        _cancel_blocked_entry_action_id(record.candidate_id),
                        record.symbol.value, execution["limit_order_id"],
                    ))
                self._invalidate_pre_entry_candidate(record, reason=block_reason)
                return True

            new_entry_admitted, terminal_stop = self._read_admission_gate()
            if not new_entry_admitted:
                if not inactive:
                    self._action_executor.cancel_limit(PaperLimitCancelRequest(
                        _cancel_blocked_entry_action_id(record.candidate_id),
                        record.symbol.value, execution["limit_order_id"],
                    ))
                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ROBOT_STOPPED with unfilled resting entry LIMIT",
                    )
                return True

            if inactive:
                self._invalidate_pre_entry_candidate(
                    record,
                    reason="ENTRY_LIMIT_INACTIVE_BEFORE_FILL",
                )
                return True

            candle = self._get_closed_candle(record.symbol.value)
            if candle is None:
                return False
            try:
                geometry_index = project_latest_geometry_index(
                    record.signal_snapshot,
                    latest_closed_candle_time_ms=int(candle["time_ms"]),
                )
            except ScannerGeometryCursorError:
                return False

            apex_index = _frozen_robot_apex_index(record.signal_snapshot)
            if Decimal(geometry_index) >= apex_index:
                result = self._action_executor.cancel_limit(PaperLimitCancelRequest(
                    _cancel_apex_entry_action_id(record.candidate_id),
                    record.symbol.value,
                    execution["limit_order_id"],
                ))
                if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
                    return False
                expired_state = dict(record.robot_state)
                expired_state["phase"] = robot_state_machine.PHASE_EXPIRED_AT_APEX
                expired_state["last_event"] = robot_state_machine.EVENT_EXPIRED_AT_APEX
                expired_state["geometry_cursor"] = geometry_index
                expired_execution = dict(execution)
                expired_execution["cancelled_at_apex_index"] = geometry_index
                expired_state["execution"] = expired_execution
                self._persist_state(record, expired_state)
                return True

            # Admission, liveness and apex all hold in this epoch: the resting
            # ENTRY may now be matched by the runtime.
            record = self._confirm_entry_admission(record, execution)
            last_limit_index = int(
                execution.get(
                    "last_limit_index",
                    record.robot_state.get("retest_index"),
                )
            )
            if geometry_index < last_limit_index:
                return False
            if not robot_entry_limit.reprice_due(
                last_limit_index=last_limit_index,
                current_index=geometry_index,
            ):
                return False

            plan = robot_entry_limit.build_retest_limit_reprice(
                self._candidate_payload(record),
                record.robot_state,
                geometry_index=geometry_index,
                tick_size=self._tick_size_provider(record.symbol.value),
                order_id=execution["limit_order_id"],
            )
            if execution.get("entry_mode") == IMPULSE_EARLY_LIMIT_ENTRY_MODE:
                # Original frozen impulse quote is NEVER rewritten to a
                # retest-boundary price. Entry remains with the same owner.
                return False
            # The reprice changes the prospective entry price. Do not amend a
            # previously admitted resting LIMIT to a price with poor or
            # uncomputable RR; keep monitoring the original proven order.
            if self._entry_rr_skip(
                record, plan, direction=str(record.robot_state["direction"]),
            ) is not None:
                return False
            result = robot_entry_limit.submit_retest_limit_reprice(
                self._action_executor, plan,
            )
            if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
                return False
            execution["last_limit_index"] = geometry_index
            self._persist_execution(record, execution)
            return True

        if not inactive:
            self._action_executor.cancel_limit(PaperLimitCancelRequest(
                _cancel_partial_remainder_action_id(record.candidate_id),
                record.symbol.value, execution["limit_order_id"],
            ))
            refreshed = self._store().get_paper_limit(
                execution["limit_order_id"], self._account_id,
            )
            if refreshed is not None:
                order = refreshed
                filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))

        if filled_fraction <= 0:
            return True

        fresh_record = self._store().get_robot_candidate(record.candidate_id) or record
        self._finalize_trade(
            fresh_record, execution, entry_path="LIMIT",
            actual_wv=filled_fraction,
        )
        return True

    def _advance_late_admission(
        self, record: RobotCandidateRecord, execution: dict[str, object],
    ) -> bool:
        if self._hold_unproven_emergency_close(record, execution):
            return False
        # This covers already-resting, partial and late-Market entry paths:
        # no new dispatch or entry finalization on a quarantined symbol.
        if self._store().robot_symbol_quarantine_candidate_ids(
            self._account_id, record.symbol,
        ):
            return False
        intent = execution.get("late_market_intent")

        if isinstance(intent, Mapping):
            if self._finalize_trade(
                record, execution, entry_path="MARKET",
                actual_wv=Decimal("1"),
            ):
                return True

        if (
            self._get_market_book is None
            or self._market_preflight is None
            or self._submit_market is None
        ):
            return False

        new_entry_admitted, terminal_stop = self._read_admission_gate()
        if not new_entry_admitted:
            if terminal_stop and not isinstance(intent, Mapping):
                self._invalidate_pre_entry_candidate(
                    record, reason="ROBOT_STOPPED before late Market submission",
                )
                return True
            return False
        if self._active_other_owner_candidate_ids(record):
            return False

        block_reason = self._pre_entry_block_reason(record)
        if block_reason is not None:
            self._invalidate_pre_entry_candidate(record, reason=block_reason)
            return True

        if isinstance(intent, Mapping):
            plan = restore_late_admission_market_plan(intent)
            result = self._submit_market(plan.request, plan.identity)
            if getattr(result, "status", None) == CommandResultStatus.COMPLETED:
                fresh = self._store().get_robot_candidate(record.candidate_id) or record
                fresh_execution = dict(fresh.robot_state.get("execution") or execution)
                self._finalize_trade(
                    fresh, fresh_execution, entry_path="MARKET",
                    actual_wv=Decimal("1"),
                )
            return True

        candle = self._get_closed_candle(record.symbol.value)
        if candle is None:
            return False
        try:
            geometry_index = project_latest_geometry_index(
                record.signal_snapshot,
                latest_closed_candle_time_ms=int(candle["time_ms"]),
            )
        except ScannerGeometryCursorError:
            return False

        book = self._get_market_book(record.symbol.value)
        if book is None:
            return False
        plan = build_late_admission_market_plan(
            self._candidate_payload(record), record.robot_state, book,
        )
        preflight = self._market_preflight(plan.request, plan.identity)
        if not getattr(preflight, "admitted", False):
            return False
        normalized_quantity = getattr(preflight, "normalized_quantity", None)
        if not isinstance(normalized_quantity, Decimal) or normalized_quantity <= 0:
            return False

        direction = str(record.robot_state.get("direction", "")).strip().upper()
        structural_extreme = self._structural_extreme(
            record.signal_snapshot, direction,
        )
        tick_size = self._tick_size_provider(record.symbol.value)
        reference_price, target_price = self._frozen_prices(
            record.signal_snapshot, direction,
        )
        decision = evaluate_late_admission(
            record.signal_snapshot,
            record.robot_state,
            book,
            quantity=Quantity(normalized_quantity),
            current_geometry_index=geometry_index,
            now_ms=self._now_ms(),
            max_book_age_ms=self._late_market_max_book_age_ms,
            structural_extreme=structural_extreme,
            tick_size=tick_size,
            frozen_signal_reference_price=reference_price,
            frozen_scanner_target_price=target_price,
            admission_ready=True,
            ownership_clear=True,
        )
        if decision.action == LATE_DECISION_APEX_REACHED:
            expired_state = dict(record.robot_state)
            expired_state["phase"] = robot_state_machine.PHASE_EXPIRED_AT_APEX
            expired_state["last_event"] = robot_state_machine.EVENT_EXPIRED_AT_APEX
            expired_state["geometry_cursor"] = geometry_index
            self._persist_state(record, expired_state)
            return True
        if decision.action != LATE_DECISION_MARKET_ENTRY:
            return False
        # No new Market entry can bypass the same exact-ID timing check.
        # Persisted intents skip this check and remain owned by recovery.
        if not self._pattern_flow_allows_entry(record):
            return False

        intent = durable_late_admission_market_intent(
            plan,
            normalized_quantity=normalized_quantity,
            current_geometry_index=geometry_index,
            projected_vwap=decision.projected_vwap,
            stop_price=decision.stop_price,
            take_price=decision.take_price,
            expected_reward=decision.expected_reward,
            rr=decision.rr,
            adverse_slippage=decision.adverse_slippage,
            persisted_at_ms=self._now_ms(),
        )
        durable_execution = dict(execution)
        durable_execution["late_market_intent"] = intent
        durable_state = dict(record.robot_state)
        durable_state["execution"] = durable_execution
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="APPROVED",
                robot_state=durable_state,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            return False

        fresh = self._store().get_robot_candidate(record.candidate_id)
        if fresh is None:
            return True
        new_entry_admitted, _terminal_stop = self._read_admission_gate()
        if not new_entry_admitted or self._active_other_owner_candidate_ids(fresh):
            return True
        block_reason = self._pre_entry_block_reason(fresh)
        if block_reason is not None:
            self._invalidate_pre_entry_candidate(fresh, reason=block_reason)
            return True

        result = self._submit_market(plan.request, plan.identity)
        if getattr(result, "status", None) == CommandResultStatus.COMPLETED:
            fresh = self._store().get_robot_candidate(record.candidate_id) or fresh
            fresh_execution = dict(fresh.robot_state.get("execution") or durable_execution)
            self._finalize_trade(
                fresh, fresh_execution, entry_path="MARKET",
                actual_wv=Decimal("1"),
            )
        return True

    def _finalize_trade(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        entry_path: str,
        actual_wv: Decimal,
    ) -> bool:
        if self._hold_unproven_emergency_close(record, execution):
            return False
        # This covers already-resting, partial and late-Market entry paths:
        # no new dispatch or entry finalization on a quarantined symbol.
        if self._store().robot_symbol_quarantine_candidate_ids(
            self._account_id, record.symbol,
        ):
            return False
        direction = record.robot_state["direction"]
        try:
            entry_evidence = self._prove_entry_evidence(
                record, execution, entry_path=entry_path,
            )
        except RobotBreakoutMonitorError as error:
            self._escalate_reconciliation(
                "ROBOT_ENTRY_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"reason={error}"
            )
            return False
        if entry_evidence is None:
            return False

        average_entry = entry_evidence.average_entry
        try:
            payload = self._candidate_payload(record)
            if robot_l_shape.is_l_shape_snapshot(record.signal_snapshot):
                plan = robot_protection.build_l_shape_protection_plan(
                    payload,
                    record.robot_state,
                    average_entry=average_entry,
                    tick_size=self._tick_size_provider(record.symbol.value),
                )
            else:
                structural_extreme = self._structural_extreme(
                    record.signal_snapshot, direction,
                )
                tick_size = self._tick_size_provider(record.symbol.value)
                reference_price, target_price = self._frozen_prices(
                    record.signal_snapshot, direction,
                )
                existing_stop = (
                    Decimal(execution["stop_price"])
                    if execution.get("stop_price")
                    else None
                )
                plan = robot_protection.build_protection_plan(
                    payload, record.robot_state,
                    average_entry=average_entry, structural_extreme=structural_extreme,
                    tick_size=tick_size, frozen_signal_reference_price=reference_price,
                    frozen_scanner_target_price=target_price, existing_stop=existing_stop,
                )
        except Exception as error:
            self._fail_closed_unprotected_fill(
                record, error, entry_path=entry_path, entry_evidence=entry_evidence,
            )
            return False

        entry_quantity = entry_evidence.quantity
        entry_position_version = entry_evidence.position_version

        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return False

        try:
            stop_result, take_result = robot_protection.submit_initial_protection(
                self._action_executor, plan,
            )
            if (
                getattr(stop_result, "status", None) != CommandResultStatus.COMPLETED
                or getattr(take_result, "status", None) != CommandResultStatus.COMPLETED
            ):
                raise RobotBreakoutMonitorError("initial protection submission did not complete")
        except Exception as error:
            self._fail_closed_unprotected_fill(
                record, error, entry_path=entry_path, entry_evidence=entry_evidence,
            )
            return False

        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return False

        try:
            confirmed_evidence = self._prove_entry_evidence(
                record, execution, entry_path=entry_path,
            )
        except RobotBreakoutMonitorError as error:
            self._escalate_reconciliation(
                "ROBOT_ENTRY_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"reason={error}"
            )
            return False
        if confirmed_evidence != entry_evidence:
            self._escalate_reconciliation(
                "ROBOT_ENTRY_OWNERSHIP_CHANGED "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return False

        try:
            fills = tuple(
                fill
                for order_id in confirmed_evidence.order_ids
                for fill in self._store().load_executions_for_order(
                    self._account_id, order_id,
                )
            )
            if not fills or any(fill.fee < 0 for fill in fills):
                raise robot_protection.RobotProtectionError(
                    "post-fill fee evidence is unavailable"
                )
            actual_rr = robot_protection.post_fill_net_rr(
                direction,
                average_entry=average_entry,
                quantity=entry_quantity,
                entry_fee=sum((fill.fee for fill in fills), Decimal("0")),
                stop_price=plan.stop_price,
                take_price=plan.take_price,
            )
        except Exception as error:
            self._fail_closed_unprotected_fill(
                record, error, entry_path=entry_path, entry_evidence=entry_evidence,
            )
            return False

        if actual_rr < Decimal("2"):
            # A post-fill R/R shortfall is an ECONOMICS exception, not an
            # INITIAL_PROTECTION_FAILURE. Both STOP/TAKE submit receipts and the
            # current full-position protection projection must agree before a
            # below-minimum fill may remain managed as an actual Robot trade.
            # Missing/contradictory protection still takes the emergency path.
            protection = self._store().get_protection_projection(
                PositionKey(self._account_id, Category.LINEAR, record.symbol, 0),
            )
            if (protection is None
                    or protection.status != "confirmed_active"
                    or protection.pending_command_id is not None
                    or protection.evidence_at_ms < entry_evidence.first_execution_at_ms
                    or protection.stop_loss != plan.stop_price
                    or protection.take_profit != plan.take_price):
                self._fail_closed_unprotected_fill(
                    record,
                    robot_protection.RobotProtectionError(
                        "initial STOP/TAKE projection does not match submitted plan"
                    ),
                    entry_path=entry_path, entry_evidence=entry_evidence,
                )
                return False

            # No competing exit obligation/unfinished command may masquerade as
            # fully protected ownership; unresolved ambiguity keeps Admission
            # closed without issuing a second aggregate Market close.
            if any(
                obligation.symbol == record.symbol
                for obligation in self._store().load_unresolved_paper_protection_obligations(
                    self._account_id
                )
            ) or any(
                cmd.trading_account_id == self._account_id and cmd.symbol == record.symbol
                for cmd in self._store().load_unfinished_commands()
            ):
                self._escalate_reconciliation(
                    "ROBOT_POST_FILL_PROTECTED_STATE_UNPROVEN "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
                )
                return False

            # Preserve the immutable entry/fill economics and record the
            # policy violation BEFORE atomically creating the real OPEN trade.
            # The candidate cannot re-enter; its exact STOP/TAKE remain active.
            state = dict(record.robot_state)
            execution_state = dict(state.get("execution") or {})
            execution_state["post_fill_policy_exception"] = {
                "reason": "POST_FILL_NET_RR_BELOW_2",
                "actual_net_rr": str(actual_rr),
                "stop_price": str(plan.stop_price),
                "take_price": str(plan.take_price),
            }
            state["execution"] = execution_state
            try:
                record = self._store().save_robot_candidate_state(
                    record.candidate_id,
                    status=record.status,
                    robot_state=state,
                    expected_revision=record.state_revision,
                    updated_at_ms=self._now_ms(),
                )
            except Exception:
                self._escalate_reconciliation(
                    "ROBOT_POST_FILL_POLICY_EXCEPTION_NOT_DURABLE "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
                )
                return False

        now_ms = self._now_ms()
        self._store().create_robot_trade(
            trade_id=f"robot-trade-{record.candidate_id}",
            trading_account_id=self._account_id,
            candidate_id=record.candidate_id,
            symbol=record.symbol,
            direction=direction,
            pattern=str(record.signal_snapshot.get("pattern", "")),
            source_timeframe=str(
                record.signal_snapshot.get(
                    "scanner_source_timeframe",
                    record.signal_snapshot.get("timeframe", "1"),
                )
            ).strip() or "1",
            signal_time_ms=record.approved_at_ms,
            # Freeze the actual owned first fill, not the later local monitor
            # clock. Reconciliation must use the immutable execution timestamp.
            entry_time_ms=entry_evidence.first_execution_at_ms,
            entry_path=entry_path,
            actual_wv=actual_wv,
            average_entry=average_entry,
            stop_price=plan.stop_price,
            take_price=plan.take_price,
            entry_quantity=entry_quantity,
            entry_position_version=entry_position_version,
            created_at_ms=max(now_ms, entry_evidence.first_execution_at_ms),
        )
        return True

    def _active_other_owner_candidate_ids(
        self, record: RobotCandidateRecord,
    ) -> tuple[str, ...]:
        owners = active_robot_owner_candidate_ids(
            self._store(), self._account_id, record.symbol,
            excluding_candidate_id=record.candidate_id,
        )
        parent = self._linked_mirror_parent(record)
        if parent is not None and owners == (parent.candidate_id,):
            return ()
        return owners

    def _linked_mirror_parent(
        self, record: RobotCandidateRecord,
    ) -> RobotCandidateRecord | None:
        state = record.robot_state or {}
        parent_id = state.get("mirror_parent_candidate_id")
        parent_sha = state.get("mirror_parent_snapshot_sha256")
        linked_direction = str(state.get("mirror_parent_direction", "")).strip().upper()
        if not isinstance(parent_id, str) or not parent_id.strip():
            return None
        parent = self._store().get_robot_candidate(parent_id)
        if (
            parent is None
            or parent.trading_account_id != self._account_id
            or parent.symbol != record.symbol
            or parent.status != "APPROVED"
            or parent.snapshot_sha256 != parent_sha
            or parent.signal_snapshot.get("pattern") not in mirror.WEDGE_PATTERNS
            or not isinstance(parent.robot_state, Mapping)
            or str(parent.robot_state.get("direction", "")).strip().upper() != linked_direction
            or str(state.get("direction", "")).strip().upper() != linked_direction
        ):
            return None
        parent_execution = parent.robot_state.get("execution")
        if isinstance(parent_execution, Mapping):
            order_id = parent_execution.get("limit_order_id")
            if isinstance(order_id, str) and order_id.strip():
                order = self._store().get_paper_limit(order_id, self._account_id)
                if order is not None and order.status not in INACTIVE_LIMIT_STATUSES:
                    return None
            if isinstance(parent_execution.get("late_market_intent"), Mapping):
                return None
        position = self._store().get_position_projection(
            PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        )
        if (
            position is not None
            and position.side is not PositionSide.FLAT
            and position.quantity.value > 0
        ):
            return None
        owners = active_robot_owner_candidate_ids(
            self._store(), self._account_id, record.symbol,
            excluding_candidate_id=record.candidate_id,
        )
        active = [
            item for item in self._store().load_active_robot_candidate_states(self._account_id)
            if item.symbol == record.symbol and item.candidate_id != record.candidate_id
            and item.status in {"APPROVED", "OPEN"}
        ]
        return parent if not owners and [item.candidate_id for item in active] == [parent.candidate_id] else None

    def _escalate_duplicate_ownership(
        self, record: RobotCandidateRecord, owner_candidate_ids: tuple[str, ...],
    ) -> None:
        self._escalate_reconciliation(
            "DUPLICATE_ROBOT_OWNER "
            f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
            f"owner_candidate_ids={','.join(owner_candidate_ids)}"
        )

    def _escalate_reconciliation(self, reason: str) -> None:
        for _attempt in range(2):
            runtime = self._store().get_robot_runtime_state(self._account_id)
            if runtime is None:
                raise RobotBreakoutMonitorError(
                    "Robot runtime state is unavailable during safety escalation"
                )
            if (
                runtime.mode == "ROBOT_RUNNING"
                and runtime.recovery_status == "RECONCILIATION_REQUIRED"
            ):
                return
            try:
                self._store().update_robot_runtime_state(
                    self._account_id,
                    mode="ROBOT_RUNNING",
                    recovery_status="RECONCILIATION_REQUIRED",
                    reason=reason,
                    expected_version=runtime.version,
                    updated_at_ms=self._now_ms(),
                )
                return
            except ConcurrentUpdate:
                continue
        raise RobotBreakoutMonitorError(
            "Robot runtime state changed during safety escalation"
        )

    def _pre_entry_block_reason(
        self,
        record: RobotCandidateRecord,
        *,
        allowed_limit_order_id: str | None = None,
        allowed_limit_order_ids: tuple[str, ...] | None = None,
    ) -> str | None:
        quarantined = self._store().robot_symbol_quarantine_candidate_ids(
            self._account_id, record.symbol,
        )
        if quarantined:
            return (
                "ROBOT_SYMBOL_QUARANTINED "
                f"symbol={record.symbol.value} candidate_ids={','.join(quarantined)}"
            )
        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        position = self._store().get_position_projection(position_key)
        if (
            position is not None
            and (
                position.side is not PositionSide.FLAT
                or position.quantity.value != 0
            )
        ):
            return (
                "FOREIGN_POSITION_PRESENT_BEFORE_ROBOT_ENTRY "
                f"symbol={record.symbol.value}"
            )

        allowed_ids = {
            item.strip()
            for item in (allowed_limit_order_ids or ())
            if isinstance(item, str) and item.strip()
        }
        if allowed_limit_order_id is not None:
            allowed_ids.add(allowed_limit_order_id)

        foreign_orders = tuple(
            order.order_id.value
            for order in self._store().load_active_paper_limits(
                self._account_id, record.symbol,
            )
            if order.order_id.value not in allowed_ids
        )
        if foreign_orders:
            return (
                "FOREIGN_WORKING_ORDER_PRESENT_BEFORE_ROBOT_ENTRY "
                f"symbol={record.symbol.value} order_ids={','.join(foreign_orders)}"
            )
        return None

    def _entry_order_ids(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        entry_path: str,
    ) -> tuple[OrderId, ...]:
        return robot_entry_order_ids(
            self._store(), self._account_id, record, execution, entry_path=entry_path,
        )

    def _prove_entry_evidence(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        entry_path: str,
    ) -> _EntryEvidence | None:
        order_ids = self._entry_order_ids(record, execution, entry_path=entry_path)
        if not order_ids:
            return None
        owned_order_ids = {item.value for item in order_ids}

        fills = tuple(
            fill
            for order_id in order_ids
            for fill in self._store().load_executions_for_order(self._account_id, order_id)
        )
        if not fills:
            return None

        direction = str(record.robot_state.get("direction", "")).strip().upper()
        expected_side = (
            OrderSide.BUY
            if direction == robot_state_machine.DIRECTION_LONG
            else OrderSide.SELL
            if direction == robot_state_machine.DIRECTION_SHORT
            else None
        )
        if expected_side is None:
            raise RobotBreakoutMonitorError("Robot entry direction is invalid")
        if any(
            fill.symbol != record.symbol
            or fill.side is not expected_side
            or fill.quantity.value <= 0
            or fill.price.value <= 0
            for fill in fills
        ):
            raise RobotBreakoutMonitorError(
                "durable Robot entry executions do not match candidate scope/direction"
            )

        quantity = sum((fill.quantity.value for fill in fills), Decimal("0"))
        notional = sum(
            (fill.price.value * fill.quantity.value for fill in fills),
            Decimal("0"),
        )
        if quantity <= 0 or notional <= 0:
            raise RobotBreakoutMonitorError("durable Robot entry evidence is empty")
        average_entry = notional / quantity

        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        position = self._store().get_position_projection(position_key)
        expected_position_side = (
            PositionSide.LONG
            if expected_side is OrderSide.BUY
            else PositionSide.SHORT
        )
        if (
            position is None
            or position.side is not expected_position_side
            or position.quantity.value != quantity
            or position.average_entry is None
            or position.average_entry.value != average_entry
        ):
            raise RobotBreakoutMonitorError(
                "aggregate position does not equal the Robot-owned entry fills"
            )

        ordered = tuple(
            sorted(
                fills,
                key=lambda fill: (
                    fill.exchange_timestamp_ms,
                    fill.dedup_key.exec_id.value,
                ),
            )
        )
        first_at = ordered[0].exchange_timestamp_ms
        symbol_executions = self._store().load_executions_for_symbol(
            self._account_id, record.symbol,
        )
        pre_entry_net = Decimal("0")
        for item in symbol_executions:
            signed = (
                item.quantity.value
                if item.side is OrderSide.BUY
                else -item.quantity.value
            )
            if item.exchange_timestamp_ms < first_at:
                pre_entry_net += signed
                continue
            if item.order_id.value not in owned_order_ids:
                raise RobotBreakoutMonitorError(
                    "foreign execution exists after Robot entry began"
                )
        if pre_entry_net != 0:
            raise RobotBreakoutMonitorError(
                "symbol was not FLAT immediately before Robot entry"
            )
        foreign_orders = tuple(
            item.order_id.value
            for item in self._store().load_active_paper_limits(
                self._account_id, record.symbol,
            )
            if item.order_id.value not in owned_order_ids
        )
        if foreign_orders:
            raise RobotBreakoutMonitorError(
                "foreign working order exists on Robot-owned symbol"
            )

        return _EntryEvidence(
            order_ids=order_ids,
            quantity=quantity,
            average_entry=average_entry,
            position_version=position.version,
            first_execution_at_ms=first_at,
        )

    @staticmethod
    def _structural_extreme(signal_snapshot: Mapping[str, object], direction: str) -> Decimal:
        # Shared pure policy is the sole authority for frozen counted touches.
        try:
            return robot_protection.wedge_structural_extreme(signal_snapshot, direction)
        except robot_protection.RobotProtectionError as exc:
            raise RobotBreakoutMonitorError(str(exc)) from exc

    @staticmethod
    def _frozen_prices(
        signal_snapshot: Mapping[str, object], direction: str,
    ) -> tuple[Decimal, Decimal]:
        # Reuse exactly the same frozen width reference/target in SIMULATION.
        try:
            return robot_protection.wedge_frozen_reference_target(signal_snapshot, direction)
        except robot_protection.RobotProtectionError as exc:
            raise RobotBreakoutMonitorError(str(exc)) from exc

    def _build_initial_retest_limit_plan(
        self, record: RobotCandidateRecord, state: Mapping[str, object],
    ):
        payload = {
            "candidate_id": record.candidate_id,
            "status": record.status,
            "timeframe": "1",
            "signal_snapshot": record.signal_snapshot,
        }
        tick_size = self._tick_size_provider(record.symbol.value)
        return robot_entry_limit.build_initial_retest_limit(
            payload, state, tick_size=tick_size,
        )

    def _l_shape_entry_rr_skip(
        self, record: RobotCandidateRecord, plan,
    ) -> tuple[str, dict[str, object]] | None:
        threshold = robot_l_shape.MIN_REWARD_RISK
        details: dict[str, object] = {
            "entry_price": str(plan.request.limit_price),
            "min_rr": str(threshold),
        }
        try:
            terms = robot_l_shape.frozen_terms(record.signal_snapshot)
            # Same STOP the post-fill protection plan uses: frozen STOP within
            # 1.5% of the entry, else the 1.5% fallback.
            stop_price = robot_protection.limited_stop(
                terms.direction,
                entry_price=plan.request.limit_price,
                preferred_stop=robot_l_shape.preferred_stop(
                    record.signal_snapshot, terms,
                    tick_size=self._tick_size_provider(record.symbol.value),
                ),
            )
            slippage = (
                mirror.STOP_SLIPPAGE_FRACTION
                if robot_l_shape.is_mirror_snapshot(record.signal_snapshot) else Decimal("0")
            )
            rr = robot_l_shape.net_reward_risk(
                terms.direction,
                entry_price=plan.request.limit_price,
                stop_price=stop_price,
                target_price=terms.target,
                exit_slippage_fraction=slippage,
            )
        except Exception as error:
            details["error"] = str(error)
            return ENTRY_RR_SKIP_UNAVAILABLE, details
        details.update(
            stop_price=str(stop_price),
            take_price=str(terms.target),
            rr=str(rr),
        )
        if rr <= 0 or rr < threshold:
            return ENTRY_RR_SKIP_POOR_RR, details
        return None

    def _entry_rr_skip(
        self, record: RobotCandidateRecord, plan, *,
        direction: str | None = None,
    ) -> tuple[str, dict[str, object]] | None:
        """Planned take/stop ratio for the retest LIMIT, before it is placed.

        Uses the same inputs as ``robot_protection.build_protection_plan`` after
        the fill (structural extreme and frozen prices from the snapshot), with
        the LIMIT price as the entry. Returns ``(reason, details)`` when the
        candidate must be skipped, ``None`` only when RR is computable and
        meets the threshold. Existing filled positions continue through their
        independent post-fill protection and emergency-close lifecycle.
        """
        threshold = robot_protection.wedge_min_entry_rr()
        details: dict[str, object] = {
            "entry_price": str(plan.request.limit_price), "min_rr": str(threshold),
        }
        try:
            direction = direction if direction is not None else plan.direction
            structural_extreme = self._structural_extreme(record.signal_snapshot, direction)
            tick_size = self._tick_size_provider(record.symbol.value)
            reference_price, target_price = self._frozen_prices(record.signal_snapshot, direction)
            stop_price = robot_protection.structural_stop(
                direction, average_entry=plan.request.limit_price,
                structural_extreme=structural_extreme, tick_size=tick_size,
            )
            take_price = robot_protection.frozen_take_90(
                direction, frozen_signal_reference_price=reference_price,
                frozen_scanner_target_price=target_price,
            )
            rr = risk_reward_ratio(
                direction, entry_price=plan.request.limit_price,
                stop_price=stop_price, take_price=take_price,
            )
        except Exception as error:
            print(
                "[ROBOT ENTRY RR UNAVAILABLE] "
                f"candidate_id={record.candidate_id} symbol={record.symbol.value} error={error}"
            )
            details["error"] = str(error)
            return ENTRY_RR_SKIP_UNAVAILABLE, details
        details.update(stop_price=str(stop_price), take_price=str(take_price), rr=str(rr))
        if rr <= 0 or rr < threshold:
            print(
                "[ROBOT ENTRY SKIPPED] "
                f"candidate_id={record.candidate_id} symbol={record.symbol.value} "
                f"reason={ENTRY_RR_SKIP_POOR_RR} rr={rr} min_rr={threshold}"
            )
            return ENTRY_RR_SKIP_POOR_RR, details
        return None

    def _arm_entry_coverage(self, symbol: str) -> bool:
        """True only once protection coverage for ``symbol`` is listening."""
        arm = self._arm_entry_coverage_callback
        if arm is None:
            return False
        try:
            return arm(symbol) is True
        except Exception as error:
            print(f"[ROBOT ENTRY COVERAGE ARM ERROR] symbol={symbol} error={error}")
            return False

    def _release_entry_coverage(self, symbol: str) -> None:
        """Drop an arm whose resting LIMIT was proven not created."""
        release = self._release_entry_coverage_callback
        if release is None:
            return
        try:
            release(symbol)
        except Exception as error:
            print(f"[ROBOT ENTRY COVERAGE RELEASE ERROR] symbol={symbol} error={error}")

    def _confirm_entry_admission(
        self, record: RobotCandidateRecord, execution: dict[str, object] | None = None,
    ) -> RobotCandidateRecord:
        """Record that this READY epoch re-evaluated the candidate's resting ENTRY (#608).

        An ENTRY LIMIT placed before the current READY epoch (restart, start from
        STOPPED, resume) is not matched by the runtime until the monitor has run
        its admission checks in the epoch and stamped the runtime-state version
        here. Only ever written under (ROBOT_RUNNING, READY); the next transition
        changes the version and so withdraws the confirmation. Returns the freshest
        record so the caller's later writes use the new revision.
        """
        state = self._store().get_robot_runtime_state(self._account_id)
        if state is None or state.mode != "ROBOT_RUNNING" or state.recovery_status != "READY":
            return record
        fresh = self._store().get_robot_candidate(record.candidate_id)
        if fresh is None or fresh.status not in {"APPROVED", "OPEN"} or fresh.robot_state is None:
            return record
        current = dict(fresh.robot_state.get("execution") or {})
        if execution is not None:
            execution["entry_admission_version"] = state.version
        if current.get("entry_admission_version") == state.version:
            return fresh
        current["entry_admission_version"] = state.version
        new_state = dict(fresh.robot_state)
        new_state["execution"] = current
        try:
            return self._store().save_robot_candidate_state(
                fresh.candidate_id,
                status=fresh.status,
                robot_state=new_state,
                expected_revision=fresh.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            return record

    def _read_admission_gate(self) -> tuple[bool, bool]:
        state = self._store().get_robot_runtime_state(self._account_id)
        if state is None:
            return False, False
        new_entry_admitted = (
            state.mode == "ROBOT_RUNNING" and state.recovery_status == "READY"
        )
        terminal_stop = state.mode == "ROBOT_STOPPED"
        return new_entry_admitted, terminal_stop

    def _invalidate_pre_entry_candidate(
        self, record: RobotCandidateRecord, *, reason: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        execution = dict(record.robot_state.get("execution") or {})
        execution["stopped_without_entry_at_ms"] = self._now_ms()
        execution["stopped_without_entry_reason"] = reason
        if details:
            execution["entry_rr_filter"] = dict(details)
        new_state = dict(record.robot_state)
        new_state["execution"] = execution
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="INVALIDATED",
                robot_state=new_state,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            pass

    def _quarantine_unstarted_frozen_fault(
        self, record: RobotCandidateRecord, error: robot_state_machine.RobotStateMachineError,
    ) -> bool:
        """Contain one malformed immutable PAPER signal before any execution.

        This is a narrow candidate-scope exception to repeated error retries,
        not a blanket replacement of account protection. Do not infer an inert
        candidate from APPROVED/FLAT alone: reuse canonical recovery proof and
        additionally reject historical fills or an unsynced projection.
        Any unproven ownership stays account-fenced; no STOP/TAKE is touched.
        """
        store = self._store()
        try:
            fresh = store.get_robot_candidate(record.candidate_id)
            if (
                fresh is None or fresh.status != "APPROVED"
                or fresh.robot_state is not None
                or fresh.candidate_id != record.candidate_id
                or fresh.trading_account_id != self._account_id
                or fresh.symbol != record.symbol
                or fresh.snapshot_sha256 != record.snapshot_sha256
                or fresh.state_revision != record.state_revision
            ):
                # Changed since the failing read: do not invalidate a newer
                # state or assume the original immutable fault still applies.
                return False
            position = store.get_position_projection(PositionKey(
                self._account_id, Category.LINEAR, fresh.symbol, 0,
            ))
            inert = (
                self._paper_candidate_is_inert(fresh)
                and not store.load_executions_for_symbol(
                    self._account_id, fresh.symbol,
                )
                and (position is None or (
                    position.side is PositionSide.FLAT
                    and position.quantity.value == 0
                    and position.sync_state == "synced"
                ))
            )
        except Exception:
            # Failed reads cannot establish a local-scope safety proof.
            inert = False
        if not inert:
            self._escalate_reconciliation(
                "ROBOT_FROZEN_INIT_OWNERSHIP_UNPROVEN "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return False
        now_ms = self._now_ms()
        state = {
            "state_version": robot_state_machine.STATE_VERSION,
            "phase": "INVALIDATED_FROZEN_INIT",
            "pattern": fresh.signal_snapshot.get("pattern"),
            "paper_quarantine": {
                "reason": "FROZEN_INIT_INVALID",
                "error_type": type(error).__name__,
                "at_ms": now_ms,
            },
        }
        try:
            store.save_robot_candidate_state(
                fresh.candidate_id, status="INVALIDATED", robot_state=state,
                expected_revision=fresh.state_revision, updated_at_ms=now_ms,
            )
        except ConcurrentUpdate:
            # A competing owner changed the row; the next normal tick
            # re-reads authority. No quarantining stale revisions.
            return False
        return True

    def _invalidate_unsupported_pattern(
        self, record: RobotCandidateRecord, error: Exception,
    ) -> None:
        # An APPROVED candidate without robot_state would otherwise fail every
        # tick and block restart reconciliation; it never had an order.
        now_ms = self._now_ms()
        state = {
            "state_version": robot_state_machine.STATE_VERSION,
            "phase": PHASE_INVALIDATED_UNSUPPORTED_PATTERN,
            "pattern": (record.signal_snapshot or {}).get("pattern"),
            "invalidated_reason": str(error),
            "invalidated_at_ms": now_ms,
        }
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="INVALIDATED",
                robot_state=state,
                expected_revision=record.state_revision,
                updated_at_ms=now_ms,
            )
        except ConcurrentUpdate:
            return
        print(
            "[ROBOT CANDIDATE INVALIDATED] "
            f"candidate_id={record.candidate_id} reason={error}"
        )

    def _fail_closed_box_unprotected_fill(
        self,
        record: RobotCandidateRecord,
        source: RobotCandidateRecord,
        proof,
        error: Exception,
    ) -> None:
        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return
        if proof.remaining_quantity <= 0:
            return
        close = self._emergency_close_path
        owner_path = self._get_market_book is None and close is not None
        get_book = close.get_market_book if owner_path else self._get_market_book
        preflight_close = close.market_preflight if owner_path else self._market_preflight
        submit_close = close.submit_market if owner_path else self._submit_market
        if get_book is None or preflight_close is None or submit_close is None:
            self._escalate_reconciliation(
                "ROBOT_BOX_PROTECTION_FAILURE_NO_CLOSE_PATH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return

        if self._incident_dir is not None:
            snapshot = record.signal_snapshot if isinstance(record.signal_snapshot, Mapping) else {}
            record_robot_incident(
                incident_type="ROBOT_PROTECTION_EMERGENCY_CLOSE",
                stage="initial_protection",
                reason_code="INITIAL_PROTECTION_FAILURE",
                symbol=record.symbol.value,
                timeframe=snapshot.get("timeframe"),
                pattern=snapshot.get("pattern"),
                candidate_id=record.candidate_id,
                error=error,
                facts={
                    "stop_proven": False,
                    "take_proven": False,
                    "market_data_authoritative": True,
                    "intended_stop_crossed": None,
                    "deadline_at_ms": None,
                    "age_ms": None,
                },
                selected_recovery_action="EMERGENCY_CLOSE",
                incident_dir=self._incident_dir,
                timestamp_ms=self._now_ms(),
            )

        execution = dict(record.robot_state.get("execution") or {})
        raw_intent = execution.get("box_emergency_close_intent")
        if isinstance(raw_intent, Mapping):
            plan = restore_box_market_plan(raw_intent)
            if plan.slot != 0 or plan.quantity != proof.remaining_quantity:
                self._escalate_reconciliation(
                    "ROBOT_BOX_EMERGENCY_CLOSE_INTENT_CONFLICT "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
                )
                return
        else:
            book = get_book(record.symbol.value)
            if book is None:
                if owner_path:
                    # In-place close has no evidence; keep the durable fence.
                    self._escalate_reconciliation(
                        "ROBOT_BOX_PROTECTION_FAILURE_NO_CLOSE_PATH "
                        f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                        "reason=no_fresh_book"
                    )
                return
            plan = build_box_emergency_close_market_plan(
                source, book, quantity=proof.remaining_quantity,
            )
            preflight = preflight_close(plan.request, plan.identity)
            if (
                not getattr(preflight, "admitted", False)
                or getattr(preflight, "normalized_quantity", None) != plan.quantity
            ):
                self._escalate_reconciliation(
                    "ROBOT_BOX_EMERGENCY_CLOSE_PREFLIGHT_FAILED "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
                )
                return
            execution["box_emergency_close_intent"] = durable_box_market_intent(plan)
            execution["protection_failure"] = type(error).__name__
            fresh = self._store().get_robot_candidate(record.candidate_id)
            if fresh is not None and fresh.status in {"APPROVED", "OPEN"}:
                state = dict(fresh.robot_state or {})
                state["execution"] = dict(execution)
                try:
                    self._store().save_robot_candidate_state(
                        fresh.candidate_id,
                        status=fresh.status,
                        robot_state=state,
                        expected_revision=fresh.state_revision,
                        updated_at_ms=self._now_ms(),
                    )
                except ConcurrentUpdate:
                    return

        try:
            self._store().reserve_box_order_identity(
                source.candidate_id,
                order_id=plan.order_id,
                role="EXIT",
                slot=0,
            )
        except Exception:
            self._escalate_reconciliation(
                "ROBOT_BOX_EMERGENCY_CLOSE_OWNERSHIP_FAILED "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return

        now_ms = self._now_ms()
        for owner in self._store().load_box_order_ownership(source.candidate_id):
            if owner.order_id == plan.order_id:
                continue
            limit = self._store().get_paper_limit(owner.order_id.value, self._account_id)
            if limit is None or limit.status in INACTIVE_LIMIT_STATUSES:
                continue
            digest = hashlib.sha256(
                f"{source.candidate_id}\0protection-failure-cancel\0{owner.order_id.value}".encode("utf-8")
            ).hexdigest()[:32]
            self._store().cancel_paper_limit(
                client_action_id=f"box-emergency-cancel-{digest}",
                request_fingerprint=hashlib.sha256(
                    f"{record.symbol.value}\0{owner.order_id.value}".encode("utf-8")
                ).hexdigest(),
                order_id=owner.order_id,
                trading_account_id=self._account_id,
                updated_at_ms=now_ms,
            )

        result = submit_close(plan.request, plan.identity)
        if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
            self._escalate_reconciliation(
                "ROBOT_BOX_EMERGENCY_CLOSE_PENDING "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return

        try:
            closed_proof = self._store().prove_box_owned_position(source.candidate_id)
        except Exception:
            self._escalate_reconciliation(
                "ROBOT_BOX_EMERGENCY_CLOSE_UNPROVEN "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return
        if closed_proof.remaining_quantity != 0:
            self._escalate_reconciliation(
                "ROBOT_BOX_EMERGENCY_CLOSE_NOT_FLAT "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return

        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        self._store().clear_paper_protection_for_flat(position_key)
        trade = self._store().get_open_robot_trade_for_symbol(
            self._account_id, record.symbol,
        )
        if trade is not None and trade.candidate_id == record.candidate_id:
            if (
                closed_proof.average_exit is None
                or closed_proof.last_execution_at_ms is None
                or closed_proof.entry_notional <= 0
            ):
                self._escalate_reconciliation(
                    "ROBOT_BOX_EMERGENCY_CLOSE_ECONOMICS_UNPROVEN "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
                )
                return
            realized_pct = (
                (closed_proof.realized_pnl - closed_proof.accumulated_fee)
                / closed_proof.entry_notional
                * Decimal("100")
            )
            self._store().close_robot_trade(
                trade.trade_id,
                exit_time_ms=closed_proof.last_execution_at_ms,
                exit_price=closed_proof.average_exit,
                exit_reason="EMERGENCY_PROTECTION_FAILURE",
                realized_pnl_usdt=closed_proof.realized_pnl,
                realized_pnl_pct=realized_pct,
                fees_costs_usdt=closed_proof.accumulated_fee,
                updated_at_ms=self._now_ms(),
            )
        else:
            fresh = self._store().get_robot_candidate(record.candidate_id)
            if fresh is not None and fresh.status == "APPROVED":
                state = dict(fresh.robot_state)
                state["execution"] = execution
                self._store().save_robot_candidate_state(
                    fresh.candidate_id,
                    status="INVALIDATED",
                    robot_state=state,
                    expected_revision=fresh.state_revision,
                    updated_at_ms=self._now_ms(),
                )
        self._release_entry_coverage(record.symbol.value)

    def _recover_take_closed_legacy_postfill(
        self, record, state, execution, command, position,
    ) -> bool:
        """Recover only an exact, already-FLAT internal PAPER TAKE, atomically.

        The account must have one immutable Market entry and one matching
        internally generated TAKE exit; no replacement command is dispatched.
        """
        store = self._store()
        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        if (position.side is not PositionSide.FLAT
                or position.quantity.value != 0 or position.version != 2
                or store.get_protection_projection(position_key) is not None):
            return False
        rows = store.load_executions_for_symbol(self._account_id, record.symbol)
        if len(rows) != 2:
            return False
        entry, exit_fill = rows
        owned = store.load_executions_for_order(
            self._account_id, command.exchange_order_id,
        )
        direction = str(state.get("direction", "")).strip().upper()
        expected_entry = OrderSide.SELL if direction == "SHORT" else OrderSide.BUY
        expected_exit = OrderSide.BUY if direction == "SHORT" else OrderSide.SELL
        suffix = exit_fill.order_id.value.removeprefix("paper-take-order-")
        intent = execution["late_market_intent"]
        if not (
            len(owned) == 1 and owned[0] == entry
            and entry.order_id == command.exchange_order_id
            and entry.side is expected_entry and exit_fill.side is expected_exit
            and entry.symbol == exit_fill.symbol == record.symbol
            and entry.dedup_key.trading_account_id == self._account_id
            and exit_fill.dedup_key.trading_account_id == self._account_id
            and entry.dedup_key.category is Category.LINEAR
            and exit_fill.dedup_key.category is Category.LINEAR
            and entry.quantity.value > 0
            and entry.quantity.value == exit_fill.quantity.value
            and entry.quantity.value == Decimal(str(intent.get("normalized_quantity")))
            and entry.price.value > 0 and exit_fill.price.value > 0
            and entry.fee >= 0 and exit_fill.fee >= 0
            and record.approved_at_ms <= entry.exchange_timestamp_ms
                < exit_fill.exchange_timestamp_ms
            and position.updated_at_ms == exit_fill.exchange_timestamp_ms
            and exit_fill.order_id.value == "paper-take-order-" + suffix
            and len(suffix) == 64
            and all(c in "0123456789abcdef" for c in suffix)
            and exit_fill.dedup_key.exec_id.value == "paper-take-exec-" + suffix
        ):
            return False
        # Before this helper the common path has already attested the unique
        # APPROVED candidate, original command and absence of foreign commands,
        # working limits, unresolved obligations or competing Robot ownership.
        structural = self._structural_extreme(record.signal_snapshot, direction)
        reference, target = self._frozen_prices(record.signal_snapshot, direction)
        tick = self._tick_size_provider(record.symbol.value)
        plan = robot_protection.build_protection_plan(
            self._candidate_payload(record), state,
            average_entry=entry.price.value, structural_extreme=structural,
            tick_size=tick, frozen_signal_reference_price=reference,
            frozen_scanner_target_price=target, existing_stop=None,
        )
        actual_rr = robot_protection.post_fill_net_rr(
            direction, average_entry=entry.price.value,
            quantity=entry.quantity.value, entry_fee=entry.fee,
            stop_price=plan.stop_price, take_price=plan.take_price,
        )
        try:
            persisted_rr = Decimal(execution["protection_failure"].split(" rr=", 1)[1])
        except (KeyError, TypeError, ValueError, IndexError):
            return False
        if not (persisted_rr.is_finite() and persisted_rr == actual_rr
                and Decimal("0") < actual_rr < Decimal("2")):
            return False
        qty = entry.quantity.value
        gross = qty * (
            entry.price.value - exit_fill.price.value if direction == "SHORT"
            else exit_fill.price.value - entry.price.value
        )
        fees = entry.fee + exit_fill.fee
        pct = (gross - fees) / (qty * entry.price.value) * 100
        now = max(self._now_ms(), record.updated_at_ms, exit_fill.exchange_timestamp_ms)
        next_state = dict(state)
        next_exec = dict(execution)
        next_exec.pop("emergency_close_pending", None)
        next_exec.pop("emergency_close_intent", None)
        next_exec["protected_postfill_recovery"] = {
            "proof": "SINGLE_MARKET_FILL_INTERNAL_TAKE_FLAT_V1",
            "entry_command_id": command.command_id.value,
            "entry_execution_id": entry.dedup_key.exec_id.value,
            "take_execution_id": exit_fill.dedup_key.exec_id.value,
            "take_order_id": exit_fill.order_id.value,
            "position_version": position.version,
            "reconciled_at_ms": now,
        }
        next_exec["post_fill_policy_exception"] = {
            "reason": "POST_FILL_NET_RR_BELOW_2", "actual_net_rr": str(actual_rr),
            "stop_price": str(plan.stop_price), "take_price": str(plan.take_price),
        }
        next_state["execution"] = next_exec
        store.create_robot_trade(
            trade_id="robot-trade-" + record.candidate_id,
            trading_account_id=self._account_id, candidate_id=record.candidate_id,
            symbol=record.symbol, direction=direction,
            pattern=str(record.signal_snapshot.get("pattern", "")),
            source_timeframe=str(record.signal_snapshot.get(
                "scanner_source_timeframe",
                record.signal_snapshot.get("timeframe", "1"),
            )).strip() or "1",
            signal_time_ms=record.approved_at_ms,
            entry_time_ms=entry.exchange_timestamp_ms, entry_path="MARKET",
            actual_wv=Decimal("1"), average_entry=entry.price.value,
            stop_price=plan.stop_price, take_price=plan.take_price,
            entry_quantity=qty, entry_position_version=1,
            created_at_ms=now, recovery_state=next_state,
            recovery_expected_revision=record.state_revision,
            recovery_closed_take=(
                exit_fill.exchange_timestamp_ms, exit_fill.price.value,
                gross, pct, fees,
            ),
        )
        return True

    def recover_protected_legacy_postfill(self, record: RobotCandidateRecord) -> bool:
        """Repair ONLY an exact, protected PAPER post-fill low-R/R orphan.

        Called on the serialized PAPER owner while REQUIRED still holds;
        never submits STOP/TAKE/Market, changes admission, or infers FLAT.
        The legacy emergency marker predates a durable close identity, so the
        *entire* symbol command/fill lineage since approval must prove only
        the original filled Market entry. Unknown evidence stays quarantined.
        """
        store = self._store()
        runtime = store.get_robot_runtime_state(self._account_id)
        scanner = store.get_scanner_runtime_state(self._account_id)
        autopilot = store.get_robot_autopilot_state(self._account_id)
        if not (
            self._account_id.value == "paper"
            and runtime is not None
            and (runtime.mode, runtime.recovery_status) == ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")
            and scanner is not None and scanner.mode == "SCANNER_STOPPED"
            and autopilot is not None and autopilot.mode == "OFF"
            and record.status == "APPROVED"
            and record.signal_snapshot.get("pattern") in ("Rising Wedge", "Falling Wedge")
            and type(record.approved_at_ms) is int and record.approved_at_ms > 0
        ):
            return False
        state = record.robot_state or {}
        execution = state.get("execution")
        if not isinstance(execution, Mapping):
            return False
        failure = execution.get("protection_failure")
        attempted = execution.get("emergency_close_attempted_at_ms")
        if not (
            state.get("phase") == "RETEST_DETECTED"
            and execution.get("entry_mode") == LATE_ADMISSION_MARKET
            and execution.get("emergency_close_pending") is True
            and execution.get("emergency_close_intent") is None
            and execution.get("emergency_close_outcome") is None
            and "emergency_closed_at_ms" not in execution
            and "post_fill_policy_exception" not in execution
            and isinstance(failure, str)
            and failure.startswith("POST_FILL_NET_RR_BELOW_2 rr=")
            and type(attempted) is int and attempted > record.approved_at_ms
            and isinstance(execution.get("late_market_intent"), Mapping)
        ):
            return False

        # Restore validates the original candidate-domain identity rather than
        # trusting a syntactically plausible command ID in candidate JSON.
        plan = restore_late_admission_market_plan(execution["late_market_intent"])
        direction = state.get("direction")
        expected_side = (
            OrderSide.SELL if direction == "SHORT" else
            OrderSide.BUY if direction == "LONG" else None
        )
        if (plan.candidate_id != record.candidate_id
                or plan.request.symbol != record.symbol.value
                or plan.direction != direction
                or expected_side is None
                or plan.request.side is not expected_side):
            return False
        command = store.get_command(plan.identity.command_id)
        if not (
            command is not None
            and command.trading_account_id == self._account_id
            and command.symbol == record.symbol
            and command.category is Category.LINEAR and command.position_idx == 0
            and command.command_kind == "create_market"
            and command.current_state.value == "filled"
            and command.side is expected_side
            and command.exchange_order_id is not None
            and command.order_link_id == plan.identity.order_link_id
            and record.approved_at_ms <= command.created_at_ms
            and command.updated_at_ms <= attempted
        ):
            return False

        # Zero unfinished commands is not enough: a previously executed
        # emergency close would be terminal in that query. Require the one
        # exact entry command, and no other commands since candidate approval.
        commands = store.load_commands_for_symbol_since(
            self._account_id, record.symbol, record.approved_at_ms,
        )
        if len(commands) != 1 or commands[0].command_id != command.command_id:
            return False
        if (store.load_active_robot_entry_orders(self._account_id, record.symbol)
                or store.load_active_paper_limits(self._account_id, record.symbol)
                or any(item.trading_account_id == self._account_id
                       and item.symbol == record.symbol
                       for item in store.load_unfinished_commands())
                or any(item.symbol == record.symbol
                       for item in store.load_unresolved_paper_protection_obligations(
                           self._account_id
                       ))
                or any(trade.symbol == record.symbol
                       for trade in store.load_open_robot_trades(self._account_id))
                or store.get_robot_trade("robot-trade-" + record.candidate_id) is not None):
            return False
        active = store.load_active_robot_candidates_for_symbol(
            self._account_id, record.symbol,
        )
        if len(active) != 1 or active[0].candidate_id != record.candidate_id:
            return False

        # A legacy internal TAKE can already have made the symbol FLAT.
        # Do not try the OPEN-only entry-position attestation in that case.
        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        position = store.get_position_projection(position_key)
        if position is not None and position.side is PositionSide.FLAT:
            return self._recover_take_closed_legacy_postfill(
                record, state, execution, command, position,
            )

        entry = self._prove_entry_evidence(record, execution, entry_path="MARKET")
        if (entry is None
                or len(entry.order_ids) != 1
                or entry.order_ids[0] != command.exchange_order_id
                or entry.first_execution_at_ms > attempted
                or entry.quantity != Decimal(str(
                    execution["late_market_intent"].get("normalized_quantity")
                ))):
            return False
        fills = store.load_executions_for_order(
            self._account_id, command.exchange_order_id,
        )
        if (len(fills) != 1 or fills[0].symbol != record.symbol
                or fills[0].side is not expected_side
                or fills[0].fee < 0):
            return False
        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        protection = store.get_protection_projection(position_key)
        if not (
            protection is not None
            and protection.status == "confirmed_active"
            and protection.pending_command_id is None
            and protection.trailing_stop is None
            and protection.evidence_at_ms >= entry.first_execution_at_ms
            and protection.stop_loss is not None
            and protection.take_profit is not None
        ):
            return False

        # Reconstruct exactly the normal filled-Wedge protection from the
        # immutable snapshot and the actual fill; never accept an unrelated
        # manually attached STOP/TAKE merely because both fields are present.
        structural = self._structural_extreme(record.signal_snapshot, direction)
        reference, target = self._frozen_prices(record.signal_snapshot, direction)
        tick_size = self._tick_size_provider(record.symbol.value)
        expected = robot_protection.build_protection_plan(
            self._candidate_payload(record), state,
            average_entry=entry.average_entry, structural_extreme=structural,
            tick_size=tick_size, frozen_signal_reference_price=reference,
            frozen_scanner_target_price=target, existing_stop=None,
        )
        from terminal.application.normalization import normalize_limit_price
        closing_side = OrderSide.BUY if direction == "SHORT" else OrderSide.SELL
        stop = normalize_limit_price(expected.stop_price, tick_size, closing_side)
        take = normalize_limit_price(expected.take_price, tick_size, closing_side)
        if protection.stop_loss != stop or protection.take_profit != take:
            return False
        actual_rr = robot_protection.post_fill_net_rr(
            direction, average_entry=entry.average_entry, quantity=entry.quantity,
            entry_fee=fills[0].fee, stop_price=expected.stop_price,
            take_price=expected.take_price,
        )
        persisted_rr = Decimal(failure.split(" rr=", 1)[1])
        if not (persisted_rr.is_finite() and persisted_rr == actual_rr
                and Decimal("0") < actual_rr < Decimal("2")):
            return False

        now = max(self._now_ms(), record.updated_at_ms)
        recovered = dict(state)
        updated = dict(execution)
        updated.pop("emergency_close_pending", None)
        updated["post_fill_policy_exception"] = {
            "reason": "POST_FILL_NET_RR_BELOW_2",
            "actual_net_rr": str(actual_rr),
            "stop_price": str(expected.stop_price),
            "take_price": str(expected.take_price),
        }
        updated["protected_postfill_recovery"] = {
            "proof": "SINGLE_MARKET_FILL_NO_EXIT_COMMAND_PROTECTED_V1",
            "entry_command_id": command.command_id.value,
            "entry_order_id": command.exchange_order_id.value,
            "entry_execution_id": fills[0].dedup_key.exec_id.value,
            "position_version": entry.position_version,
            "protection_version": protection.version,
            "reconciled_at_ms": now,
        }
        recovered["execution"] = updated
        # One transaction inserts the actual OPEN trade and CAS-clears the
        # legacy pending marker. Any failure rolls both writes back.
        store.create_robot_trade(
            trade_id="robot-trade-" + record.candidate_id,
            trading_account_id=self._account_id,
            candidate_id=record.candidate_id,
            symbol=record.symbol, direction=direction,
            pattern=str(record.signal_snapshot.get("pattern", "")),
            source_timeframe=str(record.signal_snapshot.get(
                "scanner_source_timeframe",
                record.signal_snapshot.get("timeframe", "1"),
            )).strip() or "1",
            signal_time_ms=record.approved_at_ms,
            entry_time_ms=entry.first_execution_at_ms, entry_path="MARKET",
            actual_wv=Decimal("1"), average_entry=entry.average_entry,
            stop_price=expected.stop_price, take_price=expected.take_price,
            entry_quantity=entry.quantity, entry_position_version=entry.position_version,
            created_at_ms=max(now, entry.first_execution_at_ms),
            recovery_state=recovered, recovery_expected_revision=record.state_revision,
        )
        return True

    def _hold_unproven_emergency_close(
        self, record: RobotCandidateRecord, execution: Mapping[str, object],
    ) -> bool:
        """Never redispatch an uncorrelated aggregate close after an uncertain result.

        The current PAPER full_close client action id is NOT a durable Market
        command identity. A retry could close a replacement position.
        """
        if not (
            execution.get("emergency_close_pending")
            or execution.get("emergency_close_intent")
        ):
            return False
        self._escalate_reconciliation(
            "ROBOT_EMERGENCY_CLOSE_OUTCOME_UNPROVEN "
            f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
        )
        return True

    def _fail_closed_unprotected_fill(
        self, record: RobotCandidateRecord, error: Exception, *,
        entry_path: str, entry_evidence: _EntryEvidence,
    ) -> None:
        """Persist exact post-fill recovery intent BEFORE any irreversible close.

        The action id alone does not deduplicate PAPER full_close. A crash or
        unknown response must not send the aggregate close a second time.
        """
        execution = dict(record.robot_state.get("execution") or {})
        if self._hold_unproven_emergency_close(record, execution):
            return

        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return

        try:
            confirmed = self._prove_entry_evidence(
                record, execution, entry_path=entry_path,
            )
            if confirmed is None or confirmed != entry_evidence:
                raise RobotBreakoutMonitorError("entry evidence changed before emergency intent")
            fills = tuple(
                fill
                for order_id in confirmed.order_ids
                for fill in self._store().load_executions_for_order(
                    self._account_id, order_id,
                )
            )
            execution_ids = tuple(sorted(fill.dedup_key.exec_id.value for fill in fills))
            if not execution_ids or len(execution_ids) != len(set(execution_ids)):
                raise RobotBreakoutMonitorError("emergency entry executions are ambiguous")
            if any(
                item.symbol == record.symbol
                for item in self._store().load_unresolved_paper_protection_obligations(
                    self._account_id,
                )
            ):
                raise RobotBreakoutMonitorError(
                    "existing protection obligation could race emergency close"
                )
        except Exception as proof_error:
            self._escalate_reconciliation(
                "ROBOT_EMERGENCY_CLOSE_ENTRY_UNPROVEN "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"error={type(proof_error).__name__}"
            )
            return

        request = robot_protection.emergency_close_request(
            record.candidate_id, record.symbol.value,
        )
        identity = robot_emergency_close_identity(
            request.client_action_id.value, record.symbol.value,
        )
        now_ms = self._now_ms()
        execution["protection_failure"] = str(error)
        execution["emergency_close_pending"] = True
        execution["emergency_close_attempted_at_ms"] = now_ms
        execution["emergency_close_intent"] = {
            "candidate_id": record.candidate_id,
            "account_id": self._account_id.value,
            "symbol": record.symbol.value,
            "direction": str(record.robot_state["direction"]),
            "entry_path": entry_path,
            "entry_order_ids": [item.value for item in confirmed.order_ids],
            "entry_execution_ids": list(execution_ids),
            "entry_quantity": str(confirmed.quantity),
            "average_entry": str(confirmed.average_entry),
            "entry_position_version": confirmed.position_version,
            "client_action_id": request.client_action_id.value,
            "command_id": identity.command_id.value,
            "order_link_id": identity.order_link_id,
            # A committed intent is considered possibly dispatched, even if
            # the process dies immediately after this transaction.
            "dispatch_outcome": "UNKNOWN",
        }
        durable_state = dict(record.robot_state)
        durable_state["execution"] = execution
        try:
            prepared = self._store().save_robot_candidate_state(
                record.candidate_id,
                status=record.status,
                robot_state=durable_state,
                expected_revision=record.state_revision,
                updated_at_ms=now_ms,
            )
        except Exception as persist_error:
            self._escalate_reconciliation(
                "ROBOT_EMERGENCY_CLOSE_INTENT_NOT_DURABLE "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"error={type(persist_error).__name__}"
            )
            return

        if self._incident_dir is not None:
            try:
                snapshot = (
                    record.signal_snapshot
                    if isinstance(record.signal_snapshot, Mapping) else {}
                )
                record_robot_incident(
                    incident_type="ROBOT_PROTECTION_EMERGENCY_CLOSE",
                    stage="initial_protection",
                    reason_code="INITIAL_PROTECTION_FAILURE",
                    symbol=record.symbol.value,
                    timeframe=snapshot.get("timeframe"),
                    pattern=snapshot.get("pattern"),
                    candidate_id=record.candidate_id,
                    error=error,
                    facts={
                        "stop_proven": False,
                        "take_proven": False,
                        "market_data_authoritative": None,
                        "intended_stop_crossed": None,
                        "deadline_at_ms": None,
                        "age_ms": None,
                    },
                    selected_recovery_action="EMERGENCY_CLOSE",
                    incident_dir=self._incident_dir,
                    timestamp_ms=now_ms,
                )
            except Exception:
                # Incident telemetry cannot revoke an already durable intent.
                pass

        try:
            result = self._action_executor.full_close(request)
        except Exception:
            self._escalate_reconciliation(
                "ROBOT_EMERGENCY_CLOSE_OUTCOME_UNPROVEN "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return

        completed = getattr(result, "status", None) == CommandResultStatus.COMPLETED
        authoritative_flat = False
        if completed:
            position_key = PositionKey(
                self._account_id, Category.LINEAR, record.symbol, 0,
            )
            projection = self._store().get_position_projection(position_key)
            authoritative_flat = (
                projection is not None
                and projection.side is PositionSide.FLAT
                and projection.quantity.value == 0
            )

        if not (completed and authoritative_flat):
            self._escalate_reconciliation(
                "ROBOT_EMERGENCY_CLOSE_OUTCOME_UNPROVEN "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return

        # Same-call COMPLETED and authoritative FLAT: retire the candidate.
        # Retain the durable dispatch intent as historical evidence.
        execution.pop("emergency_close_pending", None)
        execution["emergency_close_outcome"] = robot_protection.RECOVERY_CLOSED
        execution["emergency_closed_at_ms"] = self._now_ms()
        new_state = dict(prepared.robot_state)
        new_state["execution"] = execution
        try:
            self._store().save_robot_candidate_state(
                prepared.candidate_id,
                status="INVALIDATED",
                robot_state=new_state,
                expected_revision=prepared.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except Exception:
            self._escalate_reconciliation(
                "ROBOT_EMERGENCY_CLOSE_TERMINAL_NOT_DURABLE "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )

    def _persist_l_shape_invalidation(
        self,
        record: RobotCandidateRecord,
        state: Mapping[str, object],
        *,
        reason: str,
    ) -> None:
        invalidated = dict(state)
        invalidated["invalidated_reason"] = reason
        invalidated["invalidated_at_ms"] = self._now_ms()
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="INVALIDATED",
                robot_state=invalidated,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            pass

    # --- MIRROR RETEST overlay (mirror_retest_robot) -------------------------------------------------

    def _save_execution_keep_status(
        self, record: RobotCandidateRecord, execution: Mapping[str, object],
    ) -> bool:
        """Persist only ``execution["mirror"]`` on the freshest revision; status and every other key stay."""
        fresh = self._store().get_robot_candidate(record.candidate_id)
        if fresh is None or fresh.status not in {"APPROVED", "OPEN"}:
            return False
        state = dict(fresh.robot_state or {})
        merged = dict(state.get("execution") or {})
        merged["mirror"] = execution["mirror"]
        state["execution"] = merged
        try:
            self._store().save_robot_candidate_state(
                fresh.candidate_id,
                status=fresh.status,
                robot_state=state,
                expected_revision=fresh.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            return False
        return True

    def _mirror_prior_attempts(self, record, campaign, siblings) -> list[dict[str, object]]:
        """Earlier ATTACHED attempts (Box overlay or standalone) of the same campaign, for its one R0 budget."""
        prior: list[dict[str, object]] = []
        if campaign is None:
            return prior
        for item in siblings:
            other = mirror.mirror_record((item.robot_state or {}).get("execution"))
            if (
                item.candidate_id == record.candidate_id
                or other is None
                or other.get("decision") != mirror.ATTACHED
                or other.get("campaign_id") != campaign["campaign_id"]
            ):
                continue
            closed = item.status not in {"APPROVED", "OPEN"}
            net = None
            if closed:
                trade = self._store().get_robot_trade(f"robot-trade-{item.candidate_id}")
                if trade is None:
                    net = Decimal("0")       # ended before any fill
                elif trade.realized_pnl_usdt is not None and trade.fees_costs_usdt is not None:
                    net = trade.realized_pnl_usdt - trade.fees_costs_usdt
            prior.append({"mirror": other, "closed": closed, "net_pnl_usdt": net})
        return prior

    def _mirror_standalone_attachment(self, record: RobotCandidateRecord, plan) -> dict[str, object]:
        """Durable decision for a standalone MIRROR entry, except transient failures (retry without orders)."""
        now_ms = self._now_ms()
        try:
            policy = self._mirror_policy
            if policy is None:
                return {"strategy_id": mirror.STRATEGY_ID, "decision": mirror.BLOCKED,
                        "reason": "mirror_robot_policy_off", "decided_at_ms": now_ms}
            terms = robot_l_shape.frozen_terms(record.signal_snapshot)
            entry = record.signal_snapshot["mirror_entry"]
            sources = [
                item for item in mirror.scanner_level_sources(record.symbol.value, root=policy.scanner_root)
                if item["level_id"] == entry.get("level_id") and item["timeframe"] == entry.get("level_timeframe")
            ]
            siblings = self._store().load_robot_candidates_for_symbol(self._account_id, record.symbol)
            campaign = None
            if sources:
                campaign = mirror.find_active_campaign(
                    policy,
                    [item for item in siblings
                     if (item.signal_snapshot or {}).get("pattern") in mirror.WEDGE_PATTERNS],
                    symbol=record.symbol.value, direction=terms.direction, now_ms=now_ms,
                    scanner_sources=sources, breakout_close_ms=sources[0]["breakout_close_ms"],
                )
            preferred_stop = robot_l_shape.preferred_stop(
                record.signal_snapshot, terms,
                tick_size=self._tick_size_provider(record.symbol.value),
            )
            # Standalone MIRROR's owner rule is STOP BEYOND the original
            # formation. Do not silently move that STOP inside the formation
            # via the generic 1.5% fallback; reject this proposed trade instead.
            if not robot_protection.stop_within_limit(
                terms.direction, entry_price=plan.request.limit_price,
                stop_price=preferred_stop,
            ):
                return {"strategy_id": mirror.STRATEGY_ID, "decision": mirror.BLOCKED,
                        "mode": "STANDALONE",
                        "reason": "mirror_formation_stop_exceeds_1p5_percent_or_invalid",
                        "decided_at_ms": now_ms}
            stop_price = preferred_stop
            return mirror.plan_standalone_attachment(
                policy, direction=terms.direction, entry_price=plan.request.limit_price,
                stop_price=stop_price, target_price=terms.target, campaign=campaign,
                prior_attempts=self._mirror_prior_attempts(record, campaign, siblings), now_ms=now_ms,
            )
        except Exception as error:
            return {
                "strategy_id": mirror.STRATEGY_ID,
                "decision": mirror.DEFERRED,
                "reason": f"mirror_error:{type(error).__name__}",
                "decided_at_ms": now_ms,
            }

    def _mirror_attachment(self, record: RobotCandidateRecord) -> dict[str, object]:
        """Durable MIRROR decision, except transient failures which retry without orders."""
        now_ms = self._now_ms()
        try:
            siblings = self._store().load_robot_candidates_for_symbol(
                self._account_id, record.symbol,
            )
            parent_id = (record.robot_state or {}).get("mirror_parent_candidate_id")
            wedge_siblings = [
                item for item in siblings
                if (item.signal_snapshot or {}).get("pattern") in mirror.WEDGE_PATTERNS
                and (parent_id is None or item.candidate_id == parent_id)
            ]
            # A linked Box child belongs to its Wedge parent's campaign only; any other Box attempt may also join a
            # live Scanner MIRROR level campaign.
            scanner_sources = (
                mirror.scanner_level_sources(record.symbol.value, root=self._mirror_policy.scanner_root)
                if parent_id is None and self._mirror_policy.scanner_levels else ()
            )
            campaign = mirror.find_active_campaign(
                self._mirror_policy,
                wedge_siblings,
                symbol=record.symbol.value,
                direction=str(record.robot_state.get("direction", "")).upper(),
                now_ms=now_ms,
                scanner_sources=scanner_sources,
            )
            if (
                parent_id is not None
                and campaign is not None
                and campaign.get("parent_candidate_id") != parent_id
            ):
                raise mirror.MirrorRobotError("linked MIRROR parent campaign changed")
            prior = self._mirror_prior_attempts(record, campaign, siblings)
            return mirror.plan_attachment(
                self._mirror_policy,
                box_snapshot=self._box_source(record, record.robot_state.get("execution") or {}).signal_snapshot,
                symbol=record.symbol.value,
                campaign=campaign,
                prior_attempts=prior,
                now_ms=now_ms,
            )
        except Exception as error:
            return {
                "strategy_id": mirror.STRATEGY_ID,
                "decision": mirror.DEFERRED,
                "reason": f"mirror_error:{type(error).__name__}",
                "decided_at_ms": now_ms,
            }

    def _advance_mirror_box(self, record: RobotCandidateRecord) -> bool:
        """Advance the attached campaign by closed candles; close the remainder after a proven retest."""
        execution = dict((record.robot_state or {}).get("execution") or {})
        if not mirror.is_attached(execution):
            return False
        if mirror.retest_exit_requested(execution):
            return self._mirror_close_remainder(record, execution)
        if self._mirror_policy is None:
            return False
        record_mirror = dict(mirror.mirror_record(execution))
        boundary = mirror.boundary_from_dict(record_mirror["boundary"])
        state, blocked = mirror.advance_boundary(
            self._mirror_policy,
            boundary.boundary_id.split(":", 1)[0],
            record.symbol.value,
            boundary,
            record_mirror["state"],
            now_ms=self._now_ms(),
        )
        if state == record_mirror["state"] and blocked == bool(record_mirror.get("data_blocked")):
            return False
        record_mirror["state"] = state
        record_mirror["data_blocked"] = blocked
        if state.get("phase") == mirror.PHASE_RETEST_PROVEN:
            record_mirror["exit"] = {
                "reason": mirror.EXIT_REASON_RETEST,
                "requested_at_ms": self._now_ms(),
                "retest": state.get("retest"),
            }
        execution["mirror"] = record_mirror
        return self._save_execution_keep_status(record, execution)

    def _mirror_close_remainder(
        self, record: RobotCandidateRecord, execution: dict[str, object],
    ) -> bool:
        """Close what is left with the existing Box-owned EXIT MARKET (slot 0); finalization is shared."""
        source = self._box_source(record, execution)
        try:
            proof = self._store().prove_box_owned_position(source.candidate_id)
        except Exception as error:
            self._escalate_reconciliation(
                "ROBOT_MIRROR_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} reason={error}"
            )
            return False
        if proof.remaining_quantity == 0:
            if proof.entry_quantity == 0:
                # The campaign ended before any fill: no further attempt may start (owner rule 7).
                self._mirror_cancel_owned_limits(record, source, roles={"ENTRY", "EXIT"})
                self._invalidate_pre_entry_candidate(
                    record, reason="MIRROR campaign retest before Box entry",
                )
                return True
            return self._sync_box_trade(record, execution, create_trade=False)

        record_mirror = dict(mirror.mirror_record(execution))
        raw_intent = record_mirror.get("close_intent")
        if isinstance(raw_intent, Mapping):
            plan = restore_box_market_plan(raw_intent)
            if plan.slot != 0 or plan.quantity != proof.remaining_quantity:
                self._escalate_reconciliation(
                    "ROBOT_MIRROR_CLOSE_INTENT_CONFLICT "
                    f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
                )
                return False
        else:
            close = self._emergency_close_path
            owner_path = self._get_market_book is None and close is not None
            get_book = close.get_market_book if owner_path else self._get_market_book
            preflight = close.market_preflight if owner_path else self._market_preflight
            if get_book is None or preflight is None:
                return False
            book = get_book(record.symbol.value)
            if book is None:
                return False
            plan = mirror.retest_close_market_plan(source, book, quantity=proof.remaining_quantity)
            admitted = preflight(plan.request, plan.identity)
            if (
                not getattr(admitted, "admitted", False)
                or getattr(admitted, "normalized_quantity", None) != plan.quantity
            ):
                return False
            record_mirror["close_intent"] = durable_box_market_intent(plan)
            execution["mirror"] = record_mirror
            if not self._save_execution_keep_status(record, execution):
                return False

        self._store().reserve_box_order_identity(
            source.candidate_id, order_id=plan.order_id, role="EXIT", slot=0,
        )
        # Nothing owned may rest after the close: no re-entry, no stray partial EXIT.
        self._mirror_cancel_owned_limits(record, source, roles={"ENTRY", "EXIT"}, keep=plan.order_id)
        close = self._emergency_close_path
        owner_path = self._get_market_book is None and close is not None
        submit = close.submit_market if owner_path else self._submit_market
        if submit is None:
            return False
        result = submit(plan.request, plan.identity)
        if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
            return True
        return self._sync_box_trade(record, execution, create_trade=False) or True

    def _mirror_cancel_owned_limits(
        self, record: RobotCandidateRecord, source: RobotCandidateRecord, *,
        roles: set[str], keep: OrderId | None = None,
    ) -> None:
        now_ms = self._now_ms()
        for owner in self._store().load_box_order_ownership(source.candidate_id):
            if owner.role not in roles or owner.order_id == keep:
                continue
            limit = self._store().get_paper_limit(owner.order_id.value, self._account_id)
            if limit is None or limit.status in INACTIVE_LIMIT_STATUSES:
                continue
            digest = hashlib.sha256(
                f"{source.candidate_id}\0mirror-cancel\0{owner.order_id.value}".encode("utf-8")
            ).hexdigest()[:32]
            self._store().cancel_paper_limit(
                client_action_id=f"box-mirror-cancel-{digest}",
                request_fingerprint=hashlib.sha256(
                    f"{record.symbol.value}\0{owner.order_id.value}".encode("utf-8")
                ).hexdigest(),
                order_id=owner.order_id,
                trading_account_id=self._account_id,
                updated_at_ms=now_ms,
            )

    def _mirror_adjust_stop(self, record, source, plan, proof, current_stop):
        """After a proven partial TAKE: stop new entries and tighten the remainder STOP to net break-even."""
        execution = dict((record.robot_state or {}).get("execution") or {})
        if (
            not mirror.is_attached(execution)
            or proof.exit_quantity <= 0
            or proof.remaining_quantity <= 0
        ):
            return plan
        # The setup's TAKE is realized: untouched entries must not add exposure (as plain Box at flat).
        self._mirror_cancel_owned_limits(record, source, roles={"ENTRY"})
        record_mirror = dict(mirror.mirror_record(execution))
        be_stop = record_mirror.get("be_stop")
        if be_stop is None and self._get_market_book is not None:
            book = self._get_market_book(record.symbol.value)
            levels = None if book is None else (book.bids if plan.direction == "LONG" else book.asks)
            if levels:
                policy = self._mirror_policy
                computed = mirror.break_even_stop(
                    policy.fee_rate if policy else mirror.PAPER_FEE_RATE,
                    policy.stop_slippage_fraction if policy else mirror.STOP_SLIPPAGE_FRACTION,
                    direction=plan.direction,
                    proof=proof,
                    current_stop=current_stop,
                    mark=Decimal(str(levels[0].price.value)),
                    tick=Decimal(str((source.signal_snapshot.get("inputs") or {})["tick_size"])),
                )
                if computed is not None:
                    record_mirror["be_stop"] = str(computed)
                    execution["mirror"] = record_mirror
                    if self._save_execution_keep_status(record, execution):
                        be_stop = record_mirror["be_stop"]
        if be_stop is None:
            return plan
        stop = mirror.tighter_stop(plan.direction, Decimal(str(be_stop)), plan.stop_price)
        if stop == plan.stop_price:
            return plan
        return replace(
            plan,
            stop_price=stop,
            stop_request=PaperStopMutationRequest(
                robot_protection._action_id(plan.candidate_id, "stop", stop), plan.symbol, stop,
            ),
        )

    @staticmethod
    def _with_execution(
        record: RobotCandidateRecord, execution: Mapping[str, object],
    ) -> RobotCandidateRecord:
        """The same record (same revision) carrying ``execution`` for a following single write."""
        state = dict(record.robot_state or {})
        state["execution"] = dict(execution)
        return replace(record, robot_state=state)

    def _persist_execution(
        self, record: RobotCandidateRecord, execution: Mapping[str, object],
    ) -> None:
        new_state = dict(record.robot_state)
        new_state["execution"] = dict(execution)
        self._persist_state(record, new_state)

    def _persist_state(
        self, record: RobotCandidateRecord, new_state: Mapping[str, object],
    ) -> None:
        status = (
            "EXPIRED"
            if new_state.get("phase") == robot_state_machine.PHASE_EXPIRED_AT_APEX
            else "APPROVED"
        )
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status=status,
                robot_state=dict(new_state),
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            pass

    @staticmethod
    def _candidate_payload(record: RobotCandidateRecord) -> dict[str, object]:
        return {
            "candidate_id": record.candidate_id,
            "status": record.status,
            "timeframe": "1",
            "symbol": record.symbol.value,
            "signal_snapshot": dict(record.signal_snapshot),
        }

    def _now_ms(self) -> int:
        value = self._clock_ms()
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RobotBreakoutMonitorError(
                "Robot breakout monitor clock returned invalid timestamp"
            )
        return value
