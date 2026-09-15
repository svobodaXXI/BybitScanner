from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8-sig")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. RobotBreakoutMonitor: expose a fill-only event entry point that reuses
# the exact P0.3 Option A path without reading candles or matching again.
replace_once(
    "terminal/application/robot_breakout_monitor.py",
    '''        return tuple(advanced)\n\n    def _record_execution_error(self, record: RobotCandidateRecord, error: Exception) -> None:\n''',
    '''        return tuple(advanced)\n\n    def process_authoritative_fill(self, symbol: str) -> tuple[str, ...]:\n        """Finalize/protect already-authoritative entry fills for one symbol.\n\n        P0.4 event-driven entry point: callers must first apply the exact\n        market event to PAPER LIMIT matching on the serialized owner thread.\n        This method then advances only APPROVED/RETEST_DETECTED candidates\n        whose durable entry LIMIT already proves ``filled_quantity > 0``.\n        It never reads a closed candle, submits a new entry LIMIT, or matches\n        market data again; the ordinary periodic ``tick()`` remains only the\n        watchdog/backstop.\n        """\n        normalized = symbol.strip().upper()\n        if not normalized:\n            raise ValueError("symbol must be non-empty")\n\n        advanced: list[str] = []\n        for record in self._store().load_robot_candidates(self._account_id):\n            if (\n                record.status != "APPROVED"\n                or record.symbol.value != normalized\n                or record.robot_state is None\n                or record.robot_state.get("phase") != robot_state_machine.PHASE_RETEST_DETECTED\n            ):\n                continue\n            execution = record.robot_state.get("execution") or {}\n            order_id = execution.get("limit_order_id")\n            if not order_id:\n                continue\n            order = self._store().get_paper_limit(order_id, self._account_id)\n            if order is None or order.quantity <= 0 or order.filled_quantity <= 0:\n                continue\n            try:\n                if self._advance_retest_detected(record, match_resting_orders=False):\n                    advanced.append(record.candidate_id)\n            except Exception as error:\n                print(\n                    "[ROBOT CANDIDATE ERROR] "\n                    f"candidate_id={record.candidate_id} error={error}"\n                )\n                self._record_execution_error(record, error)\n        return tuple(advanced)\n\n    def _record_execution_error(self, record: RobotCandidateRecord, error: Exception) -> None:\n''',
)
replace_once(
    "terminal/application/robot_breakout_monitor.py",
    '''    def _advance_retest_detected(self, record: RobotCandidateRecord) -> bool:\n        execution = dict(record.robot_state.get("execution") or {})\n''',
    '''    def _advance_retest_detected(\n        self, record: RobotCandidateRecord, *, match_resting_orders: bool = True,\n    ) -> bool:\n        execution = dict(record.robot_state.get("execution") or {})\n''',
)
replace_once(
    "terminal/application/robot_breakout_monitor.py",
    '''        if self._match_resting_orders is not None:\n            self._match_resting_orders(record.symbol.value)\n''',
    '''        if match_resting_orders and self._match_resting_orders is not None:\n            self._match_resting_orders(record.symbol.value)\n''',
)

# 2. PaperRuntime: split LIMIT matching from generic PAPER protection, then
# drive exact market event -> LIMIT match -> P0.3 fill finalization -> durable
# Robot STOP/TAKE crossing on one serialized owner-thread pass.
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''    def _match_symbol(\n        self,\n        symbol: Symbol,\n        book,\n        match_event_id: str,\n        context_provider: "PaperCommandContextProvider",\n    ) -> int:\n        applied = 0\n        for order in self.store.load_active_paper_limits(self._account_id, symbol):\n            result = self._limit_executor.execute(\n                order=order,\n                book=book,\n                match_event_id=match_event_id,\n            )\n            if result is not None and result.apply_result is ExecutionApplyResult.APPLIED:\n                applied += 1\n        context = context_provider.context_for(symbol.value)\n''',
    '''    def _match_limits_only(\n        self,\n        symbol: Symbol,\n        book: NormalizedOrderBook,\n        match_event_id: str,\n    ) -> int:\n        """Apply one immutable book event to resting PAPER LIMITs only.\n\n        P0.4 uses this narrow helper before Robot ownership/protection\n        finalization so the event-driven path never invokes the older generic\n        PAPER protection close in ``_match_symbol``.\n        """\n        applied = 0\n        for order in self.store.load_active_paper_limits(self._account_id, symbol):\n            result = self._limit_executor.execute(\n                order=order, book=book, match_event_id=match_event_id,\n            )\n            if result is not None and result.apply_result is ExecutionApplyResult.APPLIED:\n                applied += 1\n        return applied\n\n    def _match_symbol(\n        self,\n        symbol: Symbol,\n        book,\n        match_event_id: str,\n        context_provider: "PaperCommandContextProvider",\n    ) -> int:\n        applied = self._match_limits_only(symbol, book, match_event_id)\n        context = context_provider.context_for(symbol.value)\n''',
)
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''    def _match_symbol(\n''',
    '''    def process_robot_market_event(\n        self, symbol: str, book: NormalizedOrderBook, *, event_id: str, received_at_ms: int,\n    ) -> tuple[tuple[str, ...], PaperProtectionObligationRecord | None]:\n        """Process one exact Robot market event on the serialized owner thread.\n\n        P0.4 sequence is intentionally single-pass and reuse-only: match the\n        immutable event against resting entry LIMITs, immediately run P0.3's\n        fill-only cancel/finalize/protect path, then evaluate the same event\n        against the durable Robot protection engine. No periodic monitor tick\n        or closed candle is required after authoritative fill observation.\n        """\n        normalized = Symbol(symbol.strip().upper())\n        if book.symbol != normalized:\n            raise ValueError("Robot market event symbol does not match book")\n        self._match_limits_only(normalized, book, event_id)\n        monitor = RobotBreakoutMonitor(\n            lambda: self.store,\n            self._paper_account_id,\n            get_closed_candle=self._robot_closed_candle_provider,\n            action_executor=_DirectRobotActionExecutor(self),\n            tick_size_provider=lambda item: self._instrument_provider(item).tick_size,\n            clock_ms=lambda: int(time.time() * 1000),\n        )\n        finalized = monitor.process_authoritative_fill(normalized.value)\n        obligation = self.evaluate_robot_protection_crossing(\n            normalized.value, book, event_id=event_id, received_at_ms=received_at_ms,\n        )\n        return finalized, obligation\n\n    def _match_symbol(\n''',
)
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''        unresolved_symbols = {obligation.symbol.value for obligation in unresolved}\n        return tuple(sorted(open_symbols | unresolved_symbols))\n''',
    '''        unresolved_symbols = {obligation.symbol.value for obligation in unresolved}\n\n        # P0.4: an APPROVED lifecycle with a durable entry LIMIT also needs\n        # the ordered MarketDataHub feed. A live LIMIT may receive its first\n        # fill on any book event; a cancelled/filled LIMIT with non-zero fill\n        # stays covered until ownership/protection finalization has consumed\n        # that durable evidence (restart/cancel race backstop). Zero-fill\n        # inactive orders do not retain coverage.\n        entry_symbols: set[str] = set()\n        for candidate in candidates:\n            if candidate.status != "APPROVED" or candidate.robot_state is None:\n                continue\n            if candidate.robot_state.get("phase") != "RETEST_DETECTED":\n                continue\n            execution = candidate.robot_state.get("execution") or {}\n            order_id = execution.get("limit_order_id")\n            if not order_id:\n                continue\n            order = self.store.get_paper_limit(order_id, self._paper_account_id)\n            if order is None:\n                continue\n            if order.status not in INACTIVE_LIMIT_STATUSES or order.filled_quantity > 0:\n                entry_symbols.add(candidate.symbol.value)\n\n        return tuple(sorted(open_symbols | unresolved_symbols | entry_symbols))\n''',
)

# 3. Coverage manager: reuse its ordered, bounded, continuity-checked event
# ingress for both first-fill handling and already-open STOP/TAKE coverage.
replace_once(
    "terminal/runtime/paper_http_server.py",
    '''class RobotProtectionCoverageManager:\n    """Keep independent MarketDataHub coverage for every symbol with a\n    non-flat Robot-owned PAPER trade, regardless of Workspace selection or\n    Robot entry-admission state, and forward each ordered book update to the\n    serialized PAPER owner for durable crossing evaluation.\n''',
    '''class RobotProtectionCoverageManager:\n    """Keep independent MarketDataHub coverage for Robot entry/protection.\n\n    Coverage includes durable pre-entry LIMIT lifecycles that may receive a\n    first fill plus non-flat Robot-owned PAPER trades / unresolved protection\n    obligations. It is independent of Workspace selection and forwards every\n    ordered book update to the serialized PAPER owner for first-fill handling\n    and durable crossing evaluation in one pass.\n''',
)
replace_once(
    "terminal/runtime/paper_http_server.py",
    '''            try:\n                context = self._hub.subscribe(symbol)\n            except Exception:\n                LOGGER.exception("Robot protection coverage subscribe failed; symbol=%s", symbol)\n                continue\n''',
    '''            try:\n                context = self._hub.subscribe(symbol)\n            except Exception:\n                self._mark_unhealthy(symbol, "subscribe_failed")\n                LOGGER.exception("Robot protection coverage subscribe failed; symbol=%s", symbol)\n                continue\n''',
)
replace_once(
    "terminal/runtime/paper_http_server.py",
    '''            return runtime.evaluate_robot_protection_crossing(\n                symbol, book, event_id=book_update_id, received_at_ms=received_at_ms,\n            )\n''',
    '''            return runtime.process_robot_market_event(\n                symbol, book, event_id=book_update_id, received_at_ms=received_at_ms,\n            )\n''',
)

# 4. Focused regressions.
replace_once(
    "tests/test_robot_breakout_monitor.py",
    '''    def test_first_partial_fill_is_final_limit_trade_without_market_top_up(self):\n''',
    '''    def test_event_driven_authoritative_fill_finalizes_without_periodic_tick_or_candle(self):\n        self._create_candidate()\n        self._drive_to_retest_detected()\n        self.monitor.tick()  # submits the initial LIMIT\n        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]\n        self.executor.fill_resting_limit(\n            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),\n        )\n        feed_calls_before = len(self.feed.calls)\n\n        advanced = self.monitor.process_authoritative_fill(SYMBOL)\n\n        self.assertEqual(advanced, ("candidate-1",))\n        self.assertEqual(len(self.feed.calls), feed_calls_before)\n        self.assertEqual(len(self.executor.cancel_calls), 1)\n        self.assertEqual(self.executor.market_calls, [])\n        record = self.store.get_robot_candidate("candidate-1")\n        self.assertEqual(record.status, "OPEN")\n        trade = self.store.get_robot_trade("robot-trade-candidate-1")\n        self.assertIsNotNone(trade)\n        self.assertEqual(trade.entry_path, "LIMIT")\n        self.assertEqual(trade.actual_wv, Decimal("0.6"))\n        self.assertEqual(trade.entry_quantity, Decimal("0.6"))\n        self.assertEqual(\n            [name for name, _ in self.executor.protection_calls],\n            ["create_stop", "create_take"],\n        )\n\n    def test_first_partial_fill_is_final_limit_trade_without_market_top_up(self):\n''',
)
replace_once(
    "tests/test_terminal_paper_runtime.py",
    '''def test_robot_protection_coverage_symbols_reflects_open_robot_candidates_only():\n''',
    '''def test_robot_entry_limit_is_covered_before_first_fill_and_released_after_zero_fill_cancel():\n    with tempfile.TemporaryDirectory() as temp:\n        runtime = _runtime(Path(temp) / "paper.sqlite3")\n        try:\n            _seed_pending_candidate_with_resting_limit(\n                runtime, candidate_id="candidate-entry-coverage",\n                order_id="entry-coverage-limit", symbol="BTCUSDT",\n            )\n            assert runtime.robot_protection_coverage_symbols() == ("BTCUSDT",)\n\n            runtime._robot_cancel_limit(PaperLimitCancelRequest(\n                ClientActionId("entry-coverage-cancel"),\n                "BTCUSDT", "entry-coverage-limit",\n            ))\n            assert runtime.robot_protection_coverage_symbols() == ()\n        finally:\n            runtime.close()\n\n\ndef test_robot_protection_coverage_symbols_reflects_open_robot_candidates_only():\n''',
)
replace_once(
    "tests/test_terminal_paper_http.py",
    '''        self.crossing_calls: list[tuple[str, str, int]] = []\n        self.fail_next_enqueue: BaseException | None = None\n''',
    '''        self.crossing_calls: list[tuple[str, str, int]] = []\n        self.market_event_calls: list[tuple[str, str, int]] = []\n        self.fail_next_enqueue: BaseException | None = None\n''',
)
replace_once(
    "tests/test_terminal_paper_http.py",
    '''    def evaluate_robot_protection_crossing(self, symbol, book, *, event_id, received_at_ms):\n        self.crossing_calls.append((symbol, event_id, received_at_ms))\n        return None\n''',
    '''    def process_robot_market_event(self, symbol, book, *, event_id, received_at_ms):\n        self.market_event_calls.append((symbol, event_id, received_at_ms))\n        return self.evaluate_robot_protection_crossing(\n            symbol, book, event_id=event_id, received_at_ms=received_at_ms,\n        )\n\n    def evaluate_robot_protection_crossing(self, symbol, book, *, event_id, received_at_ms):\n        self.crossing_calls.append((symbol, event_id, received_at_ms))\n        return None\n''',
)
replace_once(
    "tests/test_terminal_paper_http.py",
    '''    assert len(runtime.crossing_calls) == 1\n    symbol, event_id, received_at_ms = runtime.crossing_calls[0]\n''',
    '''    assert len(runtime.market_event_calls) == 1\n    assert len(runtime.crossing_calls) == 1\n    symbol, event_id, received_at_ms = runtime.crossing_calls[0]\n''',
)
