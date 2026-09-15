from pathlib import Path


def replace_range(path: str, start_marker: str, end_marker: str, replacement: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"{path}: start marker not found: {start_marker!r}")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"{path}: end marker not found: {end_marker!r}")
    p.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


path = "tests/test_robot_breakout_monitor.py"

replace_range(
    path,
    '''    def test_paused_partial_fill_finalizes_actual_quantity_instead_of_waiting_for_market_top_up(self):\n''',
    '''    def test_robot_stopped_partial_fill_finalizes_actual_quantity_never_orphaning_exposure(self):\n''',
    '''    def test_paused_partial_fill_finalizes_actual_quantity_instead_of_waiting_for_market_top_up(self):\n        """A fill that exists before PAUSE is observed still finalizes the\n        actual LIMIT-filled quantity immediately; PAUSE blocks only new risk.\n        P0.3 removes the old wait/top-up phase entirely."""\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        self._set_admission_state("ROBOT_RUNNING", "PAUSED")\n        calls_before = list(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(self.feed.calls, calls_before)\n        self.assertEqual(self.executor.market_calls, [])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "OPEN")\n        trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertEqual(trade.entry_path, "LIMIT")\n        self.assertEqual(trade.actual_wv, Decimal("0.6"))\n        self.assertEqual(\n            [name for name, _ in self.executor.protection_calls],\n            ["create_stop", "create_take"],\n        )\n        self.assertEqual(self.store.get_robot_runtime_state(ACCOUNT_ID).recovery_status, "PAUSED")\n\n''',
)

replace_range(
    path,
    '''    def test_robot_stopped_partial_fill_finalizes_actual_quantity_never_orphaning_exposure(self):\n''',
    '''    def test_paused_partial_fill_protection_failure_uses_fail_closed_emergency_close(self):\n''',
    '''    def test_robot_stopped_partial_fill_finalizes_actual_quantity_never_orphaning_exposure(self):\n        """ROBOT_STOPPED cannot invalidate a candidate that already has real\n        exposure; P0.3 finalizes and protects that actual LIMIT fill instead."""\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")\n        calls_before = list(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(self.feed.calls, calls_before)\n        self.assertEqual(self.executor.market_calls, [])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "OPEN")\n        trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertEqual(trade.actual_wv, Decimal("0.6"))\n        self.assertEqual(\n            [name for name, _ in self.executor.protection_calls],\n            ["create_stop", "create_take"],\n        )\n\n''',
)

replace_range(
    path,
    '''    def test_paused_partial_fill_protection_failure_uses_fail_closed_emergency_close(self):\n''',
    '''    # -- Partial-fill protection must never depend on a new closed candle --\n''',
    '''    def test_paused_partial_fill_protection_failure_uses_fail_closed_emergency_close(self):\n        """Protection failure after a partial fill still uses the existing\n        fail-closed emergency close while PAUSED, with no Market top-up."""\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        self._set_admission_state("ROBOT_RUNNING", "PAUSED")\n        self.executor.fail_create_stop = True\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(self.executor.market_calls, [])\n        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "INVALIDATED")\n        self.assertEqual(\n            record.robot_state["execution"]["emergency_close_outcome"],\n            robot_protection.RECOVERY_CLOSED,\n        )\n        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))\n        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)\n        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)\n\n    # -- Partial-fill protection must never depend on a new closed candle --\n''',
)

replace_range(
    path,
    '''    def test_paused_partial_fill_protects_immediately_with_no_closed_candle_available(self):\n''',
    '''    def test_robot_stopped_partial_fill_protects_immediately_with_no_closed_candle_available(self):\n''',
    '''    def test_paused_partial_fill_protects_immediately_with_no_closed_candle_available(self):\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        self._set_admission_state("ROBOT_RUNNING", "PAUSED")\n        calls_before = list(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(self.executor.market_calls, [])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "OPEN")\n        trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertEqual(trade.actual_wv, Decimal("0.6"))\n        self.assertEqual(\n            [name for name, _ in self.executor.protection_calls],\n            ["create_stop", "create_take"],\n        )\n        self.assertEqual(self.feed.calls, calls_before)\n\n''',
)

replace_range(
    path,
    '''    def test_robot_stopped_partial_fill_protects_immediately_with_no_closed_candle_available(self):\n''',
    '''    def test_paused_partial_fill_no_candle_and_protection_failure_emergency_closes_immediately(self):\n''',
    '''    def test_robot_stopped_partial_fill_protects_immediately_with_no_closed_candle_available(self):\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")\n        calls_before = list(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(self.executor.market_calls, [])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "OPEN")\n        trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertEqual(trade.actual_wv, Decimal("0.6"))\n        self.assertEqual(self.feed.calls, calls_before)\n\n''',
)

replace_range(
    path,
    '''    def test_paused_partial_fill_no_candle_and_protection_failure_emergency_closes_immediately(self):\n''',
    '''    def test_fail_closed_emergency_close_still_operates_when_robot_stopped(self):\n''',
    '''    def test_paused_partial_fill_no_candle_and_protection_failure_emergency_closes_immediately(self):\n        """No candle plus protection failure must emergency-close in the same\n        observation pass after first fill; no wait and no Market completion."""\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        self._set_admission_state("ROBOT_RUNNING", "PAUSED")\n        self.executor.fail_create_stop = True\n        calls_before = list(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(self.feed.calls, calls_before)\n        self.assertEqual(self.executor.market_calls, [])\n        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "INVALIDATED")\n        self.assertEqual(\n            record.robot_state["execution"]["emergency_close_outcome"],\n            robot_protection.RECOVERY_CLOSED,\n        )\n        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))\n        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)\n        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)\n\n''',
)
