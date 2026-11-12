"""Exact-ID regressions for read-only Robot campaign lineage proof."""
from __future__ import annotations

import copy
import unittest
from decimal import Decimal

from terminal.diary.campaign_lineage import (
    CampaignLineageUnproven, prove_robot_campaign_episodes,
)
from terminal.diary.models import (
    AllocationRole, DiaryEnvironment, ExecutionAllocation,
    TradeEpisode, TradeEpisodeId,
)
from terminal.diary.scoped_statistics_reporter import PaperSourceSnapshot
from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, OrderId,
    OrderSide, Origin, PositionKey, PositionSide, Price, Quantity,
    Symbol, TradingAccountId,
)


def fixture():
    account = TradingAccountId("paper")
    episodes = []
    executions = []
    origins = {}
    for n, opened, closed in ((1, 1000, 1100), (2, 1200, 1300)):
        episode_id = TradeEpisodeId("te_" + str(n) * 24)
        allocations = []
        for kind, at, order_id, side in (
            ("open", opened, f"entry-{n}", OrderSide.BUY),
            ("close", closed, f"exit-{n}", OrderSide.SELL),
        ):
            execution_key = ExecutionDedupKey(
                account, Category.LINEAR, ExecutionId(f"{kind}-{n}"),
            )
            executions.append(Execution(
                dedup_key=execution_key, order_id=OrderId(order_id),
                symbol=Symbol("BTCUSDT"), side=side,
                price=Price(Decimal("100")), quantity=Quantity(Decimal("1")),
                fee=Decimal("0.1"), exchange_timestamp_ms=at,
            ))
            origins[execution_key] = Origin.ROBOT
            allocations.append(ExecutionAllocation(
                execution_key=execution_key, trade_episode_id=episode_id,
                role=AllocationRole.OPEN if kind == "open" else AllocationRole.CLOSE,
                quantity=Decimal("1"), fee=Decimal("0.1"), occurred_at_ms=at,
            ))
        episodes.append(TradeEpisode(
            trade_episode_id=episode_id,
            position_key=PositionKey(account, Category.LINEAR, Symbol("BTCUSDT"), 0),
            side=PositionSide.LONG, environment=DiaryEnvironment.PAPER,
            opened_at_ms=opened, closed_at_ms=closed,
            opening_price=Price(Decimal("100")), average_entry=Price(Decimal("100")),
            open_quantity=Quantity(Decimal("0")), realized_price_pnl=Decimal("2"),
            execution_fees=Decimal("0.2"), allocations=tuple(allocations),
        ))
    evidence = dict(
        snapshot=PaperSourceSnapshot(
            source_revision=5, episodes=tuple(episodes), origins=origins,
            executions=tuple(executions),
        ),
        account_id="paper", trade_episode_id=episodes[1].trade_episode_id.value,
        source_revision=5,
        campaign=dict(
            trading_account_id="paper", campaign_id="camp-1",
            first_candidate_id="candidate-1", direction="LONG", symbol="BTCUSDT",
        ),
        attempts=[
            dict(trading_account_id="paper", campaign_id="camp-1",
                 candidate_id="candidate-1", attempt_index=1, previous_stop_exec_id=None),
            dict(trading_account_id="paper", campaign_id="camp-1",
                 candidate_id="candidate-2", attempt_index=2, previous_stop_exec_id="close-1"),
        ],
        trades=[
            dict(trading_account_id="paper", candidate_id="candidate-1",
                 trade_id="trade-1", symbol="BTCUSDT", direction="LONG",
                 signal_time_ms=900, entry_time_ms=1000,
                 exit_time_ms=1100, exit_reason="STOP"),
            dict(trading_account_id="paper", candidate_id="candidate-2",
                 trade_id="trade-2", symbol="BTCUSDT", direction="LONG",
                 signal_time_ms=1150, entry_time_ms=1200,
                 exit_time_ms=1300, exit_reason="TAKE"),
        ],
        entry_ownership=[
            dict(trading_account_id="paper", candidate_id="candidate-1",
                 order_id="entry-1", role="ENTRY"),
            dict(trading_account_id="paper", candidate_id="candidate-2",
                 order_id="entry-2", role="ENTRY"),
        ],
        obligations=[
            dict(trading_account_id="paper", trade_id="trade-1", status="RESOLVED",
                 winning_leg="STOP", order_id="exit-1", exec_id="close-1"),
            dict(trading_account_id="paper", trade_id="trade-2", status="RESOLVED",
                 winning_leg="TAKE", order_id="exit-2", exec_id="close-2"),
        ],
    )
    return evidence


class CampaignProofTests(unittest.TestCase):
    def test_proves_two_attempts_by_exact_order_execution_and_stop_parent(self):
        result = prove_robot_campaign_episodes(**fixture())
        self.assertEqual(result["schema"], "BYBITSCANNER_PAPER_CAMPAIGN_LINEAGE_V1")
        self.assertEqual(result["namespace"], "PAPER_READ_ONLY")
        self.assertEqual(result["source_revision"], 5)
        self.assertEqual([e["trade_episode_id"] for e in result["trade_episodes"]],
                         ["te_" + "1" * 24, "te_" + "2" * 24])
        self.assertEqual([e["exit_reason"] for e in result["trade_episodes"]],
                         ["STOP", "TAKE"])
        self.assertEqual([e["pnl_usdt"] for e in result["trade_episodes"]],
                         ["1.8", "1.8"])
        self.assertEqual(len(result["source_sha256"]), 64)
        self.assertNotIn("candles", result)
        self.assertNotIn("robot_decisions", result)

    def test_rejects_stale_revision_and_cross_account(self):
        for patch in ({"source_revision": 4}, {"account_id": "main"}):
            evidence = fixture()
            evidence.update(patch)
            with self.assertRaises(CampaignLineageUnproven):
                prove_robot_campaign_episodes(**evidence)

    def test_rejects_missing_exact_entry_or_exit(self):
        for name in ("entry_ownership", "obligations"):
            evidence = fixture()
            evidence[name] = evidence[name][:1]
            with self.assertRaises(CampaignLineageUnproven):
                prove_robot_campaign_episodes(**evidence)

    def test_rejects_fabricated_reentry_without_matching_previous_stop(self):
        evidence = fixture()
        evidence["attempts"][1]["previous_stop_exec_id"] = "unrelated-execution"
        with self.assertRaisesRegex(CampaignLineageUnproven, "campaign_stop_reentry_not_proven"):
            prove_robot_campaign_episodes(**evidence)

    def test_rejects_inferred_link_by_symbol_and_time(self):
        evidence = fixture()
        evidence["entry_ownership"][1]["order_id"] = "another-order"
        with self.assertRaisesRegex(CampaignLineageUnproven, "campaign_episode_link_missing_or_ambiguous"):
            prove_robot_campaign_episodes(**evidence)

    def test_rejects_manual_execution_in_robot_campaign(self):
        evidence = fixture()
        key = evidence["snapshot"].episodes[1].allocations[-1].execution_key
        original = evidence["snapshot"]
        evidence["snapshot"] = PaperSourceSnapshot(
            original.source_revision, original.episodes,
            {**original.origins, key: Origin.TERMINAL_MANUAL},
            original.executions,
        )
        with self.assertRaises(CampaignLineageUnproven):
            prove_robot_campaign_episodes(**evidence)

    def test_rejects_last_stop_with_future_reentry_possible(self):
        evidence = fixture()
        evidence["trades"][1]["exit_reason"] = "STOP"
        evidence["obligations"][1]["winning_leg"] = "STOP"
        with self.assertRaisesRegex(CampaignLineageUnproven, "campaign_terminal_state_unproven"):
            prove_robot_campaign_episodes(**evidence)

    def test_rejects_omitted_attempt_or_episode(self):
        evidence = fixture()
        evidence["trades"].pop()
        with self.assertRaises(CampaignLineageUnproven):
            prove_robot_campaign_episodes(**evidence)
        evidence = fixture()
        evidence["trade_episode_id"] = "te_" + "f" * 24
        with self.assertRaisesRegex(CampaignLineageUnproven, "campaign_requested_episode_not_linked"):
            prove_robot_campaign_episodes(**evidence)


if __name__ == "__main__":
    unittest.main()
