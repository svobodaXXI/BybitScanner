"""Exact-ID Wedge initial risk: additive read-only evidence only."""

import json
import unittest
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace as Obj

from terminal.diary.models import AllocationRole
from terminal.diary.wedge_lineage import (
    WedgeLineageUnproven, project_selected_paper_wedge,
)
from terminal.domain.models import Origin


@dataclass(frozen=True)
class _Token:
    value: str


@dataclass(frozen=True)
class _ExecutionKey:
    trading_account_id: _Token
    exec_id: _Token


def _example(*, direction="LONG", entry_prices=("100",),
             average_entry=None, stop_price=None, take_price=None,
             entry_quantity=None):
    symbol = _Token("EVIDENCEUSDT")
    account = _Token("paper")
    entry_order = _Token("entry-order")
    closing_order = _Token("exit-order")
    is_long = direction == "LONG"
    prices = [Decimal(p) for p in entry_prices]
    average = sum(prices, Decimal(0)) / Decimal(len(prices))
    average_entry = average if average_entry is None else average_entry
    stop = Decimal("95") if is_long else Decimal("105")
    take = Decimal("110") if is_long else Decimal("90")
    if stop_price is not None:
        stop = stop_price
    if take_price is not None:
        take = take_price
    quantity = Decimal(len(prices)) if entry_quantity is None else entry_quantity

    allocations, executions, origins = [], [], {}
    for i, price in enumerate(prices):
        key = _ExecutionKey(account, _Token(f"entry-{i}"))
        timestamp = 120000 + 60000 * i
        allocations.append(Obj(
            role=AllocationRole.OPEN if i == 0 else AllocationRole.INCREASE,
            execution_key=key, occurred_at_ms=timestamp,
            quantity=Decimal("1"), fee=Decimal("0.1"),
        ))
        executions.append(Obj(
            dedup_key=key, symbol=symbol, exchange_timestamp_ms=timestamp,
            quantity=Obj(value=Decimal("1")), fee=Decimal("0.1"),
            order_id=entry_order, side=_Token("buy" if is_long else "sell"),
            price=Obj(value=price),
        ))
        origins[key] = Origin.ROBOT

    close_timestamp = 120000 + 60000 * len(prices)
    close_key = _ExecutionKey(account, _Token("close-execution"))
    allocations.append(Obj(
        role=AllocationRole.CLOSE, execution_key=close_key,
        occurred_at_ms=close_timestamp, quantity=Decimal(len(prices)),
        fee=Decimal("0.2"),
    ))
    executions.append(Obj(
        dedup_key=close_key, symbol=symbol,
        exchange_timestamp_ms=close_timestamp,
        quantity=Obj(value=Decimal(len(prices))), fee=Decimal("0.2"),
        order_id=closing_order, side=_Token("sell" if is_long else "buy"),
        price=Obj(value=Decimal("94") if is_long else Decimal("106")),
    ))
    origins[close_key] = Origin.ROBOT

    episode = Obj(
        trade_episode_id=_Token("te_" + "a" * 24),
        position_key=Obj(symbol=symbol),
        side=_Token(direction.lower()),
        opened_at_ms=120000,
        closed_at_ms=close_timestamp,
        allocations=tuple(allocations),
        realized_price_pnl=Decimal("-6"),
        execution_fees=Decimal("0.2") + Decimal("0.1") * len(prices),
    )
    trade = {
        "trading_account_id": "paper", "candidate_id": "candidate-one",
        "trade_id": "robot-trade-one", "symbol": symbol.value,
        "direction": direction,
        "pattern": "Falling Wedge" if is_long else "Rising Wedge",
        "source_timeframe": "M5", "signal_time_ms": 60000,
        "entry_time_ms": 120000, "exit_time_ms": close_timestamp,
        "exit_reason": "STOP", "average_entry": str(average_entry),
        "entry_quantity": str(quantity), "stop_price": str(stop),
        "take_price": str(take),
    }
    evidence = {
        "candidates": ({
            "trading_account_id": "paper", "candidate_id": "candidate-one",
            "symbol": symbol.value,
            "robot_state_json": json.dumps({
                "execution": {"limit_order_id": entry_order.value}
            }),
        },),
        "trades": (trade,),
        "robot_entries": ({
            "trading_account_id": "paper", "origin": "ROBOT",
            "order_id": entry_order.value,
        },),
        "obligations": ({
            "trading_account_id": "paper", "trade_id": "robot-trade-one",
            "status": "RESOLVED", "winning_leg": "STOP",
            "exec_id": close_key.exec_id.value,
            "order_id": closing_order.value,
        },),
    }
    snapshot = Obj(
        source_revision=595, episodes=(episode,), origins=origins,
        executions=tuple(executions), wedge_evidence=evidence,
    )
    return snapshot, episode.trade_episode_id.value


def _project(snapshot, episode_id, revision=595):
    return project_selected_paper_wedge(
        snapshot, account_id="paper", owner="ROBOT",
        trade_episode_id=episode_id, source_revision=revision,
    )


class WedgeEntryRiskLineageTests(unittest.TestCase):
    def test_long_initial_risk_matches_exact_fill_and_stop(self):
        snapshot, eid = _example()
        report = _project(snapshot, eid)
        self.assertEqual(report["entry_risk"]["status"], "PROVEN_PERSISTED_ENTRY_TERMS")
        self.assertEqual(report["entry_risk"]["initial_stop_price"], "95")
        self.assertEqual(Decimal(report["entry_risk"]["initial_risk_price"]), Decimal("5"))
        self.assertEqual(Decimal(report["entry_risk"]["initial_risk_pct"]), Decimal("5"))
        self.assertEqual(report["exit_reason"], "STOP")
        self.assertEqual(report["decisions_coverage"], "NOT_PROVIDED")

    def test_short_initial_risk_and_multiple_entry_fills(self):
        snapshot, eid = _example(
            direction="SHORT", entry_prices=("99", "101"),
            stop_price=Decimal("106"), take_price=Decimal("90"),
        )
        report = _project(snapshot, eid)
        self.assertEqual(report["entry_risk"]["status"], "PROVEN_PERSISTED_ENTRY_TERMS")
        self.assertEqual(Decimal(report["entry_risk"]["filled_average_entry"]), Decimal("100"))
        self.assertEqual(Decimal(report["entry_risk"]["initial_risk_price"]), Decimal("6"))

    def test_mismatched_persisted_average_does_not_make_up_risk(self):
        snapshot, eid = _example(entry_prices=("100", "102"), average_entry=Decimal("100"))
        report = _project(snapshot, eid)
        self.assertEqual(report["entry_risk"]["status"], "UNPROVEN")
        self.assertEqual(report["entry_risk"]["reason"], "entry_fills_terms_mismatch")
        self.assertNotIn("initial_stop_price", report["entry_risk"])
        self.assertEqual(report["signal_pattern"], "Falling Wedge")

    def test_invalid_stop_order_does_not_make_up_risk(self):
        snapshot, eid = _example(stop_price=Decimal("101"))
        report = _project(snapshot, eid)
        self.assertEqual(report["entry_risk"]["status"], "UNPROVEN")
        self.assertEqual(report["entry_risk"]["reason"], "entry_protection_order_invalid")

    def test_stale_revision_remains_fail_closed(self):
        snapshot, eid = _example()
        with self.assertRaises(WedgeLineageUnproven):
            _project(snapshot, eid, revision=594)

    def test_without_exact_robot_entry_ownership_remains_fail_closed(self):
        snapshot, eid = _example()
        snapshot.wedge_evidence["robot_entries"] = ()
        with self.assertRaises(WedgeLineageUnproven):
            _project(snapshot, eid)


if __name__ == "__main__":
    unittest.main()
