"""Exact-ID regressions for read-only Robot campaign lineage proof."""
from __future__ import annotations

import unittest
from decimal import Decimal

from terminal.diary.campaign_lineage import (
    CampaignLineageUnproven, prove_robot_campaign_episodes,
    project_selected_paper_campaign,
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
                 pattern="Box", source_timeframe="5m", signal_time_ms=900, entry_time_ms=1000,
                 exit_time_ms=1100, exit_reason="STOP"),
            dict(trading_account_id="paper", candidate_id="candidate-2",
                 trade_id="trade-2", symbol="BTCUSDT", direction="LONG",
                 pattern="Box", source_timeframe="5m", signal_time_ms=1150, entry_time_ms=1200,
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
        self.assertEqual(result["trade_episodes"][0]["signal_pattern"], "Box")
        self.assertEqual(result["trade_episodes"][0]["signal_timeframe"], "5m")
        self.assertEqual(result["trade_episodes"][0]["signal_provenance"],
                         "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY")
        self.assertEqual(len(result["source_sha256"]), 64)
        self.assertNotIn("candles", result)
        self.assertNotIn("robot_decisions", result)

    def test_selected_episode_resolves_only_exact_campaign(self):
        evidence = fixture()
        source = evidence["snapshot"]
        source = PaperSourceSnapshot(
            source.source_revision, source.episodes, source.origins,
            source.executions,
            campaign_evidence={
                "campaigns": (evidence["campaign"],),
                "attempts": tuple(evidence["attempts"]),
                "trades": tuple(evidence["trades"]),
                "entry_ownership": tuple(evidence["entry_ownership"]),
                "obligations": tuple(evidence["obligations"]),
            },
        )
        document = project_selected_paper_campaign(
            source, account_id="paper", owner="ROBOT",
            trade_episode_id=evidence["trade_episode_id"], source_revision=5,
        )
        self.assertEqual(document["campaign_id"], "camp-1")
        self.assertEqual([a["execution_id"] for a in document["trade_episodes"][1]["execution_allocations"]],
                         ["open-2", "close-2"])
        self.assertEqual(document["trade_episodes"][1]["known_execution_fees_usdt"], "0.2")
        self.assertEqual(document["trade_episodes"][1]["execution_allocations"][1]["order_id"], "exit-2")
        self.assertEqual(document["trade_episodes"][1]["signal_pattern"], "Box")

    def test_selected_episode_requires_source_evidence_not_proximity(self):
        evidence = fixture()
        with self.assertRaisesRegex(CampaignLineageUnproven, "campaign_source_evidence_unavailable"):
            project_selected_paper_campaign(
                evidence["snapshot"], account_id="paper", owner="ROBOT",
                trade_episode_id=evidence["trade_episode_id"], source_revision=5,
            )

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



def test_campaign_sqlite_reader_uses_actual_production_table_definitions(tmp_path):
    """Offline SQLite fixture: real schema DDL, exact IDs, no paper DB writes."""
    import hashlib
    import sqlite3
    from terminal.diary.scoped_statistics_reporter import load_paper_source_snapshot
    from terminal.persistence.schema import SCHEMA_STATEMENTS

    db = tmp_path / "fixture-paper.sqlite3"
    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        # Minimal unmodified existing Diary source tables, then the canonical
        # production DDL for every campaign join (including their constraints).
        con.executescript("""
            CREATE TABLE paper_accounts (trading_account_id TEXT PRIMARY KEY);
            INSERT INTO paper_accounts VALUES ('paper');
            CREATE TABLE executions (
                trading_account_id TEXT, category TEXT, exec_id TEXT,
                order_id TEXT, symbol TEXT, side TEXT, price TEXT,
                quantity TEXT, fee TEXT, exchange_timestamp_ms INTEGER
            );
            CREATE TABLE trading_commands (
                command_id TEXT, trading_account_id TEXT, exchange_order_id TEXT,
                origin TEXT, controller TEXT
            );
        """)
        for table in (
            "robot_candidates", "box_attempt_ownership", "robot_trades",
            "box_order_ownership", "robot_reentry_campaigns",
            "robot_reentry_attempts", "paper_protection_obligations",
        ):
            ddl = next(
                statement for statement in SCHEMA_STATEMENTS
                if statement.lstrip().startswith(f"CREATE TABLE {table} (")
            )
            con.execute(ddl)
        def insert(table, fields):
            keys = tuple(fields)
            con.execute(
                f"INSERT INTO {table} ({', '.join(keys)}) VALUES "
                + "(" + ",".join("?" for _ in keys) + ")",
                tuple(fields.values()),
            )
        for index, opened, closed, exit_reason in (
            (1, 1000, 1100, "STOP"), (2, 1200, 1300, "TAKE"),
        ):
            for role, stamp, side, oid, exec_id in (
                ("OPEN", opened, "Buy", f"entry-{index}", f"open-{index}"),
                ("CLOSE", closed, "Sell", f"exit-{index}", f"close-{index}"),
            ):
                insert("executions", {
                    "trading_account_id": "paper", "category": "linear",
                    "exec_id": exec_id, "order_id": oid, "symbol": "BTCUSDT",
                    "side": side, "price": "100" if role == "OPEN" else "101",
                    "quantity": "1", "fee": "0.1", "exchange_timestamp_ms": stamp,
                })
                insert("trading_commands", {
                    "command_id": f"command-{exec_id}", "trading_account_id": "paper",
                    "exchange_order_id": oid, "origin": "robot", "controller": "robot",
                })
            candidate_snapshot = '{"id":"candidate-' + str(index) + '"}'
            insert("robot_candidates", {
                "candidate_id": f"candidate-{index}", "trading_account_id": "paper",
                "symbol": "BTCUSDT", "status": "APPROVED",
                "signal_snapshot_json": candidate_snapshot,
                "snapshot_sha256": hashlib.sha256(candidate_snapshot.encode()).hexdigest(),
                "robot_state_json": None, "state_revision": 0,
                "approved_at_ms": opened - 100, "updated_at_ms": opened - 100,
            })
            insert("box_attempt_ownership", {
                "candidate_id": f"candidate-{index}", "trading_account_id": "paper",
                "symbol": "BTCUSDT", "attempt": 1,
                "baseline_position_version": 1, "baseline_time_ms": opened - 100,
                "baseline_execution_count": 0, "baseline_execution_hash": "b" * 64,
            })
            insert("box_order_ownership", {
                "trading_account_id": "paper", "order_id": f"entry-{index}",
                "candidate_id": f"candidate-{index}", "role": "ENTRY", "slot": 1,
            })
            insert("robot_trades", {
                "trade_id": f"trade-{index}", "trading_account_id": "paper",
                "candidate_id": f"candidate-{index}", "symbol": "BTCUSDT",
                "direction": "LONG", "pattern": "Box", "source_timeframe": "5m",
                "signal_time_ms": opened - 100, "entry_time_ms": opened,
                "entry_path": "LIMIT", "actual_wv": "0.5",
                "average_entry": "100", "stop_price": "99", "take_price": "101",
                "exit_time_ms": closed, "exit_price": "101",
                "exit_reason": exit_reason, "realized_pnl_usdt": "0.8",
                "realized_pnl_pct": "0.8", "fees_costs_usdt": "0.2",
                "version": 1, "created_at_ms": opened, "updated_at_ms": closed,
            })
            insert("paper_protection_obligations", {
                "obligation_id": f"ob-{index}", "trade_id": f"trade-{index}",
                "trading_account_id": "paper", "symbol": "BTCUSDT",
                "protection_version": 1, "winning_leg": exit_reason,
                "trigger_price": "99", "observed_exit_price": "101",
                "observed_quantity": "1", "market_event_id": f"m-{index}",
                "source_received_at_ms": closed, "latched_at_ms": closed,
                "order_id": f"exit-{index}", "exec_id": f"close-{index}",
                "status": "RESOLVED", "version": 1, "updated_at_ms": closed,
            })
        insert("robot_reentry_campaigns", {
            "trading_account_id": "paper", "campaign_id": "campaign-1",
            "symbol": "BTCUSDT", "direction": "LONG",
            "first_candidate_id": "candidate-1",
            "frozen_thesis_sha256": "a" * 64,
            "original_risk_budget_usdt": "10", "created_at_ms": 900,
        })
        for index, stamp, previous in ((1, 900, None), (2, 1150, "close-1")):
            insert("robot_reentry_attempts", {
                "trading_account_id": "paper", "campaign_id": "campaign-1",
                "attempt_index": index, "candidate_id": f"candidate-{index}",
                "reserved_risk_usdt": "1", "previous_stop_exec_id": previous,
                "reserved_at_ms": stamp,
            })
        con.commit()
    finally:
        con.close()

    before = hashlib.sha256(db.read_bytes()).hexdigest()
    snapshot = load_paper_source_snapshot(db, include_campaign_evidence=True)
    assert snapshot.source_revision == 5
    assert len(snapshot.episodes) == 2
    assert snapshot.campaign_evidence is not None
    response = project_selected_paper_campaign(
        snapshot, account_id="paper", owner="ROBOT",
        trade_episode_id=snapshot.episodes[1].trade_episode_id.value,
        source_revision=5,
    )
    assert response["schema"] == "BYBITSCANNER_PAPER_CAMPAIGN_LINEAGE_V1"
    assert response["campaign_id"] == "campaign-1"
    assert len(response["trade_episodes"]) == 2
    assert response["trade_episodes"][0]["execution_allocations"][0]["order_id"] == "entry-1"
    assert response["trade_episodes"][1]["execution_allocations"][-1]["order_id"] == "exit-2"
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
