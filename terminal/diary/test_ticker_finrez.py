"""Focused first-screen Finrez ranking and Moscow-period regressions."""
from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from terminal.diary.ticker_finrez import (
    EpisodeFactsNotFound, EpisodeFactsSourceChanged,
    aggregate_ticker_pnl, period_start_ms, project_paper_closed_episode_facts,
    project_paper_ticker_pnl,
)
from terminal.diary.models import (
    AllocationRole, DiaryEnvironment, ExecutionAllocation, TradeEpisode, TradeEpisodeId,
)
from terminal.diary.scoped_statistics_archive import StatisticsScopeError
from terminal.diary.scoped_statistics_reporter import PaperSourceSnapshot
from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, OrderId, OrderSide, Origin, PositionKey, PositionSide,
    Price, Quantity, Symbol, TradingAccountId,
)


_MSK = ZoneInfo("Europe/Moscow")


def _ms(day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(2026, 11, day, hour, minute, tzinfo=_MSK).timestamp() * 1000)


def _episode(symbol: str, gross: str, fees: str, closed_at: int | None):
    return SimpleNamespace(
        position_key=SimpleNamespace(symbol=SimpleNamespace(value=symbol)),
        realized_price_pnl=Decimal(gross),
        execution_fees=Decimal(fees),
        closed_at_ms=closed_at,
    )


class FinrezRankingTests(unittest.TestCase):
    def test_today_starts_at_moscow_midnight_not_device_timezone(self):
        now = _ms(9, 12)
        self.assertEqual(period_start_ms(period="TODAY", now_ms=now), _ms(9, 0))
        start, rows = aggregate_ticker_pnl(
            [
                _episode("BTCUSDT", "100", "1", _ms(8, 23, 59)),
                _episode("BTCUSDT", "-10", "0.5", _ms(9, 0)),
                _episode("ETHUSDT", "7", "1", _ms(9, 11)),
                _episode("DOGEUSDT", "100", "0", _ms(9, 12, 1)),
                _episode("ADAUSDT", "100", "0", None),
            ], period="TODAY", now_ms=now,
        )
        self.assertEqual(start, _ms(9, 0))
        self.assertEqual(rows, [
            {"symbol": "ETHUSDT", "pnl_usdt": "6", "trade_count": 1},
            {"symbol": "BTCUSDT", "pnl_usdt": "-10.5", "trade_count": 1},
        ])

    def test_all_time_sums_each_ticker_and_subtracts_fees_once(self):
        _, rows = aggregate_ticker_pnl([
            _episode("BTCUSDT", "5", "1", _ms(8, 23)),
            _episode("ETHUSDT", "-1", "0.2", _ms(9, 0)),
            _episode("BTCUSDT", "-2", "0.5", _ms(9, 10)),
            _episode("XRPUSDT", "0", "0", _ms(9, 10)),
        ], period="ALL", now_ms=_ms(9, 11))
        self.assertEqual(rows, [
            {"symbol": "BTCUSDT", "pnl_usdt": "1.5", "trade_count": 2},
            {"symbol": "XRPUSDT", "pnl_usdt": "0", "trade_count": 1},
            {"symbol": "ETHUSDT", "pnl_usdt": "-1.2", "trade_count": 1},
        ])

    def test_calendar_periods_use_moscow_boundaries(self):
        now = _ms(12, 12)  # Thursday 12 Nov 2026
        self.assertEqual(period_start_ms(period="DAY", now_ms=now), _ms(12, 0))
        self.assertEqual(period_start_ms(period="TODAY", now_ms=now), _ms(12, 0))
        self.assertEqual(period_start_ms(period="WEEK", now_ms=now), _ms(9, 0))
        self.assertEqual(period_start_ms(period="MONTH", now_ms=now),
                         int(datetime(2026, 11, 1, tzinfo=_MSK).timestamp() * 1000))
        self.assertEqual(period_start_ms(period="YEAR", now_ms=now),
                         int(datetime(2026, 1, 1, tzinfo=_MSK).timestamp() * 1000))
        self.assertEqual(period_start_ms(period="ALL", now_ms=now), 0)

    def test_all_calendar_periods_filter_by_actual_episode_close_time(self):
        now = _ms(12, 12)
        rows = [
            _episode("BTCUSDT", "1", "0", _ms(12, 2)),
            _episode("BTCUSDT", "2", "0", _ms(9, 0)),
            _episode("BTCUSDT", "4", "0", _ms(8, 23)),
        ]
        expected = {"DAY": ("1", 1), "WEEK": ("3", 2),
                    "MONTH": ("7", 3), "YEAR": ("7", 3), "ALL": ("7", 3)}
        for period, (pnl, count) in expected.items():
            _, ranked = aggregate_ticker_pnl(rows, period=period, now_ms=now)
            self.assertEqual(ranked, [{"symbol": "BTCUSDT",
                                       "pnl_usdt": pnl, "trade_count": count}])

    def test_rejects_unknown_period_and_negative_time(self):
        for period, now in [("UNKNOWN", _ms(9, 12)), ("TODAY", -1)]:
            with self.assertRaises(ValueError):
                period_start_ms(period=period, now_ms=now)




def _scoped_episode(
    suffix: str, symbol: str, roles_and_origins, *, opened_at=None, closed_at=None,
):
    """Typed immutable episode and exact per-execution controller evidence."""
    episode_id = TradeEpisodeId(suffix)
    opened_at = opened_at if opened_at is not None else _ms(9, 9)
    allocations = []
    origins = {}
    for index, (role, origin) in enumerate(roles_and_origins):
        key = ExecutionDedupKey(TradingAccountId("paper"), Category.LINEAR, ExecutionId(f"{suffix}-{index}"))
        allocations.append(ExecutionAllocation(
            execution_key=key, trade_episode_id=episode_id, role=role,
            quantity=Decimal("1"), fee=Decimal("0.1"), occurred_at_ms=opened_at + index,
        ))
        origins[key] = origin
    episode = TradeEpisode(
        trade_episode_id=episode_id,
        position_key=PositionKey(TradingAccountId("paper"), Category.LINEAR, Symbol(symbol), 0),
        side=PositionSide.LONG, environment=DiaryEnvironment.PAPER,
        opened_at_ms=opened_at, closed_at_ms=closed_at if closed_at is not None else _ms(9, 10),
        opening_price=Price(Decimal("100")), average_entry=Price(Decimal("100")),
        open_quantity=Quantity(Decimal("0")), realized_price_pnl=Decimal("5"),
        execution_fees=Decimal("0.1") * len(allocations), allocations=tuple(allocations),
    )
    return episode, origins


class FinrezMixedControllerTests(unittest.TestCase):
    def test_robot_manual_close_is_visible_but_not_counted_as_autonomous_robot_pnl(self):
        pure, p = _scoped_episode("robot", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        assisted, a = _scoped_episode("assisted", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.REDUCE, Origin.TERMINAL_MANUAL),
            (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        manual, m = _scoped_episode("manual", "ETHUSDT", [
            (AllocationRole.OPEN, Origin.TERMINAL_MANUAL),
            (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        snapshot = PaperSourceSnapshot(4, (pure, assisted, manual), {**p, **a, **m})
        robot = project_paper_ticker_pnl(
            snapshot, account_id="paper", owner="ROBOT", period="TODAY", now_ms=_ms(9, 12),
        )
        self.assertEqual(robot["tickers"], [
            {"symbol": "BTCUSDT", "pnl_usdt": "4.8", "trade_count": 1},
        ])
        self.assertEqual(robot["manual_interventions"], [
            {"symbol": "BTCUSDT", "pnl_usdt": "4.7", "trade_count": 1},
        ])
        self.assertEqual(robot["attribution_coverage"], {
            "status": "COMPLETE",
            "excluded_unattributed_episode_count": 0,
            "excluded_unattributed_execution_count": 0,
        })
        manual_report = project_paper_ticker_pnl(
            snapshot, account_id="paper", owner="MANUAL", period="ALL", now_ms=_ms(9, 12),
        )
        self.assertEqual(manual_report["tickers"], [
            {"symbol": "ETHUSDT", "pnl_usdt": "4.8", "trade_count": 1},
        ])
        self.assertEqual(manual_report["manual_interventions"], [])

    def test_assisted_only_is_not_fabricated_as_zero_trades(self):
        assisted, origins = _scoped_episode("assisted", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        snapshot = PaperSourceSnapshot(3, (assisted,), origins)
        report = project_paper_ticker_pnl(
            snapshot, account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
        )
        self.assertEqual(report["tickers"], [])
        self.assertEqual(report["manual_interventions"][0]["trade_count"], 1)

    def test_robot_open_manual_increases_robot_close_is_joint_not_owned_pnl(self):
        # Exact historical role/controller pattern: two robot additions,
        # two manual additions, one robot addition, then robot final close.
        joint, joint_origins = _scoped_episode("joint", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT),
            (AllocationRole.INCREASE, Origin.ROBOT),
            (AllocationRole.INCREASE, Origin.ROBOT),
            (AllocationRole.INCREASE, Origin.TERMINAL_MANUAL),
            (AllocationRole.INCREASE, Origin.TERMINAL_MANUAL),
            (AllocationRole.INCREASE, Origin.ROBOT),
            (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        robot, robot_origins = _scoped_episode("pure-robot", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        manual, manual_origins = _scoped_episode("pure-manual", "ETHUSDT", [
            (AllocationRole.OPEN, Origin.TERMINAL_MANUAL),
            (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        snapshot = PaperSourceSnapshot(
            20, (robot, joint, manual), {**joint_origins, **robot_origins, **manual_origins},
        )
        for period in ("TODAY", "ALL"):
            with self.subTest(period=period):
                robot_report = project_paper_ticker_pnl(
                    snapshot, account_id="paper", owner="ROBOT", period=period, now_ms=_ms(9, 12),
                )
                manual_report = project_paper_ticker_pnl(
                    snapshot, account_id="paper", owner="MANUAL", period=period, now_ms=_ms(9, 12),
                )
                joint_rows = [{"symbol": "BTCUSDT", "pnl_usdt": "4.3", "trade_count": 1}]
                self.assertEqual(robot_report["joint_management"], joint_rows)
                self.assertEqual(manual_report["joint_management"], joint_rows)
                self.assertEqual(robot_report["tickers"], [
                    {"symbol": "BTCUSDT", "pnl_usdt": "4.8", "trade_count": 1},
                ])
                self.assertEqual(manual_report["tickers"], [
                    {"symbol": "ETHUSDT", "pnl_usdt": "4.8", "trade_count": 1},
                ])
                self.assertEqual(robot_report["manual_interventions"], [])
                self.assertEqual(manual_report["manual_interventions"], [])
                self.assertEqual(robot_report["attribution_coverage"]["status"], "COMPLETE")
                self.assertEqual(manual_report["attribution_coverage"]["status"], "COMPLETE")

    def test_joint_management_outside_today_does_not_appear_or_block(self):
        historical, origins = _scoped_episode(
            "joint-yesterday", "BTCUSDT", [
                (AllocationRole.OPEN, Origin.ROBOT),
                (AllocationRole.INCREASE, Origin.TERMINAL_MANUAL),
                (AllocationRole.CLOSE, Origin.ROBOT),
            ], opened_at=_ms(8, 23, 58), closed_at=_ms(8, 23, 59),
        )
        snap = PaperSourceSnapshot(10, (historical,), origins)
        today = project_paper_ticker_pnl(
            snap, account_id="paper", owner="ROBOT", period="TODAY", now_ms=_ms(9, 12),
        )
        self.assertEqual(today["joint_management"], [])
        all_report = project_paper_ticker_pnl(
            snap, account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
        )
        self.assertEqual(all_report["joint_management"], [
            {"symbol": "BTCUSDT", "pnl_usdt": "4.7", "trade_count": 1},
        ])


    def test_closed_episode_locators_are_controller_proven_and_not_automatic_replay(self):
        pure, pure_origins = _scoped_episode("robot", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        assisted, assisted_origins = _scoped_episode("assisted", "ETHUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        joint, joint_origins = _scoped_episode("joint", "XRPUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT),
            (AllocationRole.INCREASE, Origin.TERMINAL_MANUAL),
            (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        manual, manual_origins = _scoped_episode("manual", "SOLUSDT", [
            (AllocationRole.OPEN, Origin.TERMINAL_MANUAL),
            (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        unknown, _ = _scoped_episode("unknown", "DOGEUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        source = PaperSourceSnapshot(15, (pure, assisted, joint, manual, unknown), {
            **pure_origins, **assisted_origins, **joint_origins, **manual_origins,
        })
        robot = project_paper_ticker_pnl(
            source, account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
        )
        rows = robot["closed_episodes"]
        # Real domain PositionSide values are "Long"/"Short"; HTTP requires
        # the uppercase contract accepted by the mobile Deals validator.
        self.assertTrue(all(r["side"] == "LONG" for r in rows))
        self.assertEqual({r["trade_episode_id"]: r["cohort"] for r in rows}, {
            "robot": "ROBOT",
            "assisted": "ROBOT_MANUAL_CLOSE",
            "joint": "JOINT_MANAGEMENT",
        })
        self.assertEqual([r["trade_episode_id"] for r in rows], sorted(
            r["trade_episode_id"] for r in rows
        ))  # same close time: stable ID ordering
        self.assertTrue(all(r["replay_evidence"] == "EPISODE_INDEX_ONLY" for r in rows))
        self.assertEqual(rows[0]["execution_count"], 2)
        self.assertEqual(rows[0]["pnl_usdt"], "4.8")
        self.assertNotIn("unknown", [r["trade_episode_id"] for r in rows])
        self.assertNotIn("manual", [r["trade_episode_id"] for r in rows])
        self.assertEqual(robot["attribution_coverage"]["status"], "PARTIAL")

        terminal = project_paper_ticker_pnl(
            source, account_id="paper", owner="MANUAL", period="ALL", now_ms=_ms(9, 12),
        )
        self.assertEqual({r["trade_episode_id"]: r["cohort"] for r in terminal["closed_episodes"]}, {
            "manual": "MANUAL", "joint": "JOINT_MANAGEMENT",
        })

    def test_closed_episode_locators_respect_close_time_and_preserve_exact_pnl(self):
        old, origins_old = _scoped_episode(
            "yesterday", "BTCUSDT",
            [(AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT)],
            opened_at=_ms(8, 23, 50), closed_at=_ms(8, 23, 59),
        )
        current, origins_current = _scoped_episode(
            "today", "BTCUSDT",
            [(AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT)],
        )
        source = PaperSourceSnapshot(12, (old, current), {**origins_old, **origins_current})
        today = project_paper_ticker_pnl(
            source, account_id="paper", owner="ROBOT", period="TODAY", now_ms=_ms(9, 12),
        )
        self.assertEqual([r["trade_episode_id"] for r in today["closed_episodes"]], ["today"])
        self.assertEqual(today["closed_episodes"][0]["pnl_usdt"], "4.8")

    def test_other_mixed_ownership_remains_blocked(self):
        cases = [
            [(AllocationRole.OPEN, Origin.TERMINAL_MANUAL), (AllocationRole.CLOSE, Origin.ROBOT)],
            [(AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.INCREASE, Origin.TERMINAL_MANUAL),
             (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL)],
            [(AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.REDUCE, Origin.TERMINAL_MANUAL),
             (AllocationRole.CLOSE, Origin.ROBOT)],
        ]
        for i, roles in enumerate(cases):
            mixed, origins = _scoped_episode(f"mixed-{i}", "BTCUSDT", roles)
            with self.subTest(case=i), self.assertRaisesRegex(StatisticsScopeError, "mixed_controller"):
                project_paper_ticker_pnl(
                    PaperSourceSnapshot(2, (mixed,), origins),
                    account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
                )

    def test_unknown_episode_is_excluded_and_reported_as_partial_not_zero(self):
        unknown, origins = _scoped_episode("unknown", "ETHUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        origins.clear()
        report = project_paper_ticker_pnl(
            PaperSourceSnapshot(2, (unknown,), origins),
            account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
        )
        self.assertEqual(report["tickers"], [])
        self.assertEqual(report["manual_interventions"], [])
        self.assertEqual(report["attribution_coverage"], {
            "status": "PARTIAL",
            "excluded_unattributed_episode_count": 1,
            "excluded_unattributed_execution_count": 2,
        })

    def test_today_ignores_unattributed_historical_episode_outside_period(self):
        current, current_origins = _scoped_episode("current", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        historical, historical_origins = _scoped_episode(
            "historical", "ETHUSDT",
            [(AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT)],
            opened_at=_ms(8, 23, 58),
            closed_at=_ms(8, 23, 59),
        )
        historical_origins.clear()
        report = project_paper_ticker_pnl(
            PaperSourceSnapshot(5, (historical, current), {
                **historical_origins, **current_origins,
            }),
            account_id="paper", owner="ROBOT", period="TODAY", now_ms=_ms(9, 12),
        )
        self.assertEqual(report["tickers"], [
            {"symbol": "BTCUSDT", "pnl_usdt": "4.8", "trade_count": 1},
        ])
        self.assertEqual(report["attribution_coverage"], {
            "status": "COMPLETE",
            "excluded_unattributed_episode_count": 0,
            "excluded_unattributed_execution_count": 0,
        })


class ClosedEpisodeFactsTests(unittest.TestCase):
    def _snapshot(self):
        identity = "te_" + "a" * 24
        episode, origins = _scoped_episode(identity, "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT),
            (AllocationRole.INCREASE, Origin.ROBOT),
            (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        executions = tuple(
            Execution(
                dedup_key=item.execution_key,
                order_id=OrderId("order-" + str(index)),
                symbol=episode.position_key.symbol,
                side=OrderSide.BUY if item.role in (AllocationRole.OPEN, AllocationRole.INCREASE) else OrderSide.SELL,
                price=Price(Decimal("100") + index),
                quantity=Quantity(item.quantity),
                fee=item.fee,
                exchange_timestamp_ms=item.occurred_at_ms,
            )
            for index, item in enumerate(episode.allocations)
        )
        return identity, PaperSourceSnapshot(8, (episode,), origins, executions=executions)

    def test_exports_original_fill_price_orders_and_controller_without_fabricating_decisions(self):
        identity, snapshot = self._snapshot()
        doc = project_paper_closed_episode_facts(
            snapshot, account_id="paper", owner="ROBOT",
            trade_episode_id=identity, source_revision=8, now_ms=_ms(9, 12),
        )
        self.assertEqual(doc["schema"], "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1")
        self.assertEqual(doc["namespace"], "PAPER_READ_ONLY")
        self.assertEqual(doc["cohort"], "ROBOT")
        self.assertEqual(doc["side"], "LONG")
        self.assertEqual(doc["source_revision"], 8)
        self.assertEqual(doc["pnl_usdt"], "4.7")
        self.assertEqual(doc["execution_allocations"], [
            {
                "execution_id": f"{identity}-{index}", "order_id": f"order-{index}",
                "order_side": "Buy" if index < 2 else "Sell",
                "execution_price": str(100 + index),
                "allocated_quantity": "1", "allocated_fee": "0.1",
                "occurred_at_ms": snapshot.episodes[0].allocations[index].occurred_at_ms,
                "allocation_role": ["OPEN", "INCREASE", "CLOSE"][index],
                "controller": "ROBOT",
            }
            for index in range(3)
        ])
        self.assertEqual(doc["replay_evidence"], "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES")
        self.assertNotIn("candles", doc)
        self.assertNotIn("strategy", doc)
        self.assertNotIn("robot_decisions", doc)

    def test_fails_closed_for_stale_index_wrong_owner_or_missing_source_facts(self):
        identity, snapshot = self._snapshot()
        args = dict(account_id="paper", owner="ROBOT", trade_episode_id=identity, now_ms=_ms(9, 12))
        with self.assertRaises(EpisodeFactsSourceChanged):
            project_paper_closed_episode_facts(snapshot, source_revision=9, **args)
        with self.assertRaises(EpisodeFactsNotFound):
            project_paper_closed_episode_facts(snapshot, source_revision=8, **{**args, "owner": "MANUAL"})
        with self.assertRaises(StatisticsScopeError):
            project_paper_closed_episode_facts(
                PaperSourceSnapshot(8, snapshot.episodes, snapshot.origins),
                source_revision=8, **args,
            )
        with self.assertRaises(StatisticsScopeError):
            project_paper_closed_episode_facts(
                PaperSourceSnapshot(8, snapshot.episodes, snapshot.origins, executions=snapshot.executions[:1]),
                source_revision=8, **args,
            )
        with self.assertRaises(ValueError):
            project_paper_closed_episode_facts(snapshot, source_revision=8, **{**args, "trade_episode_id": "bad"})




class EpisodeD2ContextReadOnlyTests(unittest.TestCase):
    def _linked_store(self, path):
        from terminal.diary.decision_models import (
            SetupInstanceId, SetupInstanceRecord, DecisionEventId, DecisionEventKind,
            DecisionEventRecord, OrderPlanId, OrderPlanRecord, TradeEpisodeSetupLink,
        )
        from terminal.diary.decision_store import DiaryDecisionStore
        from terminal.domain.models import Controller

        instance = SetupInstanceId("setup-robot")
        setup = SetupInstanceRecord(
            setup_instance_id=instance, symbol=Symbol("BTCUSDT"),
            timeframe="5m", pattern="Falling Wedge", direction=PositionSide.LONG,
            strategy_version="v1", setup_id="candidate-42", hypothesis_id=None,
            entry_mode="breakout_retest", origin=Origin.ROBOT, created_at_ms=100,
        )
        with DiaryDecisionStore.open(path) as store:
            store.create_setup_instance(setup)
            for key, kind, stamp in [
                ("strategy-1", DecisionEventKind.STRATEGY, 110),
                ("risk-1", DecisionEventKind.RISK, 120),
            ]:
                store.append_decision_event(DecisionEventRecord(
                    decision_event_id=DecisionEventId(key), setup_instance_id=instance,
                    kind=kind, previous_state="PENDING", next_state="APPROVED",
                    reason_code=key.upper().replace("-", "_") + "_OK",
                    origin=Origin.ROBOT, controller=Controller.ROBOT,
                    strategy_version="v1", hypothesis_id=None, setup_id="candidate-42",
                    entry_mode="breakout_retest", feature_snapshot_ref="feature-ref",
                    risk_snapshot_ref="risk-ref" if kind is DecisionEventKind.RISK else None,
                    order_plan_id=None, occurred_at_ms=stamp,
                ))
            store.create_order_plan(OrderPlanRecord(
                order_plan_id=OrderPlanId("plan-1"), setup_instance_id=instance,
                strategy_decision_event_id=DecisionEventId("strategy-1"),
                risk_decision_event_id=DecisionEventId("risk-1"),
                trading_account_id=TradingAccountId("paper"),
                symbol=Symbol("BTCUSDT"), side=PositionSide.LONG, created_at_ms=130,
            ))
            store.link_trade_episode(TradeEpisodeSetupLink(
                trade_episode_id=TradeEpisodeId("te_" + "a"*24),
                setup_instance_id=instance, order_plan_id=OrderPlanId("plan-1"),
                linked_at_ms=140,
            ))

    def test_missing_d2_store_does_not_initialize_database_or_guess_signal(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from terminal.diary.episode_context import project_episode_d2_context_read_only as read
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "not-created.sqlite3"
            result = read(path, trade_episode_id="te_" + "a"*24, account_id="paper",
                          symbol="BTCUSDT", side="LONG", opening_controller="ROBOT")
            self.assertEqual(result["status"], "D2_STORE_ABSENT")
            self.assertEqual(result["geometry_status"], "NOT_EXPORTED")
            self.assertFalse(path.exists())

    def test_exact_link_exposes_only_observed_d2_setup_decisions_without_writes(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from terminal.diary.episode_context import project_episode_d2_context_read_only as read
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "diary.sqlite3"
            self._linked_store(path)
            before_bytes = path.read_bytes()
            before_mtime = path.stat().st_mtime_ns
            args = dict(account_id="paper", symbol="BTCUSDT", side="LONG",
                        opening_controller="ROBOT")
            result = read(path, trade_episode_id="te_" + "a"*24, **args)
            self.assertEqual(result["status"], "EXACT_D2_LINK")
            self.assertEqual(result["setup"]["setup_id"], "candidate-42")
            self.assertEqual(result["setup"]["pattern"], "Falling Wedge")
            self.assertEqual(result["setup"]["timeframe"], "5m")
            self.assertEqual(result["setup"]["strategy_version"], "v1")
            self.assertTrue(result["setup"]["has_feature_snapshot_ref"])
            self.assertEqual(result["geometry_status"], "NOT_EXPORTED")
            self.assertEqual([e["kind"] for e in result["decisions"]], ["STRATEGY", "RISK"])
            self.assertEqual([e["reason_code"] for e in result["decisions"]],
                             ["STRATEGY_1_OK", "RISK_1_OK"])
            self.assertEqual(result["decision_scope"], "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG")
            self.assertNotIn("geometry", result)
            self.assertNotIn("robot_runtime_events", result)
            self.assertEqual(path.read_bytes(), before_bytes)
            self.assertEqual(path.stat().st_mtime_ns, before_mtime)

            absent = read(path, trade_episode_id="te_" + "b"*24, **args)
            self.assertEqual(absent["status"], "NO_EXACT_EPISODE_LINK")
            for patch in [
                {"symbol": "ETHUSDT"}, {"side": "SHORT"},
                {"opening_controller": "MANUAL"},
            ]:
                mismatch = read(path, trade_episode_id="te_" + "a"*24, **{**args, **patch})
                self.assertEqual(mismatch["status"], "CONFLICTING_D2_LINK")
                self.assertNotIn("setup", mismatch)
                self.assertNotIn("decisions", mismatch)
            with self.assertRaises(ValueError):
                read(path, trade_episode_id="te_" + "a"*24, **{**args, "account_id": "main"})

    def test_invalid_d2_is_unavailable_without_changing_execution_facts(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from terminal.diary.episode_context import project_episode_d2_context_read_only as read
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.sqlite3"
            path.write_bytes(b"not sqlite3")
            result = read(path, trade_episode_id="te_" + "a"*24, account_id="paper",
                          symbol="BTCUSDT", side="LONG", opening_controller="ROBOT")
            self.assertEqual(result["status"], "EVIDENCE_UNAVAILABLE")
            self.assertEqual(path.read_bytes(), b"not sqlite3")




class EpisodeOriginalGeometryReadOnlyTests(unittest.TestCase):
    def _source(self, candidate_id):
        return {
            "schema_version": 1,
            "signal_id": candidate_id, "symbol": "BTCUSDT", "timeframe": "5m",
            "bars": [
                {"open_time_ms": 100, "open": 101.0, "high": 103.0,
                 "low": 99.0, "close": 100.0},
                {"open_time_ms": 200, "open": 100.0, "high": 102.0,
                 "low": 98.0, "close": 101.0},
            ],
            "boundaries": [
                {"boundary_id": "frozen-lower", "kind": "segment", "anchors": [
                    {"bar_open_time_ms": 100, "price": 99.5},
                    {"bar_open_time_ms": 200, "price": 99.8},
                ]},
            ],
        }

    @staticmethod
    def _context(candidate_id):
        return {
            "status": "EXACT_D2_LINK", "source": "TRADING_DIARY_D2",
            "geometry_status": "NOT_EXPORTED",
            "decision_scope": "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
            "setup": {
                "setup_id": candidate_id, "symbol": "BTCUSDT", "timeframe": "5m",
                "pattern": "Falling Wedge", "origin": "ROBOT",
                "created_at_ms": 300,
            },
        }

    def test_only_exact_hash_checked_archived_detector_geometry_is_exported(self):
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from signal_archive import record_original_signal
        from terminal.diary.episode_context import attach_verified_original_geometry

        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"BYBITSCANNER_SIGNAL_ARCHIVE_DIR": root}
        ):
            candidate = "candidate-42"
            self.assertTrue(record_original_signal(
                candidate, symbol="BTCUSDT", timeframe="5m",
                pattern="Falling Wedge", text="source",
                image_bytes=b"immutable-original-image",
                sent_at_ms=350, geometry_snapshot=self._source(candidate),
            ))
            archive = Path(root)
            before = {
                p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                for p in archive.iterdir()
            }
            result = attach_verified_original_geometry(
                self._context(candidate), symbol="BTCUSDT", opened_at_ms=500,
            )
            self.assertEqual(result["geometry_status"], "ORIGINAL_ARCHIVE_HASH_VERIFIED")
            original = result["original_geometry"]
            self.assertEqual(original["signal_id"], candidate)
            self.assertEqual(original["snapshot"], self._source(candidate))
            self.assertEqual(original["linkage_basis"], "D2_SETUP_ID_EQUALS_ARCHIVED_CANDIDATE_ID")
            self.assertEqual(original["integrity"], "LOCAL_ARCHIVE_HASH_ONLY_NOT_CRYPTOGRAPHIC_PROOF")
            self.assertNotIn("corrected_boundaries", original)
            self.assertNotIn("robot_runtime_decisions", original)
            self.assertEqual(before, {
                p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in archive.iterdir()
            })

            # A missing D2 link is never inferred from a ticker, archive or time.
            missing = {"status": "NO_EXACT_EPISODE_LINK", "geometry_status": "NOT_EXPORTED"}
            self.assertEqual(
                attach_verified_original_geometry(missing, symbol="BTCUSDT", opened_at_ms=500),
                missing,
            )
            wrong = self._context(candidate)
            wrong["setup"]["pattern"] = "Rising Wedge"
            self.assertEqual(
                attach_verified_original_geometry(wrong, symbol="BTCUSDT", opened_at_ms=500)[
                    "geometry_status"
                ], "NOT_EXPORTED",
            )
            self.assertEqual(
                attach_verified_original_geometry(
                    self._context(candidate), symbol="ETHUSDT", opened_at_ms=500,
                )["geometry_status"], "NOT_EXPORTED",
            )
            self.assertEqual(
                attach_verified_original_geometry(
                    self._context(candidate), symbol="BTCUSDT", opened_at_ms=300,
                )["geometry_status"], "NOT_EXPORTED",
            )

            # The frozen byte hash must be checked by the canonical archive reader.
            frozen = next(archive.glob("*.geometry.json"))
            frozen.write_bytes(frozen.read_bytes() + b" ")
            self.assertEqual(
                attach_verified_original_geometry(
                    self._context(candidate), symbol="BTCUSDT", opened_at_ms=500,
                )["geometry_status"], "NOT_EXPORTED",
            )

def test_campaign_lineage_proof_regressions():
    """Keep new exact-ID proof cases inside the existing mandatory Diary CI gate."""
    from terminal.diary.test_campaign_lineage import CampaignProofTests

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CampaignProofTests)
    result = unittest.TestResult()
    suite.run(result)
    assert result.testsRun >= 8
    assert result.wasSuccessful(), (result.failures, result.errors)



def test_campaign_sqlite_schema_regression(tmp_path):
    from terminal.diary.test_campaign_lineage import (
        test_campaign_sqlite_reader_uses_actual_production_table_definitions,
    )
    test_campaign_sqlite_reader_uses_actual_production_table_definitions(tmp_path)


class SimulatorLaunchRelayTests(unittest.TestCase):
    """Paired-device relay cannot grant trading, shell, or arbitrary URL access."""

    def make_relay(self):
        from terminal.diary.simulator_launch_relay import SimulatorLaunchRelay

        tick = [100.0]
        token = "A" * 64
        relay = SimulatorLaunchRelay(
            origin="https://stats.example.test",
            devices={"owner-pc": token, "owner-laptop": "B" * 64},
            clock=lambda: tick[0],
        )
        return relay, tick, token

    def test_disabled_without_secret_config_and_rejects_invalid_config(self):
        from terminal.diary.simulator_launch_relay import SimulatorLaunchRelay, RelayInvalid
        from unittest.mock import patch

        with patch.dict("os.environ", {
            "BYBITSCANNER_SIMULATOR_BRIDGE_ORIGIN": "",
            "BYBITSCANNER_SIMULATOR_BRIDGE_DEVICES_JSON": "",
        }):
            self.assertIsNone(SimulatorLaunchRelay.from_environment())
        with self.assertRaises(RelayInvalid):
            SimulatorLaunchRelay(origin="http://wrong.test", devices={"pc": "A" * 64})
        with self.assertRaises(RelayInvalid):
            SimulatorLaunchRelay(origin="https://stats.example.test", devices={
                "pc": "A" * 64, "laptop": "A" * 64,
            })

    def test_rejects_unpaired_device_bad_token_and_cross_origin_request(self):
        from terminal.diary.simulator_launch_relay import RelayForbidden, RelayUnavailable
        relay, _, token = self.make_relay()
        episode = "te_" + "a" * 24
        with self.assertRaises(RelayForbidden):
            relay.poll(device="owner-pc", token="Z" * 64)
        with self.assertRaises(RelayForbidden):
            relay.poll(device="unknown", token=token)
        with self.assertRaises(RelayUnavailable):
            relay.enqueue(episode, request_origin="https://stats.example.test",
                          fetch_site="same-origin")
        self.assertEqual(relay.poll(device="owner-pc", token=token)["state"], "IDLE")
        for origin, site in [
            ("https://evil.test", "same-origin"), ("https://stats.example.test", "cross-site"),
            ("", "same-origin"),
        ]:
            with self.assertRaises(RelayForbidden):
                relay.enqueue(episode, request_origin=origin, fetch_site=site)

    def test_typed_single_use_ack_and_expiration(self):
        from terminal.diary.simulator_launch_relay import (
            RelayInvalid, RelayUnavailable,
        )
        relay, tick, token = self.make_relay()
        relay.poll(device="owner-pc", token=token)
        episode = "te_" + "a" * 24
        for wrong in ["BTCUSDT", "te_" + "A" * 24, episode + ";powershell"]:
            with self.assertRaises(RelayInvalid):
                relay.enqueue(wrong, request_origin=relay.origin, fetch_site="same-origin")
        receipt = relay.enqueue(episode, request_origin=relay.origin, fetch_site="same-origin")
        self.assertEqual(receipt["state"], "QUEUED")
        with self.assertRaises(RelayUnavailable):
            relay.enqueue(episode, request_origin=relay.origin, fetch_site="same-origin")
        command = relay.poll(device="owner-pc", token=token)
        self.assertEqual(command["episode_id"], episode)
        self.assertEqual(command["request_id"], receipt["request_id"])
        self.assertEqual(relay.poll(device="owner-pc", token=token)["state"], "IDLE")
        self.assertEqual(
            relay.acknowledge(device="owner-pc", token=token,
                              request_id=command["request_id"], launched=True)["state"],
            "LAUNCHED",
        )
        with self.assertRaises(RelayInvalid):
            relay.acknowledge(device="owner-pc", token=token,
                              request_id=command["request_id"], launched=True)
        self.assertEqual(relay.status(receipt["request_id"],
                                     request_origin=relay.origin, fetch_site="same-origin")["state"],
                         "LAUNCHED")
        tick[0] += 13
        with self.assertRaises(RelayUnavailable):
            relay.enqueue(episode, request_origin=relay.origin, fetch_site="same-origin")

    def test_other_device_cannot_ack_or_read_unrelated_queue(self):
        from terminal.diary.simulator_launch_relay import RelayInvalid
        relay, _, token = self.make_relay()
        relay.poll(device="owner-pc", token=token)
        relay.poll(device="owner-laptop", token="B" * 64)
        # Latest heartbeat tie is deterministic; owner-pc is lexically later.
        receipt = relay.enqueue("te_" + "b" * 24,
                                request_origin=relay.origin, fetch_site="same-origin")
        self.assertEqual(relay.poll(device="owner-laptop", token="B" * 64)["state"], "IDLE")
        with self.assertRaises(RelayInvalid):
            relay.acknowledge(device="owner-laptop", token="B" * 64,
                              request_id=receipt["request_id"], launched=True)
        relay.poll(device="owner-pc", token=token)
        self.assertEqual(relay.acknowledge(device="owner-pc", token=token,
                                          request_id=receipt["request_id"],
                                          launched=False)["state"], "FAILED")

    def test_unacknowledged_delivery_expires_and_is_not_redelivered(self):
        relay, tick, token = self.make_relay()
        relay.poll(device="owner-pc", token=token)
        receipt = relay.enqueue("te_" + "c" * 24,
                                request_origin=relay.origin, fetch_site="same-origin")
        self.assertEqual(relay.poll(device="owner-pc", token=token)["state"], "OPEN_EPISODE")
        tick[0] += 36
        self.assertEqual(relay.poll(device="owner-pc", token=token)["state"], "IDLE")
        self.assertEqual(relay.status(receipt["request_id"], request_origin=relay.origin,
                                      fetch_site="same-origin")["state"], "EXPIRED")


if __name__ == "__main__":
    unittest.main()
