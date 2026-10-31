import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from robot_lifecycle_posts import (
    EVENT_CLOSED, EVENT_OPENED, REMEMBERED_TRADE_IDS, LifecycleEvent, LifecycleState,
    collect_new_lifecycle_events, format_lifecycle_caption, load_lifecycle_state,
    mark_notified, save_lifecycle_state,
)
from robot_position_view import PositionView
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore

INIT_MS = 1_000_000


def _trade(trade_id, entry_ms, exit_ms=None, *, symbol="SAGAUSDT", exit_reason=None):
    return SimpleNamespace(
        trade_id=trade_id, symbol=Symbol(symbol), entry_time_ms=entry_ms,
        exit_time_ms=exit_ms, exit_reason=exit_reason,
    )


def _store(*trades):
    # The real query already filters by time; the fake returns everything so the
    # function's own >= initialized_at_ms checks are exercised.
    return SimpleNamespace(load_robot_trades_with_events_since=lambda account, since: trades)


def _kinds(events):
    return [(event.kind, event.trade_id) for event in events]


class LifecycleStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "review_queue" / ".robot_lifecycle_notified"

    def test_first_run_initializes_at_now_and_persists(self):
        state = load_lifecycle_state(self.path, INIT_MS)
        self.assertEqual((state.initialized_at_ms, state.opened, state.closed), (INIT_MS, [], []))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["initialized_at_ms"], INIT_MS)

    def test_restart_keeps_initialization_time_and_sent_ids(self):
        state = load_lifecycle_state(self.path, INIT_MS)
        mark_notified(state, LifecycleEvent(EVENT_OPENED, "t1", "SAGAUSDT", INIT_MS + 1))
        save_lifecycle_state(self.path, state)

        restarted = load_lifecycle_state(self.path, INIT_MS + 999_999)

        self.assertEqual(restarted.initialized_at_ms, INIT_MS)
        self.assertEqual(restarted.opened, ["t1"])

    def test_damaged_file_reinitializes_at_now(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{broken", encoding="utf-8")
        self.assertEqual(load_lifecycle_state(self.path, INIT_MS + 5).initialized_at_ms, INIT_MS + 5)

    def test_mark_notified_keeps_last_200_per_kind(self):
        state = LifecycleState(INIT_MS)
        for index in range(REMEMBERED_TRADE_IDS + 5):
            mark_notified(state, LifecycleEvent(EVENT_CLOSED, f"t{index}", "X", INIT_MS))
        self.assertEqual(len(state.closed), REMEMBERED_TRADE_IDS)
        self.assertEqual(state.closed[0], "t5")
        self.assertEqual(state.opened, [])


class CollectLifecycleEventsTests(unittest.TestCase):
    def test_first_run_does_not_backfill_history(self):
        store = _store(
            _trade("old-closed", INIT_MS - 50, INIT_MS - 10, exit_reason="STOP"),
            _trade("old-open", INIT_MS - 5),
        )
        self.assertEqual(collect_new_lifecycle_events(store, LifecycleState(INIT_MS)), [])

    def test_trade_opened_before_init_reports_only_its_close(self):
        store = _store(_trade("t1", INIT_MS - 5, INIT_MS + 10, exit_reason="TAKE"))
        events = collect_new_lifecycle_events(store, LifecycleState(INIT_MS))
        self.assertEqual(_kinds(events), [(EVENT_CLOSED, "t1")])
        self.assertEqual(events[0].exit_reason, "TAKE")

    def test_open_precedes_close_and_events_are_time_ordered(self):
        store = _store(
            _trade("t1", INIT_MS + 10, INIT_MS + 10, exit_reason="STOP"),  # same-ms open/close
            _trade("t2", INIT_MS + 5),
            _trade("t3", INIT_MS + 1, INIT_MS + 20, exit_reason="TAKE"),
        )
        events = collect_new_lifecycle_events(store, LifecycleState(INIT_MS))
        self.assertEqual(_kinds(events), [
            (EVENT_OPENED, "t3"), (EVENT_OPENED, "t2"), (EVENT_OPENED, "t1"),
            (EVENT_CLOSED, "t1"), (EVENT_CLOSED, "t3"),
        ])

    def test_restart_skips_sent_and_resends_unsent(self):
        store = _store(_trade("t1", INIT_MS + 1, INIT_MS + 20, exit_reason="STOP"), _trade("t2", INIT_MS + 2))
        state = LifecycleState(INIT_MS, opened=["t1", "t2"], closed=[])
        # t1 "открыта" and t2 were already sent; t1 "закрыта" was not (e.g. listener was down).
        self.assertEqual(_kinds(collect_new_lifecycle_events(store, state)), [(EVENT_CLOSED, "t1")])
        state.closed.append("t1")
        self.assertEqual(collect_new_lifecycle_events(store, state), [])


class LifecycleCaptionTests(unittest.TestCase):
    def _view(self, fees_usdt=Decimal("0.0277"), **trade_overrides):
        # Stored fees_costs_usdt / realized_pnl_pct (closing leg only) must not be shown.
        trade = SimpleNamespace(
            exit_price=Decimal("0.0249"), exit_reason="STOP",
            realized_pnl_usdt=Decimal("-0.5"), fees_costs_usdt=Decimal("0.0137"),
            realized_pnl_pct=Decimal("-2.02"), entry_quantity=Decimal("1000"),
            average_entry=Decimal("0.0254"),
        )
        for key, value in trade_overrides.items():
            setattr(trade, key, value)
        return PositionView(
            symbol="SAGAUSDT", direction="LONG", is_open=False, quantity=Decimal("1000"),
            average_entry=Decimal("0.0254"), stop_price=Decimal("0.0249"),
            take_price=Decimal("0.0284"), pattern="Falling Wedge", trade=trade,
            fees_usdt=fees_usdt,
        )

    def test_opened_caption(self):
        view = PositionView(
            symbol="SAGAUSDT", direction="LONG", is_open=True, quantity=Decimal("100"),
            average_entry=Decimal("0.0254"), stop_price=Decimal("0.0249"),
            take_price=Decimal("0.0284"), pattern="Falling Wedge", trade=SimpleNamespace(),
        )
        caption = format_lifecycle_caption(LifecycleEvent(EVENT_OPENED, "t1", "SAGAUSDT", 1), view)
        self.assertTrue(caption.startswith("🤖 Сделка открыта\n\nSAGAUSDT · LONG"))
        for text in ("Размер: 100", "Средний вход: 0.0254", "STOP: 0.0249", "TAKE: 0.0284",
                     "Паттерн: Falling Wedge"):
            self.assertIn(text, caption)

    def test_all_patterns_number_only_proven_filled_trade_attempts(self):
        from dataclasses import replace
        view = PositionView(
            symbol="SAGAUSDT", direction="LONG", is_open=True, quantity=Decimal("100"),
            average_entry=Decimal("0.0254"), stop_price=Decimal("0.0249"),
            take_price=Decimal("0.0284"), pattern="Falling Wedge", trade=SimpleNamespace(),
        )
        event = LifecycleEvent(EVENT_OPENED, "t1", "SAGAUSDT", 1)
        self.assertTrue(format_lifecycle_caption(event, view).startswith("🤖 Сделка открыта"))
        for index, label in ((2, "Повторный перезаход №1"), (3, "Повторный перезаход №2")):
            caption = format_lifecycle_caption(event, replace(view, reentry_attempt_index=index))
            self.assertTrue(caption.startswith("🤖 " + label))
        self.assertNotIn("Повторный", format_lifecycle_caption(
            event, replace(view, reentry_attempt_index=None)))

    def test_mirror_lifecycle_uses_source_type_and_no_unproven_role_switch(self):
        from dataclasses import replace
        view = PositionView(
            symbol="SAGAUSDT", direction="SHORT", is_open=True, quantity=Decimal("100"),
            average_entry=Decimal("0.0254"), stop_price=Decimal("0.0249"),
            take_price=Decimal("0.0284"), pattern="MIRROR", trade=SimpleNamespace(),
            mirror_campaign=True, mirror_timeframe="5", mirror_level_source="swing_zone",
            reentry_attempt_index=2,
        )
        opened = LifecycleEvent(EVENT_OPENED, "t1", "SAGAUSDT", 1)
        self.assertEqual(format_lifecycle_caption(opened, view),
            "🪞 MIRROR · SAGAUSDT · 5m\nГоризонтальный уровень · смена роли не подтверждена\nПовторный перезаход №1")
        closed = LifecycleEvent(EVENT_CLOSED, "t1", "SAGAUSDT", 2, "STOP")
        self.assertIn("Сделка закрыта · по стопу", format_lifecycle_caption(closed, view))
        self.assertIn("Зеркальный уровень", format_lifecycle_caption(opened,
            replace(view, mirror_retest_confirmed=True)))
        pattern = replace(view, mirror_level_source="pattern_boundary",
                          mirror_pattern="Rising Wedge", mirror_retest_confirmed=False)
        self.assertIn("Граница паттерна · Rising Wedge", format_lifecycle_caption(opened, pattern))

    def test_closed_caption_reason_and_result(self):
        for reason, label in (
            ("STOP", "по стопу"), ("TAKE", "по тейку"),
            ("EMERGENCY_CLOSE", "аварийное закрытие"), ("MANUAL", "MANUAL"),
        ):
            with self.subTest(reason=reason):
                event = LifecycleEvent(EVENT_CLOSED, "t1", "SAGAUSDT", 1, reason)
                caption = format_lifecycle_caption(event, self._view(exit_reason=reason))
                self.assertTrue(caption.startswith(f"🤖 Сделка закрыта · {label}\n\n"))
                self.assertIn(f"Выход: 0.0249 ({label})", caption)
                # (-0.5 - 0.0277) / (1000 * 0.0254) * 100 = -2.08
                self.assertIn(
                    "Итог: -0.5 USDT (до комиссий), комиссии 0.0277 USDT (вход + выход), "
                    "-2.08% (после комиссий)",
                    caption,
                )
                self.assertNotIn("PnL:", caption)
                self.assertLessEqual(len(caption), 1024)

    def test_closed_caption_without_fees(self):
        event = LifecycleEvent(EVENT_CLOSED, "t1", "SAGAUSDT", 1, "TAKE")
        caption = format_lifecycle_caption(event, self._view(fees_usdt=None))
        self.assertIn("комиссии — (вход + выход), — (после комиссий)", caption)


class MirrorChartDeliveryTests(unittest.TestCase):
    def test_missing_mirror_chart_is_not_marked_delivered(self):
        from unittest.mock import patch
        import telegram_monitoring as monitoring
        view = PositionView(
            symbol="SAGAUSDT", direction="LONG", is_open=True, quantity=Decimal("1"),
            average_entry=Decimal("1"), stop_price=Decimal("0.9"),
            take_price=Decimal("1.2"), pattern="MIRROR",
            trade=SimpleNamespace(), mirror_campaign=True,
        )
        with patch.object(monitoring, "render_position_chart", side_effect=ValueError("no candles")), \
             patch.object(monitoring, "_send_text") as text_sender:
            self.assertFalse(monitoring._send_chart_card(
                "123", view, None, "card", {"inline_keyboard": []}, require_chart=True))
            text_sender.assert_not_called()

    def test_failed_mirror_photo_is_not_counted_as_successful_text(self):
        from unittest.mock import patch
        import telegram_monitoring as monitoring
        view = PositionView(
            symbol="SAGAUSDT", direction="LONG", is_open=True, quantity=Decimal("1"),
            average_entry=Decimal("1"), stop_price=Decimal("0.9"),
            take_price=Decimal("1.2"), pattern="MIRROR",
            trade=SimpleNamespace(), mirror_campaign=True,
        )
        with patch.object(monitoring, "render_position_chart", return_value="chart.png"), \
             patch.object(monitoring.telegram_bot, "send_photo", side_effect=RuntimeError("gateway")), \
             patch.object(monitoring, "_send_text") as text_sender:
            self.assertFalse(monitoring._send_chart_card(
                "123", view, None, "card", {"inline_keyboard": []}, require_chart=True))
            text_sender.assert_not_called()


class MirrorAttachmentClassificationTests(unittest.TestCase):
    def test_only_attached_execution_is_mirror_not_not_attached_box(self):
        from unittest.mock import patch
        from robot_position_view import load_position_view

        trade = SimpleNamespace(
            trade_id="t1", candidate_id="c1", symbol=Symbol("SAGAUSDT"),
            entry_time_ms=1000, exit_time_ms=2000, direction="LONG",
            pattern="IKIGAI_BOX", entry_quantity=Decimal("1"),
            average_entry=Decimal("100"), stop_price=Decimal("98"),
            take_price=Decimal("105"), exit_price=Decimal("103"),
            exit_reason="TAKE", realized_pnl_usdt=Decimal("3"),
            fees_costs_usdt=Decimal("0.1"))
        metadata = {
            "decision": "NOT_ATTACHED", "mirror_level_source": "swing_zone",
            "mirror_timeframe": "5", "boundary": {"anchor_price": "100"},
        }
        candidate = SimpleNamespace(
            robot_state={"execution": {"mirror": metadata}},
            signal_snapshot={"pattern": "IKIGAI_BOX"},
        )
        store = SimpleNamespace(
            get_position_projection=lambda key: None,
            get_robot_trade=lambda trade_id: trade,
            get_robot_candidate=lambda candidate_id: candidate,
            get_robot_reentry_attempt_index=lambda account, candidate_id: None,
        )
        with patch("robot_position_view._trade_markers", return_value=((), None)):
            not_attached = load_position_view(store, "SAGAUSDT", trade_id="t1", now_ms=2000)
            self.assertFalse(not_attached.mirror_campaign)
            self.assertIsNone(not_attached.mirror_level_source)
            self.assertIsNone(not_attached.mirror_boundary)
            self.assertNotIn("🪞 MIRROR", format_lifecycle_caption(
                LifecycleEvent(EVENT_OPENED, "t1", "SAGAUSDT", 1000), not_attached))
            metadata["decision"] = "ATTACHED"
            attached = load_position_view(store, "SAGAUSDT", trade_id="t1", now_ms=2000)
            self.assertTrue(attached.mirror_campaign)
            self.assertEqual(attached.mirror_level_source, "swing_zone")
            self.assertIn("🪞 MIRROR", format_lifecycle_caption(
                LifecycleEvent(EVENT_OPENED, "t1", "SAGAUSDT", 1000), attached))
            metadata.pop("decision")
            absent = load_position_view(store, "SAGAUSDT", trade_id="t1", now_ms=2000)
            self.assertFalse(absent.mirror_campaign)


class CampaignHistoryMarkerTests(unittest.TestCase):
    def test_only_closed_prior_same_campaign_fills_are_added(self):
        from unittest.mock import patch
        from robot_position_view import TradeMarker, load_position_view

        current = SimpleNamespace(
            trade_id="current", candidate_id="candidate-2", symbol=Symbol("SAGAUSDT"),
            entry_time_ms=3000, exit_time_ms=4000, direction="LONG", pattern="MIRROR",
            entry_quantity=Decimal("1"), average_entry=Decimal("101"),
            stop_price=Decimal("99"), take_price=Decimal("105"), exit_price=Decimal("102"))
        prior = SimpleNamespace(
            trade_id="prior", candidate_id="candidate-1", symbol=Symbol("SAGAUSDT"),
            entry_time_ms=1000, exit_time_ms=2000)
        unfinished = SimpleNamespace(
            trade_id="unfinished", candidate_id="candidate-3", symbol=Symbol("SAGAUSDT"),
            entry_time_ms=1500, exit_time_ms=None)
        source = SimpleNamespace(robot_state={"execution": {"mirror": {
            "decision": "ATTACHED", "mirror_level_source": "swing_zone",
            "mirror_timeframe": "5"}}},
            signal_snapshot=None)
        store = SimpleNamespace(
            get_position_projection=lambda key: None,
            get_robot_trade=lambda trade_id: current,
            get_robot_candidate=lambda candidate_id: source,
            get_robot_reentry_attempt_index=lambda account, candidate_id: 2,
            load_robot_reentry_campaign_trades=lambda account, candidate_id:
                (prior, current, unfinished),
        )
        filled_old = TradeMarker(1200, Decimal("100"), "Buy", True)
        hollow_old = TradeMarker(1250, Decimal("99"), "Buy", False)
        filled_current = TradeMarker(3100, Decimal("101"), "Buy", True)
        def fake_markers(store, account, trade, candidate, *, now_ms):
            if trade.trade_id == "prior":
                return (filled_old, hollow_old), Decimal("0.1")
            return (filled_current,), Decimal("0.2")

        with patch("robot_position_view._trade_markers", side_effect=fake_markers):
            view = load_position_view(store, "SAGAUSDT", trade_id="current", now_ms=4000)
        self.assertEqual(view.markers, (filled_old, filled_current))
        self.assertEqual(view.fees_usdt, Decimal("0.2"))  # no prior fees in current trade PnL


class LifecycleStoreQueryTests(unittest.TestCase):
    """The new read-only store query against a real SQLite schema."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.account = TradingAccountId("paper")
        self.store = SQLiteStore.open(Path(self.temp.name) / "paper.sqlite3")
        self.addCleanup(self.store.close)

    def _open(self, candidate_id, entry_ms):
        self.store.create_robot_candidate(
            candidate_id=candidate_id, trading_account_id=self.account, symbol=Symbol("SAGAUSDT"),
            status="APPROVED", signal_snapshot={"pattern": "Falling Wedge", "id": candidate_id},
            approved_at_ms=100, updated_at_ms=100,
        )
        self.store.create_robot_trade(
            trade_id=f"robot-trade-{candidate_id}", trading_account_id=self.account,
            candidate_id=candidate_id, symbol=Symbol("SAGAUSDT"), direction="LONG",
            pattern="Falling Wedge", source_timeframe="1", signal_time_ms=100,
            entry_time_ms=entry_ms, entry_path="LIMIT", actual_wv=Decimal("1"),
            average_entry=Decimal("100"), stop_price=Decimal("98"), take_price=Decimal("105"),
            entry_quantity=Decimal("1"), entry_position_version=1, created_at_ms=entry_ms,
        )

    def _close(self, candidate_id, exit_ms):
        self.store.close_robot_trade(
            f"robot-trade-{candidate_id}", exit_time_ms=exit_ms, exit_price=Decimal("98"),
            exit_reason="STOP", realized_pnl_usdt=Decimal("-2"), realized_pnl_pct=Decimal("-2.1"),
            fees_costs_usdt=Decimal("0.1"), updated_at_ms=exit_ms,
        )

    def test_query_returns_trades_opened_or_closed_since(self):
        self._open("history", 500)
        self._close("history", 600)
        self._open("closed-after", 800)
        self._close("closed-after", 1200)
        self._open("opened-after", 1500)

        trades = self.store.load_robot_trades_with_events_since(self.account, 1000)
        self.assertEqual(
            [trade.trade_id for trade in trades],
            ["robot-trade-closed-after", "robot-trade-opened-after"],
        )
        events = collect_new_lifecycle_events(self.store, LifecycleState(1000))
        self.assertEqual(_kinds(events), [
            (EVENT_CLOSED, "robot-trade-closed-after"), (EVENT_OPENED, "robot-trade-opened-after"),
        ])


if __name__ == "__main__":
    unittest.main()
