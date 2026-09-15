from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, got {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "terminal/runtime/paper_runtime.py",
    '''    def _match_limits_only(\n        self,\n        symbol: Symbol,\n        book: NormalizedOrderBook,\n        match_event_id: str,\n    ) -> int:\n''',
    '''    def _match_limits_only(\n        self,\n        symbol: Symbol,\n        book: NormalizedOrderBook,\n        match_event_id: str,\n        *,\n        allowed_order_ids: set[str] | None = None,\n    ) -> int:\n''',
)
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''        applied = 0\n        for order in self.store.load_active_paper_limits(self._account_id, symbol):\n            result = self._limit_executor.execute(\n                order=order, book=book, match_event_id=match_event_id,\n            )\n''',
    '''        applied = 0\n        for order in self.store.load_active_paper_limits(self._account_id, symbol):\n            if allowed_order_ids is not None and order.order_id.value not in allowed_order_ids:\n                continue\n            result = self._limit_executor.execute(\n                order=order, book=book, match_event_id=match_event_id,\n            )\n''',
)
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''        if book.symbol != normalized:\n            raise ValueError("Robot market event symbol does not match book")\n        self._match_limits_only(normalized, book, event_id)\n        monitor = RobotBreakoutMonitor(\n''',
    '''        if book.symbol != normalized:\n            raise ValueError("Robot market event symbol does not match book")\n        entry_order_ids: set[str] = set()\n        for candidate in self.store.load_robot_candidates(self._paper_account_id):\n            if (\n                candidate.status != "APPROVED"\n                or candidate.symbol != normalized\n                or candidate.robot_state is None\n                or candidate.robot_state.get("phase") != "RETEST_DETECTED"\n            ):\n                continue\n            order_id = (candidate.robot_state.get("execution") or {}).get("limit_order_id")\n            if order_id:\n                entry_order_ids.add(order_id)\n        self._match_limits_only(\n            normalized, book, event_id, allowed_order_ids=entry_order_ids,\n        )\n        monitor = RobotBreakoutMonitor(\n''',
)
replace_once(
    "terminal/runtime/paper_runtime.py",
    '''            order_id = execution.get("limit_order_id")\n            if not order_id:\n                continue\n            order = self.store.get_paper_limit(order_id, self._paper_account_id)\n''',
    '''            order_id = execution.get("limit_order_id")\n            if not order_id:\n                # Subscribe one monitor cycle early: RETEST_DETECTED is\n                # persisted before the following periodic tick submits the\n                # entry LIMIT. This eliminates the resync window in which an\n                # immediately marketable new LIMIT could fill before the\n                # independent Robot event feed was attached.\n                entry_symbols.add(candidate.symbol.value)\n                continue\n            order = self.store.get_paper_limit(order_id, self._paper_account_id)\n''',
)

replace_once(
    "tests/test_terminal_paper_runtime.py",
    '''def test_robot_entry_limit_is_covered_before_first_fill_and_released_after_zero_fill_cancel():\n''',
    '''def test_retest_detected_candidate_is_covered_before_entry_limit_submission():\n    with tempfile.TemporaryDirectory() as temp:\n        runtime = _runtime(Path(temp) / "paper.sqlite3")\n        try:\n            account = TradingAccountId("paper")\n            runtime.store.create_robot_candidate(\n                candidate_id="candidate-prelimit-coverage", trading_account_id=account,\n                symbol=Symbol("BTCUSDT"), status="APPROVED",\n                signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge"},\n                approved_at_ms=1000, updated_at_ms=1000,\n            )\n            runtime.store.save_robot_candidate_state(\n                "candidate-prelimit-coverage", status="APPROVED",\n                robot_state={"phase": "RETEST_DETECTED", "execution": {}},\n                expected_revision=0, updated_at_ms=1001,\n            )\n            assert runtime.robot_protection_coverage_symbols() == ("BTCUSDT",)\n        finally:\n            runtime.close()\n\n\ndef test_robot_entry_limit_is_covered_before_first_fill_and_released_after_zero_fill_cancel():\n''',
)

# Restore the pre-existing UTF-8 BOMs removed only as an artifact of the first
# temporary patch script, keeping the semantic PR diff free of encoding churn.
for name in (
    "terminal/runtime/paper_http_server.py",
    "tests/test_terminal_paper_runtime.py",
):
    path = Path(name)
    data = path.read_bytes()
    if not data.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(b"\xef\xbb\xbf" + data)
