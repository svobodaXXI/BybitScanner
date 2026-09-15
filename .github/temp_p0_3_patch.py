from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_range(path: str, start_marker: str, end_marker: str, replacement: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"{path}: start marker not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"{path}: end marker not found")
    p.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


monitor = "terminal/application/robot_breakout_monitor.py"
replace_once(
    monitor,
    "robot_partial_fill.py, robot_market_confirmation.py and robot_protection.py,\n",
    "robot_protection.py,\n",
)
replace_once(monitor, "import robot_market_confirmation\n", "")
replace_once(monitor, "import robot_partial_fill\n", "")
replace_once(
    monitor,
    '''# Matches the existing PaperRuntime.full_close() emergency-close tolerance\n# (terminal/api/rest.py) -- reused rather than inventing a new number.\nMARKET_SLIPPAGE_TYPE = "Percent"\nMARKET_SLIPPAGE_VALUE = Decimal("0.5")\n\n''',
    "",
)
replace_once(monitor, "    def market(self, request): ...\n", "")
replace_once(
    monitor,
    '''def _cancel_partial_remainder_action_id(candidate_id: str) -> ClientActionId:\n    # No existing robot_*.py module owns "cancel the resting LIMIT before a\n    # partial-fill Market completion" -- it is orchestration this coordinator\n    # owns directly, mirroring the digest-based ClientActionId construction\n    # PaperRuntime.robot_close_all() already uses for a similar Robot-owned\n    # action outside the five pure modules.\n''',
    '''def _cancel_partial_remainder_action_id(candidate_id: str) -> ClientActionId:\n    # P0.3 Option A: the first authoritative non-zero fill ends entry sizing.\n    # Cancel the still-resting remainder through the same sanctioned LIMIT\n    # cancellation path. The deterministic action id makes retries idempotent;\n    # no Market top-up is ever submitted from this lifecycle.\n''',
)
replace_range(
    monitor,
    '''        filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))\n        inactive = order.status in INACTIVE_LIMIT_STATUSES\n''',
    '''    def _finalize_trade(\n''',
    '''        filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))\n        inactive = order.status in INACTIVE_LIMIT_STATUSES\n\n        if filled_fraction <= 0:\n            new_entry_admitted, terminal_stop = self._read_admission_gate()\n            if new_entry_admitted:\n                return False\n            # A working, still-fully-unfilled entry LIMIT exists but the\n            # admission gate no longer permits new entry risk -- cancel it\n            # through the same sanctioned execution path used everywhere\n            # else in this module. No exposure exists yet, so ROBOT_STOPPED\n            # can terminalize the candidate; PAUSED/RECONCILIATION_REQUIRED\n            # leave it APPROVED and recoverable.\n            if not inactive:\n                self._action_executor.cancel_limit(PaperLimitCancelRequest(\n                    _cancel_blocked_entry_action_id(record.candidate_id),\n                    record.symbol.value, execution["limit_order_id"],\n                ))\n            if terminal_stop:\n                self._invalidate_pre_entry_candidate(\n                    record, reason="ROBOT_STOPPED with unfilled resting entry LIMIT",\n                )\n            return True\n\n        # P0.3 Option A: the first authoritative non-zero fill is the trigger\n        # to end entry sizing. In this SAME processing pass, cancel any live\n        # remainder and immediately finalize/protect the actual LIMIT-filled\n        # exposure. There is deliberately no closed-candle read, wait timer,\n        # RR/adverse-move gate, or Market completion path here.\n        if not inactive:\n            self._action_executor.cancel_limit(PaperLimitCancelRequest(\n                _cancel_partial_remainder_action_id(record.candidate_id),\n                record.symbol.value, execution["limit_order_id"],\n            ))\n            # Cancellation can race a final resting fill. Protect and record\n            # the latest authoritative quantity after cancellation rather than\n            # inventing a target size or submitting a Market top-up.\n            refreshed = self._store().get_paper_limit(\n                execution["limit_order_id"], self._account_id,\n            )\n            if refreshed is not None:\n                order = refreshed\n                filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))\n\n        if filled_fraction <= 0:\n            # Filled quantity must never decrease, but fail closed if durable\n            # evidence becomes contradictory instead of inventing exposure.\n            return True\n\n        average_entry = self._average_entry(record.symbol)\n        if average_entry is None:\n            return True\n\n        fresh_record = self._store().get_robot_candidate(record.candidate_id) or record\n        self._finalize_trade(\n            fresh_record, execution, entry_path="LIMIT",\n            actual_wv=filled_fraction, average_entry=average_entry,\n        )\n        return True\n\n''',
)

monitor_test = "tests/test_robot_breakout_monitor.py"
replace_once(monitor_test, "import robot_partial_fill\n", "")
replace_range(
    monitor_test,
    '''    def test_partial_fill_waits_then_completes_via_market_and_creates_mixed_trade(self):\n''',
    '''    def test_unavailable_candle_leaves_state_untouched_and_does_not_crash(self):\n''',
    '''    def test_first_partial_fill_is_final_limit_trade_without_market_top_up(self):\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()  # submits the initial LIMIT\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        feed_calls_before = len(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(len(self.feed.calls), feed_calls_before)\n        self.assertEqual(len(self.executor.cancel_calls), 1)\n        self.assertEqual(self.executor.cancel_calls[0].order_id, order_id)\n        order = self.store.get_paper_limit(order_id, ACCOUNT_ID)\n        self.assertEqual(order.status, "cancelled")\n        self.assertEqual(order.filled_quantity, Decimal("0.6"))\n        self.assertEqual(self.executor.market_calls, [])\n\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "OPEN")\n        trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertIsNotNone(trade)\n        self.assertEqual(trade.entry_path, "LIMIT")\n        self.assertEqual(trade.actual_wv, Decimal("0.6"))\n        self.assertEqual(trade.average_entry, Decimal("81"))\n        self.assertEqual(\n            [name for name, _ in self.executor.protection_calls],\n            ["create_stop", "create_take"],\n        )\n        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)\n        projection = self.store.get_position_projection(position_key)\n        self.assertEqual(projection.quantity.value, Decimal("0.6"))\n        self.assertEqual(trade.entry_quantity, Decimal("0.6"))\n\n    def test_first_partial_fill_protection_failure_fails_closed_without_market_top_up(self):\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()  # submits the initial LIMIT\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        self.executor.fail_create_stop = True\n        feed_calls_before = len(self.feed.calls)\n\n        advanced = self.monitor.tick()\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(len(self.feed.calls), feed_calls_before)\n        self.assertEqual(len(self.executor.cancel_calls), 1)\n        self.assertEqual(self.executor.market_calls, [])\n        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "INVALIDATED")\n        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))\n        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)\n        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)\n\n''',
)
