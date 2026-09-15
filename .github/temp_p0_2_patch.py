from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


admission = "terminal/application/robot_admission.py"
replace_once(
    admission,
    '''class RobotAdmissionRejected(PersistenceError):
    """Raised when a candidate cannot cross the durable Robot admission gate."""


def admit_robot_candidate(
''',
    '''class RobotAdmissionRejected(PersistenceError):
    """Raised when a candidate cannot cross the durable Robot admission gate."""


def active_robot_owner_candidate_ids(
    store: SQLiteStore,
    trading_account_id: TradingAccountId,
    symbol: Symbol,
    *,
    excluding_candidate_id: str | None = None,
) -> tuple[str, ...]:
    """Return candidate ids that already own exposure on ``symbol``.

    Robot v0.1 PAPER uses one-way ``position_idx=0`` net positions. Ownership
    belongs to an OPEN lifecycle, or to an APPROVED lifecycle whose own entry
    LIMIT has authoritative non-zero fill evidence. Unfilled APPROVED
    candidates are not owners and remain recoverable.
    """
    owners: list[str] = []
    for record in store.load_robot_candidates(trading_account_id):
        if record.symbol != symbol or record.candidate_id == excluding_candidate_id:
            continue
        if record.status == "OPEN":
            owners.append(record.candidate_id)
            continue
        if record.status != "APPROVED" or not isinstance(record.robot_state, Mapping):
            continue
        execution = record.robot_state.get("execution")
        if not isinstance(execution, Mapping):
            continue
        order_id = execution.get("limit_order_id")
        if not isinstance(order_id, str) or not order_id.strip():
            continue
        order = store.get_paper_limit(order_id, trading_account_id)
        if order is not None and order.filled_quantity > 0:
            owners.append(record.candidate_id)
    return tuple(sorted(set(owners)))


def admit_robot_candidate(
''',
)
replace_once(
    admission,
    '''        if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "READY":
            raise RobotAdmissionRejected("Robot admission is not ready")

        record, created = store.create_robot_candidate(
''',
    '''        if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "READY":
            raise RobotAdmissionRejected("Robot admission is not ready")

        owners = active_robot_owner_candidate_ids(
            store, PAPER_ACCOUNT_ID, symbol, excluding_candidate_id=candidate_id,
        )
        if owners:
            raise RobotAdmissionRejected(
                "Robot symbol already has an active exposure owner: " + ",".join(owners)
            )

        record, created = store.create_robot_candidate(
''',
)

monitor = "terminal/application/robot_breakout_monitor.py"
replace_once(
    monitor,
    '''from scanner_geometry_cursor import ScannerGeometryCursorError, project_latest_geometry_index
from terminal.api.models import ClientActionId, CommandResultStatus, PaperLimitCancelRequest
''',
    '''from scanner_geometry_cursor import ScannerGeometryCursorError, project_latest_geometry_index
from terminal.api.models import ClientActionId, CommandResultStatus, PaperLimitCancelRequest
from terminal.application.robot_admission import active_robot_owner_candidate_ids
''',
)
replace_once(
    monitor,
    '''                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ROBOT_STOPPED before entry order submission",
                    )
                    return True
                return False

            result = self._submit_initial_retest_limit(record, record.robot_state)
''',
    '''                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ROBOT_STOPPED before entry order submission",
                    )
                    return True
                return False

            # P0.2 final pre-submission ownership check. A different
            # pending-partial or OPEN lifecycle already owns this net symbol,
            # so keep this candidate APPROVED/recoverable and submit no risk.
            if self._active_other_owner_candidate_ids(record):
                return False

            result = self._submit_initial_retest_limit(record, record.robot_state)
''',
)
replace_once(
    monitor,
    '''        entry_quantity = entry_projection.quantity.value
        entry_position_version = entry_projection.version

        try:
            stop_result, take_result = robot_protection.submit_initial_protection(
''',
    '''        entry_quantity = entry_projection.quantity.value
        entry_position_version = entry_projection.version

        # A fill now exists. If another lifecycle already owns this net
        # symbol, ownership is ambiguous: do not submit conflicting protection
        # and never blind-close the net position. Preserve evidence and
        # require reconciliation.
        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return

        try:
            stop_result, take_result = robot_protection.submit_initial_protection(
''',
)
replace_once(
    monitor,
    '''        except Exception as error:
            self._fail_closed_unprotected_fill(record, error)
            return

        now_ms = self._now_ms()
        self._store().create_robot_trade(
''',
    '''        except Exception as error:
            self._fail_closed_unprotected_fill(record, error)
            return

        # Re-check immediately before final ownership commit. This closes the
        # race between the pre-protection probe and create_robot_trade().
        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return

        now_ms = self._now_ms()
        self._store().create_robot_trade(
''',
)
replace_once(
    monitor,
    '''    def _average_entry(self, symbol: Symbol) -> Decimal | None:
''',
    '''    def _active_other_owner_candidate_ids(
        self, record: RobotCandidateRecord,
    ) -> tuple[str, ...]:
        return active_robot_owner_candidate_ids(
            self._store(), self._account_id, record.symbol,
            excluding_candidate_id=record.candidate_id,
        )

    def _escalate_duplicate_ownership(
        self, record: RobotCandidateRecord, owner_candidate_ids: tuple[str, ...],
    ) -> None:
        reason = (
            "DUPLICATE_ROBOT_OWNER "
            f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
            f"owner_candidate_ids={','.join(owner_candidate_ids)}"
        )
        for _attempt in range(2):
            runtime = self._store().get_robot_runtime_state(self._account_id)
            if runtime is None:
                raise RobotBreakoutMonitorError(
                    "Robot runtime state is unavailable during duplicate ownership escalation"
                )
            if (
                runtime.mode == "ROBOT_RUNNING"
                and runtime.recovery_status == "RECONCILIATION_REQUIRED"
                and runtime.reason == reason
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
            "Robot runtime state changed during duplicate ownership escalation"
        )

    def _average_entry(self, symbol: Symbol) -> Decimal | None:
''',
)
replace_once(
    monitor,
    '''        request = robot_protection.emergency_close_request(record.candidate_id, record.symbol.value)
        execution = dict(record.robot_state.get("execution") or {})
        execution["protection_failure"] = str(error)
        execution["emergency_close_attempted_at_ms"] = self._now_ms()
''',
    '''        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            # Section 10 narrow exception: a full-close would destroy another
            # legitimate owner of the same net position. Preserve evidence,
            # escalate, and deliberately do not close.
            execution = dict(record.robot_state.get("execution") or {})
            execution["protection_failure"] = str(error)
            execution["duplicate_owner_candidate_ids"] = list(duplicate_owners)
            execution["duplicate_ownership_detected_at_ms"] = self._now_ms()
            self._persist_execution(record, execution)
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return

        request = robot_protection.emergency_close_request(record.candidate_id, record.symbol.value)
        execution = dict(record.robot_state.get("execution") or {})
        execution["protection_failure"] = str(error)
        execution["emergency_close_attempted_at_ms"] = self._now_ms()
''',
)

admission_test = "tests/test_robot_admission.py"
replace_once(
    admission_test,
    '''import tempfile
import unittest
from pathlib import Path
''',
    '''import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
''',
)
replace_once(
    admission_test,
    '''from terminal.domain.models import TradingAccountId
''',
    '''from terminal.domain.models import Symbol, TradingAccountId
''',
)
replace_once(
    admission_test,
    '''

if __name__ == "__main__":
    unittest.main()
''',
    '''
    def test_active_owner_on_symbol_advisory_rejects_new_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            self._make_candidate(candidate_dir, "owner")
            self._make_candidate(candidate_dir, "candidate-2")
            self._ready_database(db_path)

            store = SQLiteStore.open(db_path)
            try:
                owner_snapshot = load_candidate("owner", store_dir=candidate_dir)["signal_snapshot"]
                store.create_robot_candidate(
                    candidate_id="owner",
                    trading_account_id=TradingAccountId("paper"),
                    symbol=Symbol("ONGUSDT"),
                    status="APPROVED",
                    signal_snapshot=owner_snapshot,
                    approved_at_ms=1500,
                    updated_at_ms=1500,
                )
                store.create_robot_trade(
                    trade_id="robot-trade-owner",
                    trading_account_id=TradingAccountId("paper"),
                    candidate_id="owner",
                    symbol=Symbol("ONGUSDT"),
                    direction="LONG",
                    pattern="Falling Wedge",
                    source_timeframe="1",
                    signal_time_ms=1500,
                    entry_time_ms=1600,
                    entry_path="LIMIT",
                    actual_wv=Decimal("1"),
                    average_entry=Decimal("1"),
                    stop_price=Decimal("0.9"),
                    take_price=Decimal("1.2"),
                    entry_quantity=Decimal("1"),
                    entry_position_version=1,
                    created_at_ms=1600,
                )
            finally:
                store.close()

            with self.assertRaisesRegex(
                RobotAdmissionRejected, "active exposure owner: owner",
            ):
                admit_robot_candidate(
                    "candidate-2",
                    database_path=db_path,
                    store_dir=candidate_dir,
                    clock_ms=lambda: 2000,
                )

            self.assertEqual(
                load_candidate("candidate-2", store_dir=candidate_dir)["status"],
                "AVAILABLE",
            )
            store = SQLiteStore.open(db_path)
            try:
                self.assertIsNone(store.get_robot_candidate("candidate-2"))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
''',
)

monitor_test = "tests/test_robot_breakout_monitor.py"
replace_once(
    monitor_test,
    '''    def test_batusdt_like_wrong_side_structural_extreme_falls_back_and_protects(self):
''',
    '''    def test_existing_open_owner_blocks_first_limit_without_invalidating_candidate(self):
        self._create_candidate(candidate_id="owner")
        self._drive_to_retest_detected("owner")
        self.monitor.tick()
        owner_order_id = self.store.get_robot_candidate("owner").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            owner_order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"),
        )
        self.monitor.tick()
        self.assertEqual(self.store.get_robot_candidate("owner").status, "OPEN")

        self._create_candidate(candidate_id="candidate-2")
        self._drive_to_retest_detected("candidate-2")
        prior_limit_count = len(self.executor.limit_calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ())
        self.assertEqual(len(self.executor.limit_calls), prior_limit_count)
        blocked = self.store.get_robot_candidate("candidate-2")
        self.assertEqual(blocked.status, "APPROVED")
        self.assertNotIn("limit_order_id", blocked.robot_state.get("execution") or {})

    def test_late_second_fill_escalates_duplicate_owner_without_net_close(self):
        self._create_candidate(candidate_id="candidate-a")
        self._drive_to_retest_detected("candidate-a")
        self.monitor.tick()
        order_a = self.store.get_robot_candidate("candidate-a").robot_state["execution"]["limit_order_id"]

        self._create_candidate(candidate_id="candidate-b")
        self._drive_to_retest_detected("candidate-b")
        self.monitor.tick()
        order_b = self.store.get_robot_candidate("candidate-b").robot_state["execution"]["limit_order_id"]

        self.executor.fill_resting_limit(order_a, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))
        self.monitor.tick()
        self.assertEqual(self.store.get_robot_candidate("candidate-a").status, "OPEN")
        protection_count = len(self.executor.protection_calls)

        self.executor.fill_resting_limit(order_b, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("82"))
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-b",))
        self.assertEqual(self.store.get_robot_candidate("candidate-b").status, "APPROVED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-b"))
        self.assertEqual(len(self.executor.protection_calls), protection_count)
        self.assertNotIn("full_close", [name for name, _ in self.executor.protection_calls])
        runtime = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(
            (runtime.mode, runtime.recovery_status),
            ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
        )
        self.assertIn("DUPLICATE_ROBOT_OWNER", runtime.reason)
        self.assertIn("candidate-a", runtime.reason)
        projection = self.store.get_position_projection(
            PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        )
        self.assertEqual(projection.quantity.value, Decimal("2"))

    def test_duplicate_owner_race_during_protection_failure_never_blind_closes(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))
        self.executor.fail_create_stop = True

        with patch.object(
            RobotBreakoutMonitor,
            "_active_other_owner_candidate_ids",
            side_effect=[(), ("candidate-owner",)],
        ):
            advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.store.get_robot_candidate("candidate-1").status, "APPROVED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertNotIn("full_close", [name for name, _ in self.executor.protection_calls])
        runtime = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(
            (runtime.mode, runtime.recovery_status),
            ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
        )
        self.assertIn("candidate-owner", runtime.reason)

    def test_batusdt_like_wrong_side_structural_extreme_falls_back_and_protects(self):
''',
)
