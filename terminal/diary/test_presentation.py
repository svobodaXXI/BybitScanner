from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from terminal.diary.models import DiaryEnvironment, TradeEpisodeId
from terminal.diary.presentation import project_trade_episode


def _episode(*, closed: bool):
    allocation = SimpleNamespace(
        execution_key=SimpleNamespace(
            exec_id=SimpleNamespace(value="exec-1"),
        ),
        role=SimpleNamespace(value="CLOSE" if closed else "OPEN"),
        quantity=Decimal("2"),
        fee=Decimal("0.1"),
        occurred_at_ms=2_000 if closed else 1_000,
    )
    return SimpleNamespace(
        trade_episode_id=TradeEpisodeId("episode-1"),
        position_key=SimpleNamespace(
            symbol=SimpleNamespace(value="BTCUSDT"),
        ),
        side=SimpleNamespace(value="Long"),
        environment=DiaryEnvironment.PAPER,
        opened_at_ms=1_000,
        closed_at_ms=2_000 if closed else None,
        opening_price=SimpleNamespace(value=Decimal("100")),
        average_entry=SimpleNamespace(value=Decimal("101")),
        open_quantity=SimpleNamespace(
            value=Decimal("0") if closed else Decimal("2"),
        ),
        realized_price_pnl=Decimal("3"),
        execution_fees=Decimal("0.1"),
        allocations=(allocation,),
        is_closed=closed,
    )


def test_closed_episode_keeps_net_pnl_missing_without_cost_evidence():
    projected = project_trade_episode(
        _episode(closed=True),
        now_ms=5_000,
    )

    assert projected["readiness"] == "CLOSED_INCOMPLETE"
    assert projected["needs_attention"] is True
    assert projected["pnl"] is None
    assert "MISSING_FUNDING" in projected["missing_reasons"]
    assert projected["exit_price"] is None
    assert projected["controller_origin"] is None


def test_open_episode_uses_current_duration_without_claiming_pnl():
    projected = project_trade_episode(
        _episode(closed=False),
        now_ms=5_000,
    )

    assert projected["readiness"] == "OPEN"
    assert projected["needs_attention"] is False
    assert projected["holding_duration_ms"] == 4_000
    assert projected["pnl"] is None


def test_trade_details_reuse_episode_allocations_and_keep_missing_facts_null():
    projected = project_trade_episode(
        _episode(closed=True),
        now_ms=5_000,
    )
    details = projected["details"]

    assert details["identity"]["trade_episode_id"] == "episode-1"
    assert details["decision"]["setup_id"] is None
    assert details["risk"]["initial_risk"] is None
    assert details["orders_executions"] == [
        {
            "execution_id": "exec-1",
            "role": "CLOSE",
            "quantity": "2",
            "fee": "0.1",
            "occurred_at_ms": 2_000,
        }
    ]
    assert details["outcome"]["realized_price_pnl"] == "3"
    assert details["outcome"]["net_pnl"] is None
    assert details["automatic_factors"] is None
    assert details["notes"] is None
