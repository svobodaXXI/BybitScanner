from __future__ import annotations

from pathlib import Path

from terminal.diary.decision_models import (
    DecisionEventId,
    DecisionEventKind,
    DecisionEventRecord,
    OrderPlanId,
    OrderPlanRecord,
    SetupInstanceId,
    SetupInstanceRecord,
    TradeEpisodeSetupLink,
)
from terminal.diary.decision_store import DiaryDecisionStore
from terminal.diary.models import TradeEpisodeId
from terminal.diary.setup_presentation import project_setup_list
from terminal.domain.models import Controller, Origin, PositionSide, Symbol, TradingAccountId


def _setup(instance_id: str, *, created_at_ms: int) -> SetupInstanceRecord:
    return SetupInstanceRecord(
        setup_instance_id=SetupInstanceId(instance_id),
        symbol=Symbol("BTCUSDT"),
        timeframe="1m",
        pattern="Falling Wedge",
        direction=PositionSide.LONG,
        strategy_version="strategy-v1",
        setup_id="falling-wedge",
        hypothesis_id=None,
        entry_mode="breakout_retest",
        origin=Origin.ROBOT,
        created_at_ms=created_at_ms,
    )


def _event(
    instance_id: str,
    event_id: str,
    *,
    kind: DecisionEventKind,
    next_state: str,
    reason: str,
    occurred_at_ms: int,
) -> DecisionEventRecord:
    return DecisionEventRecord(
        decision_event_id=DecisionEventId(event_id),
        setup_instance_id=SetupInstanceId(instance_id),
        kind=kind,
        previous_state="CANDIDATE",
        next_state=next_state,
        reason_code=reason,
        origin=Origin.ROBOT,
        controller=Controller.ROBOT,
        strategy_version="strategy-v1",
        hypothesis_id=None,
        setup_id="falling-wedge",
        entry_mode="breakout_retest",
        feature_snapshot_ref="feature-1",
        risk_snapshot_ref=(
            "risk-1" if kind is DecisionEventKind.RISK else None
        ),
        order_plan_id=None,
        occurred_at_ms=occurred_at_ms,
    )


def test_setup_projection_keeps_admitted_setup_without_fabricated_decision(tmp_path: Path):
    with DiaryDecisionStore.open(tmp_path / "diary.sqlite3") as store:
        store.create_setup_instance(_setup("setup-admitted", created_at_ms=100))

        projected = project_setup_list(store)

    assert projected == [
        {
            "setup_instance_id": "setup-admitted",
            "setup_id": "falling-wedge",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "pattern": "Falling Wedge",
            "direction": "LONG",
            "strategy_version": "strategy-v1",
            "hypothesis_id": None,
            "entry_mode": "breakout_retest",
            "origin": "ROBOT",
            "created_at_ms": 100,
            "status": "ADMITTED",
            "decision_state": None,
            "reason_code": None,
            "controller": None,
            "latest_decision_at_ms": None,
            "trade_episode_ids": [],
            "needs_attention": True,
            "missing_evidence": ["MISSING_DECISION_EVENTS"],
        }
    ]


def test_setup_projection_uses_terminal_outcome_reason_and_trade_link(tmp_path: Path):
    with DiaryDecisionStore.open(tmp_path / "diary.sqlite3") as store:
        store.create_setup_instance(_setup("setup-linked", created_at_ms=200))
        strategy = _event(
            "setup-linked",
            "strategy-1",
            kind=DecisionEventKind.STRATEGY,
            next_state="STRATEGY_APPROVED",
            reason="STRATEGY_OK",
            occurred_at_ms=210,
        )
        risk = _event(
            "setup-linked",
            "risk-1",
            kind=DecisionEventKind.RISK,
            next_state="RISK_APPROVED",
            reason="RISK_OK",
            occurred_at_ms=220,
        )
        store.append_decision_event(strategy)
        store.append_decision_event(risk)
        store.create_order_plan(
            OrderPlanRecord(
                order_plan_id=OrderPlanId("plan-1"),
                setup_instance_id=SetupInstanceId("setup-linked"),
                strategy_decision_event_id=strategy.decision_event_id,
                risk_decision_event_id=risk.decision_event_id,
                trading_account_id=TradingAccountId("paper"),
                symbol=Symbol("BTCUSDT"),
                side=PositionSide.LONG,
                created_at_ms=225,
            )
        )
        store.link_trade_episode(
            TradeEpisodeSetupLink(
                trade_episode_id=TradeEpisodeId("episode-1"),
                setup_instance_id=SetupInstanceId("setup-linked"),
                order_plan_id=OrderPlanId("plan-1"),
                linked_at_ms=230,
            )
        )
        store.record_setup_outcome(
            _event(
                "setup-linked",
                "outcome-1",
                kind=DecisionEventKind.SETUP_OUTCOME,
                next_state="EXPIRED",
                reason="APEX_REACHED",
                occurred_at_ms=240,
            )
        )

        projected = project_setup_list(store)

    assert projected[0]["status"] == "EXPIRED"
    assert projected[0]["decision_state"] == "EXPIRED"
    assert projected[0]["reason_code"] == "APEX_REACHED"
    assert projected[0]["controller"] == "ROBOT"
    assert projected[0]["trade_episode_ids"] == ["episode-1"]
    assert projected[0]["needs_attention"] is False
    assert projected[0]["missing_evidence"] == []


def test_setup_projection_is_newest_first(tmp_path: Path):
    with DiaryDecisionStore.open(tmp_path / "diary.sqlite3") as store:
        store.create_setup_instance(_setup("older", created_at_ms=100))
        store.create_setup_instance(_setup("newer", created_at_ms=300))

        projected = project_setup_list(store)

    assert [item["setup_instance_id"] for item in projected] == ["newer", "older"]
