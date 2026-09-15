from pathlib import Path

path = Path("tests/test_robot_breakout_monitor.py")
text = path.read_text(encoding="utf-8")

duplicate = '''    # -- Partial-fill protection must never depend on a new closed candle --\n    # -- Partial-fill protection must never depend on a new closed candle --\n'''
if text.count(duplicate) != 1:
    raise SystemExit("duplicate comment marker not found exactly once")
text = text.replace(
    duplicate,
    '''    # -- Partial-fill protection must never depend on a new closed candle --\n''',
    1,
)

marker = '''    def test_first_partial_fill_is_final_limit_trade_without_market_top_up(self):\n'''
if text.count(marker) != 1:
    raise SystemExit("P0.3 partial-fill test marker not found exactly once")

restart_test = '''    def test_restart_after_partial_fill_finalizes_once_without_market_top_up(self):\n        """A restart after authoritative partial fill but before ownership\n        commit must recover through the same P0.3 subtractive path: cancel\n        remainder, protect the proven fill, and create exactly one owner.\n        No fresh candle or Market completion is required."""\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()  # submits the initial LIMIT\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n\n        # Simulate process restart after the fill is durable but before the\n        # old monitor has observed/finalized it. The restarted coordinator\n        # gets a fresh SQLite connection and no closed candle is queued.\n        self.monitor.close()\n        self.monitor = RobotBreakoutMonitor(\n            lambda: SQLiteStore.open(self.db_path),\n            ACCOUNT_ID,\n            get_closed_candle=self.feed,\n            action_executor=self.executor,\n            tick_size_provider=lambda symbol: Decimal("0.1"),\n            clock_ms=self.clock,\n        )\n        feed_calls_before = len(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(len(self.feed.calls), feed_calls_before)\n        self.assertEqual(len(self.executor.cancel_calls), 1)\n        self.assertEqual(self.executor.market_calls, [])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "OPEN")\n        trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertIsNotNone(trade)\n        self.assertEqual(trade.entry_path, "LIMIT")\n        self.assertEqual(trade.actual_wv, Decimal("0.6"))\n        self.assertEqual(trade.entry_quantity, Decimal("0.6"))\n        self.assertEqual(\n            [name for name, _ in self.executor.protection_calls],\n            ["create_stop", "create_take"],\n        )\n\n        # Once the candidate is OPEN, a further tick cannot create a second\n        # trade, protection set, cancel, or entry mutation.\n        self.assertEqual(self.monitor.tick(), ())\n        self.assertEqual(len(self.executor.cancel_calls), 1)\n        self.assertEqual(self.executor.market_calls, [])\n        self.assertEqual(len(self.executor.protection_calls), 2)\n        same_trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertEqual(same_trade, trade)\n\n'''
text = text.replace(marker, restart_test + marker, 1)
path.write_text(text, encoding="utf-8")
