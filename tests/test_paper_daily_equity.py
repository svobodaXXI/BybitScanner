"""AUTOPILOT-EQUITY-1B: PAPER-equity v1 daily facts on disposable SQLite stores only."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from terminal.application import paper_daily_equity as eq
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.paper_daily_equity import MarkPrice, collect_paper_daily_equity_facts
from terminal.domain.models import (
    Category, ExecutionId, OrderId, OrderSide, TradingAccountId,
)
from terminal.exchange.events import ExecutionEvent
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_robot_autopilot_shadow import _Db, ACCOUNT

D0 = 1791925200000  # 2026-10-14 00:00 MSK
MIN = 60_000
AGE = 5_000


class DailyEquityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        self.store = _Db(Path(self.tmp.name)).store  # PAPER account 5000, created at 1 ms
        self.engine = ExecutionEngine(self.store)
        self.n = 0

    def tearDown(self):
        self.store.close()

    def fill(self, side, price, qty, at, *, symbol="AAAUSDT", fee="0", exec_id=None):
        self.n += 1
        price, qty = Decimal(price), Decimal(qty)
        event = ExecutionEvent(
            trading_account_id=ACCOUNT, category=Category.LINEAR, symbol=symbol,
            exec_id=ExecutionId(exec_id or f"e{self.n}"), order_id=OrderId(f"o-{exec_id}" if exec_id else f"o{self.n}"),
            order_link_id=None, side=OrderSide(side), execution_price=price,
            execution_quantity=qty, execution_fee=Decimal(fee), execution_value=price * qty,
            is_maker=True, executed_at_ms=at, sequence=None)
        return self.engine.apply_paper_execution(event)

    def facts(self, as_of, marks=None, account=ACCOUNT):
        reader = SQLiteStore.open_reader(self.path)
        try:
            return collect_paper_daily_equity_facts(reader, account, as_of_ms=as_of,
                                                    marks=marks or {}, max_mark_age_ms=AGE)
        finally:
            reader.close()

    def test_msk_midnight_boundary_and_fees(self):
        # Yesterday: +10 realized, 0.5 fees. Today: -4 realized, 0.25 fees.
        self.fill("Buy", "100", "1", D0 - 10 * MIN, fee="0.25")
        self.fill("Sell", "110", "1", D0 - 5 * MIN, fee="0.25")
        self.fill("Buy", "100", "1", D0 + MIN, fee="0.125")
        self.fill("Sell", "96", "1", D0 + 2 * MIN, fee="0.125")
        facts = self.facts(D0 + 3 * MIN)
        self.assertTrue(facts.data_available)
        self.assertEqual((facts.business_date_msk, facts.day_start_ms), ("2026-10-14", D0))
        self.assertEqual(facts.baseline_equity_usdt, Decimal("5009.5"))
        self.assertEqual(facts.current_adjusted_equity_usdt, Decimal("5005.25"))
        self.assertEqual(facts.daily_change_usdt, Decimal("-4.25"))
        self.assertEqual(facts.daily_change_pct, Decimal("-4.25") / Decimal("5009.5") * 100)
        self.assertEqual(facts.funding_model, "PAPER_SIMULATOR_NO_FUNDING")  # funding = 0 by model
        # The next MSK day re-bases on everything before its own 00:00.
        tomorrow = self.facts(D0 + eq.DAY_MS + MIN)
        self.assertEqual((tomorrow.business_date_msk, tomorrow.baseline_equity_usdt,
                          tomorrow.daily_change_usdt), ("2026-10-15", Decimal("5005.25"), Decimal("0")))

    def test_fill_at_exactly_midnight_belongs_to_the_new_day(self):
        self.fill("Buy", "100", "1", D0 - MIN)
        self.fill("Sell", "100", "1", D0)  # flat only from 00:00 itself: open AT the boundary
        self.assertEqual(self.facts(D0 + MIN).unavailability_reason, eq.POSITION_OPEN_AT_DAY_START)

    def test_position_open_at_boundary_makes_the_day_unavailable_even_if_flat_now(self):
        self.fill("Buy", "100", "2", D0 - MIN)
        self.fill("Sell", "105", "2", D0 + MIN)
        facts = self.facts(D0 + 2 * MIN)
        self.assertEqual((facts.data_available, facts.unavailability_reason, facts.baseline_equity_usdt),
                         (False, eq.POSITION_OPEN_AT_DAY_START, None))

    def test_open_position_partial_fills_and_unrealized_pnl(self):
        self.fill("Buy", "100", "1", D0 + MIN, fee="0.1")
        self.fill("Buy", "103", "2", D0 + 2 * MIN, fee="0.2")   # average 102
        self.fill("Sell", "104", "1", D0 + 3 * MIN, fee="0.1")  # realized +2, 2 left @ 102
        now = D0 + 4 * MIN
        facts = self.facts(now, {"AAAUSDT": MarkPrice(Decimal("101"), now - 1000)})
        # 5000 + 2 - 0.4 + 2 * (101 - 102)
        self.assertEqual(facts.current_adjusted_equity_usdt, Decimal("4999.6"))
        self.assertEqual(facts.daily_change_usdt, Decimal("-0.4"))

    def test_short_unrealized_is_symmetric(self):
        self.fill("Sell", "50", "4", D0 + MIN)
        now = D0 + 2 * MIN
        facts = self.facts(now, {"AAAUSDT": MarkPrice(Decimal("45"), now)})
        self.assertEqual(facts.daily_change_usdt, Decimal("20"))

    def test_missing_stale_or_invalid_mark_is_unavailable(self):
        self.fill("Buy", "100", "1", D0 + MIN)
        now = D0 + 2 * MIN
        self.assertEqual(self.facts(now).unavailability_reason, eq.MARK_PRICE_MISSING)
        self.assertEqual(self.facts(now, {"BBBUSDT": MarkPrice(Decimal("1"), now)}).unavailability_reason,
                         eq.MARK_PRICE_MISSING)
        stale = {"AAAUSDT": MarkPrice(Decimal("100"), now - AGE - 1)}
        self.assertEqual(self.facts(now, stale).unavailability_reason, eq.MARK_PRICE_STALE)
        future = {"AAAUSDT": MarkPrice(Decimal("100"), now + 1)}
        self.assertEqual(self.facts(now, future).unavailability_reason, eq.MARK_PRICE_INVALID)
        zero = {"AAAUSDT": MarkPrice(Decimal("0"), now)}
        self.assertEqual(self.facts(now, zero).unavailability_reason, eq.MARK_PRICE_INVALID)
        self.assertTrue(self.facts(now, {"AAAUSDT": MarkPrice(Decimal("100"), now - AGE)}).data_available)

    def test_duplicate_execution_changes_nothing_and_restart_is_stable(self):
        self.fill("Buy", "100", "1", D0 + MIN, fee="0.5", exec_id="dup-1")
        self.fill("Sell", "90", "1", D0 + 2 * MIN, fee="0.5", exec_id="dup-2")
        before = self.facts(D0 + 3 * MIN)
        repeat = self.fill("Sell", "90", "1", D0 + 2 * MIN, fee="0.5", exec_id="dup-2")
        self.assertEqual(repeat.value, "duplicate")
        self.store.close()
        self.store = SQLiteStore.open(self.path)  # restart: nothing persisted by the facts reader
        after = self.facts(D0 + 3 * MIN)
        self.assertEqual(before, after)
        self.assertEqual(after.daily_change_usdt, Decimal("-11"))

    def test_external_transfer_or_rewritten_account_is_unavailable(self):
        self.store._connection.execute("UPDATE paper_accounts SET equity_usdt='6000' WHERE trading_account_id='paper'")
        self.assertEqual(self.facts(D0 + MIN).unavailability_reason, eq.EXTERNAL_TRANSFER_UNSUPPORTED)
        self.store._connection.execute(
            "UPDATE paper_accounts SET equity_usdt='5000', version=2 WHERE trading_account_id='paper'")
        self.assertEqual(self.facts(D0 + MIN).unavailability_reason, eq.EXTERNAL_TRANSFER_UNSUPPORTED)

    def test_account_created_today_has_no_proven_baseline(self):
        self.store._connection.execute(f"UPDATE paper_accounts SET updated_at_ms={D0 + 1}")
        self.assertEqual(self.facts(D0 + MIN).unavailability_reason, eq.ACCOUNT_CREATED_AFTER_DAY_START)

    def test_contradicting_or_incomplete_journal_is_unavailable(self):
        self.fill("Buy", "100", "1", D0 - 2 * MIN)
        self.fill("Sell", "100", "1", D0 - MIN)
        self.assertTrue(self.facts(D0 + MIN).data_available)
        # A projection that the journal does not reproduce (e.g. a lost execution).
        self.store._connection.execute("UPDATE position_projections SET realized_pnl='3'")
        self.assertEqual(self.facts(D0 + MIN).unavailability_reason, eq.PROJECTION_MISMATCH)
        self.store._connection.execute("UPDATE position_projections SET realized_pnl='0'")
        self.store._connection.execute("DELETE FROM executions WHERE exec_id='e2'")
        self.assertEqual(self.facts(D0 + MIN).unavailability_reason, eq.PROJECTION_MISMATCH)

    def test_tied_timestamps_and_future_executions_fail_closed(self):
        self.fill("Buy", "100", "1", D0 - MIN)
        self.store._connection.execute(
            "INSERT INTO executions VALUES ('paper','linear','tie','o-tie','AAAUSDT','Sell','100','1','0',?)",
            (D0 - MIN,))
        self.assertEqual(self.facts(D0 + MIN).unavailability_reason, eq.EXECUTION_ORDER_AMBIGUOUS)
        self.store._connection.execute("DELETE FROM executions WHERE exec_id='tie'")
        self.assertEqual(self.facts(D0 - 2 * MIN).unavailability_reason, eq.EXECUTION_AFTER_AS_OF)

    def test_accounts_are_independent(self):
        self.fill("Buy", "100", "1", D0 - 2 * MIN)
        self.fill("Sell", "100", "1", D0 - MIN)
        self.store._connection.execute(
            "INSERT INTO executions VALUES ('bybit-x','linear','foreign','o-f','AAAUSDT','Buy','1','999','9',?)",
            (D0 + MIN,))
        self.store._connection.execute(
            "INSERT INTO position_projections VALUES ('bybit-x','linear','AAAUSDT',0,'Long','999','1','0','9','999','synced',1,10)")
        facts = self.facts(D0 + 2 * MIN)
        self.assertEqual((facts.data_available, facts.daily_change_usdt), (True, Decimal("0")))
        foreign = self.facts(D0 + 2 * MIN, account=TradingAccountId("bybit-x"))
        self.assertEqual(foreign.unavailability_reason, eq.ACCOUNT_UNAVAILABLE)

    def test_msk_day_start(self):
        self.assertEqual(eq.msk_day_start_ms(D0), ("2026-10-14", D0))
        self.assertEqual(eq.msk_day_start_ms(D0 - 1), ("2026-10-13", D0 - eq.DAY_MS))


if __name__ == "__main__":
    unittest.main()
