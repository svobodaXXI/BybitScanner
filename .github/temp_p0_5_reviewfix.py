from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8-sig")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Critical review fix: duplicate-owner ambiguity must be proven absent BEFORE
# any unresolved protection obligation is allowed to dispatch a net close.
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''            if unresolved_candidate_ids:\n                return fail(\n                    "reconcile_robot could not prove pending Robot entry safety: "\n                    + ",".join(sorted(unresolved_candidate_ids))\n                )\n\n            now_ms = int(time.time() * 1000)\n''',
    '''            if unresolved_candidate_ids:\n                return fail(\n                    "reconcile_robot could not prove pending Robot entry safety: "\n                    + ",".join(sorted(unresolved_candidate_ids))\n                )\n\n            # Duplicate-owner ambiguity is a pre-dispatch hard gate. An\n            # already-latched protection obligation is still capable of a net\n            # close, so checking ownership only after resuming obligations\n            # would be too late. Never dispatch any close until every active\n            # symbol proves at most one Robot owner.\n            candidates = self.store.load_robot_candidates(self._paper_account_id)\n            symbols = sorted({\n                item.symbol for item in candidates if item.status in {"APPROVED", "OPEN"}\n            }, key=lambda item: item.value)\n            for symbol in symbols:\n                owners = active_robot_owner_candidate_ids(\n                    self.store, self._paper_account_id, symbol,\n                )\n                if len(owners) > 1:\n                    unresolved_candidate_ids.update(owners)\n            if unresolved_candidate_ids:\n                return fail(\n                    "DUPLICATE_ROBOT_OWNER during reconcile_robot: "\n                    + ",".join(sorted(unresolved_candidate_ids))\n                )\n\n            now_ms = int(time.time() * 1000)\n''',
)
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''            candidates = self.store.load_robot_candidates(self._paper_account_id)\n            symbols = sorted({\n                item.symbol for item in candidates if item.status in {"APPROVED", "OPEN"}\n            }, key=lambda item: item.value)\n            for symbol in symbols:\n                owners = active_robot_owner_candidate_ids(\n                    self.store, self._paper_account_id, symbol,\n                )\n                if len(owners) > 1:\n                    unresolved_candidate_ids.update(owners)\n            if unresolved_candidate_ids:\n                return fail(\n                    "DUPLICATE_ROBOT_OWNER during reconcile_robot: "\n                    + ",".join(sorted(unresolved_candidate_ids))\n                )\n\n            candidates = self.store.load_robot_candidates(self._paper_account_id)\n''',
    '''            candidates = self.store.load_robot_candidates(self._paper_account_id)\n''',
)

# Strengthen the duplicate-owner regression with an already-latched obligation;
# reconcile must not dispatch its stable close identity while ownership is ambiguous.
replace_once(
    "tests/test_terminal_paper_runtime.py",
    '''            _set_admission(\n                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",\n            )\n            executions_before = len(runtime.store.load_executions())\n            position_before = runtime.store.get_position_projection(PositionKey(\n''',
    '''            runtime.store.latch_paper_protection_obligation(\n                trade_id="trade-reconcile-owner-a", protection_version=1,\n                winning_leg="STOP", trigger_price=Decimal("64000"),\n                observed_exit_price=Decimal("63990"), observed_quantity=Decimal("0.004"),\n                market_event_id="evt-duplicate-owner", source_received_at_ms=4000,\n                source_generation=0, source_sequence=4000, source_update_id=4000,\n                source_event_at_ms=4000, source_matching_engine_cts_ms=None,\n                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),\n                latched_at_ms=4000,\n            )\n            _set_admission(\n                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",\n            )\n            executions_before = len(runtime.store.load_executions())\n            position_before = runtime.store.get_position_projection(PositionKey(\n''',
)
replace_once(
    "tests/test_terminal_paper_runtime.py",
    '''            assert runtime.store.get_robot_trade("trade-reconcile-owner-a").exit_time_ms is None\n            assert runtime.store.get_robot_trade("trade-reconcile-owner-b").exit_time_ms is None\n        finally:\n            runtime.close()\n\n\ndef test_robot_protection_crossing_leg_preserves_long_short_and_stop_precedence():\n''',
    '''            assert runtime.store.get_robot_trade("trade-reconcile-owner-a").exit_time_ms is None\n            assert runtime.store.get_robot_trade("trade-reconcile-owner-b").exit_time_ms is None\n            obligation = runtime.store.get_paper_protection_obligation_for_trade(\n                "trade-reconcile-owner-a"\n            )\n            assert obligation.status == "TRIGGERED"\n        finally:\n            runtime.close()\n\n\ndef test_robot_reconcile_is_independent_of_workspace_live_account_selection():\n    paper_account = TradingAccount(\n        TradingAccountId("paper"), "Paper / Virtual", TradingAccountProvider.PAPER,\n        TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,\n    )\n    live_account = TradingAccount(\n        TradingAccountId("bybit-1"), "Live Mainnet", TradingAccountProvider.BYBIT,\n        TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,\n    )\n    manager = TradingAccountManager(\n        (paper_account, live_account), active_account_id=paper_account.id,\n    )\n    with tempfile.TemporaryDirectory() as temp:\n        provider = MutableBookProvider("BTCUSDT", _entry_book())\n        primary = _instrument()\n        runtime = PaperRuntime(\n            Path(temp) / "paper.sqlite3", book_provider=provider,\n            instrument_snapshot=primary,\n            instrument_provider=lambda symbol: replace(primary, symbol=symbol),\n            account_manager=manager,\n        )\n        runtime._robot_command_dispatcher = lambda operation: operation(runtime)\n        try:\n            _open_robot_position_with_confirmed_protection(\n                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),\n                stop_price=Decimal("64000"), take_price=Decimal("64600"),\n                trade_id="trade-reconcile-live-ui", candidate_id="candidate-reconcile-live-ui",\n            )\n            _set_admission(\n                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",\n            )\n            manager.activate(live_account.id)\n\n            result = runtime.robot_reconcile()\n\n            assert result.success is True\n            assert result.recovery_status == "PAUSED"\n            assert manager.active_account.id == live_account.id\n        finally:\n            runtime.close()\n\n\ndef test_robot_protection_crossing_leg_preserves_long_short_and_stop_precedence():\n''',
)

# Make recovery legality regression actually cover READY, PAUSED and STOPPED/REQUIRED.
replace_once(
    "tests/test_robot_recovery_coordinator.py",
    '''    def test_reconcile_required_rejects_every_other_durable_state_without_side_effect(self):\n        for status in (READY, PAUSED):\n            running = self._initialize_running()\n            if status != READY:\n                running = self.store.update_robot_runtime_state(\n                    ACCOUNT_ID, mode="ROBOT_RUNNING", recovery_status=status, reason=None,\n                    expected_version=running.version, updated_at_ms=self.clock(),\n                )\n            version = running.version\n            coordinator = RobotRecoveryCoordinator(\n                self.store, ACCOUNT_ID, clock_ms=self.clock,\n            )\n            with self.assertRaises(RobotRecoveryError):\n                coordinator.reconcile_required()\n            self.assertEqual(\n                self.store.get_robot_runtime_state(ACCOUNT_ID).version, version,\n            )\n            # Reset through a fresh DB state is simpler than inventing an\n            # illegal backwards transition inside the same loop.\n            if status == READY:\n                break\n''',
    '''    def test_reconcile_required_rejects_every_other_durable_state_without_side_effect(self):\n        coordinator = RobotRecoveryCoordinator(\n            self.store, ACCOUNT_ID, clock_ms=self.clock,\n        )\n        running = self._initialize_running()\n        with self.assertRaises(RobotRecoveryError):\n            coordinator.reconcile_required()\n        self.assertEqual(\n            self.store.get_robot_runtime_state(ACCOUNT_ID).version, running.version,\n        )\n\n        paused = self.store.update_robot_runtime_state(\n            ACCOUNT_ID, mode="ROBOT_RUNNING", recovery_status=PAUSED, reason=None,\n            expected_version=running.version, updated_at_ms=self.clock(),\n        )\n        with self.assertRaises(RobotRecoveryError):\n            coordinator.reconcile_required()\n        self.assertEqual(\n            self.store.get_robot_runtime_state(ACCOUNT_ID).version, paused.version,\n        )\n\n        stopped_required = self.store.update_robot_runtime_state(\n            ACCOUNT_ID, mode="ROBOT_STOPPED",\n            recovery_status="RECONCILIATION_REQUIRED", reason="stopped ambiguity",\n            expected_version=paused.version, updated_at_ms=self.clock(),\n        )\n        with self.assertRaises(RobotRecoveryError):\n            coordinator.reconcile_required()\n        self.assertEqual(\n            self.store.get_robot_runtime_state(ACCOUNT_ID).version, stopped_required.version,\n        )\n''',
)

# Preserve pre-existing UTF-8 BOMs; avoid encoding-only PR churn.
for name in (
    "terminal/runtime/paper_http_server.py",
    "tests/test_terminal_paper_runtime.py",
):
    path = Path(name)
    data = path.read_bytes()
    if not data.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(b"\xef\xbb\xbf" + data)
