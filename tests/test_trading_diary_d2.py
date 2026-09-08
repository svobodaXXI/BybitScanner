from pathlib import Path

import pytest

from terminal.diary import (
    DecisionEventId,
    DecisionEventKind,
    DecisionEventRecord,
    DiaryDecisionStore,
    DiaryImmutableConflict,
    DiaryLinkageError,
    OrderPlanId,
    OrderPlanRecord,
    SetupInstanceId,
    SetupInstanceRecord,
    TradeEpisodeId,
    TradeEpisodeSetupLink,
)
from terminal.domain.models import Controller, Origin, PositionSide, Symbol, TradingAccountId


def _setup(*, setup_id: str = "setup-1") -> SetupInstanceRecord:
    return SetupInstanceRecord(
        setup_instance_id=SetupInstanceId("si-1"),
        symbol=Symbol("BTCUSDT"),
        timeframe="5m",
        pattern="Falling Wedge",
        direction=PositionSide.LONG,
        strategy_version="strategy-v1",
        setup_id=setup_id,
        hypothesis_id="H-001",
        entry_mode="breakout_retest",
        origin=Origin.ROBOT,
        created_at_ms=100,
    )


def _decision(event_id: str, kind: DecisionEventKind, next_state: str, ts: int) -> DecisionEventRecord:
    return DecisionEventRecord(
        decision_event_id=DecisionEventId(event_id),
        setup_instance_id=SetupInstanceId("si-1"),
        kind=kind,
        previous_state="CANDIDATE",
        next_state=next_state,
        reason_code=f"REASON_{event_id}",
        origin=Origin.ROBOT,
        controller=Controller.ROBOT,
        strategy_version="strategy-v1",
        hypothesis_id="H-001",
        setup_id="setup-1",
        entry_mode="breakout_retest",
        feature_snapshot_ref="feature-snapshot-1",
        risk_snapshot_ref="risk-snapshot-1" if kind is DecisionEventKind.RISK else None,
        order_plan_id=None,
        occurred_at_ms=ts,
    )


def _plan() -> OrderPlanRecord:
    return OrderPlanRecord(
        order_plan_id=OrderPlanId("op-1"),
        setup_instance_id=SetupInstanceId("si-1"),
        strategy_decision_event_id=DecisionEventId("de-strategy"),
        risk_decision_event_id=DecisionEventId("de-risk"),
        trading_account_id=TradingAccountId("acct-1"),
        symbol=Symbol("BTCUSDT"),
        side=PositionSide.LONG,
        created_at_ms=130,
    )


def test_persists_setup_decisions_plan_and_episode_link_across_reopen(tmp_path: Path):
    path = tmp_path / "trading_diary.sqlite3"
    with DiaryDecisionStore.open(path) as store:
        store.create_setup_instance(_setup())
        store.append_decision_event(
            _decision("de-strategy", DecisionEventKind.STRATEGY, "STRATEGY_APPROVED", 110)
        )
        store.append_decision_event(
            _decision("de-risk", DecisionEventKind.RISK, "RISK_APPROVED", 120)
        )
        store.create_order_plan(_plan())
        store.link_trade_episode(
            TradeEpisodeSetupLink(
                trade_episode_id=TradeEpisodeId("te-1"),
                setup_instance_id=SetupInstanceId("si-1"),
                order_plan_id=OrderPlanId("op-1"),
                linked_at_ms=140,
            )
        )

    with DiaryDecisionStore.open(path) as store:
        assert store.get_setup_instance(SetupInstanceId("si-1")) == _setup()
        assert [event.decision_event_id.value for event in store.load_decision_events(SetupInstanceId("si-1"))] == [
            "de-strategy",
            "de-risk",
        ]
        assert store.get_order_plan(OrderPlanId("op-1")) == _plan()
        assert store.get_trade_episode_link(TradeEpisodeId("te-1")).setup_instance_id == SetupInstanceId("si-1")


def test_setup_and_decision_identities_are_idempotent_but_conflicting_reuse_fails(tmp_path: Path):
    with DiaryDecisionStore.open(tmp_path / "diary.sqlite3") as store:
        setup = _setup()
        assert store.create_setup_instance(setup) == setup
        assert store.create_setup_instance(setup) == setup
        with pytest.raises(DiaryImmutableConflict):
            store.create_setup_instance(_setup(setup_id="different"))

        event = _decision("de-strategy", DecisionEventKind.STRATEGY, "STRATEGY_APPROVED", 110)
        assert store.append_decision_event(event) == event
        assert store.append_decision_event(event) == event
        conflict = DecisionEventRecord(
            decision_event_id=event.decision_event_id,
            setup_instance_id=event.setup_instance_id,
            kind=event.kind,
            previous_state=event.previous_state,
            next_state="STRATEGY_REJECTED",
            reason_code=event.reason_code,
            origin=event.origin,
            controller=event.controller,
            strategy_version=event.strategy_version,
            hypothesis_id=event.hypothesis_id,
            setup_id=event.setup_id,
            entry_mode=event.entry_mode,
            feature_snapshot_ref=event.feature_snapshot_ref,
            risk_snapshot_ref=event.risk_snapshot_ref,
            order_plan_id=event.order_plan_id,
            occurred_at_ms=event.occurred_at_ms,
        )
        with pytest.raises(DiaryImmutableConflict):
            store.append_decision_event(conflict)


def test_records_skipped_invalidated_and_expired_as_durable_setup_outcomes(tmp_path: Path):
    with DiaryDecisionStore.open(tmp_path / "diary.sqlite3") as store:
        store.create_setup_instance(_setup())
        for index, outcome in enumerate(("SKIPPED", "INVALIDATED", "EXPIRED"), start=1):
            store.record_setup_outcome(
                _decision(f"outcome-{index}", DecisionEventKind.SETUP_OUTCOME, outcome, 200 + index)
            )
        assert [event.next_state for event in store.load_setup_outcomes()] == [
            "SKIPPED",
            "INVALIDATED",
            "EXPIRED",
        ]


def test_order_plan_requires_matching_strategy_and_risk_decisions(tmp_path: Path):
    with DiaryDecisionStore.open(tmp_path / "diary.sqlite3") as store:
        store.create_setup_instance(_setup())
        store.append_decision_event(
            _decision("de-strategy", DecisionEventKind.STRATEGY, "STRATEGY_APPROVED", 110)
        )
        with pytest.raises(DiaryLinkageError, match="strategy and risk"):
            store.create_order_plan(_plan())

        store.append_decision_event(
            _decision("de-risk", DecisionEventKind.STRATEGY, "RISK_APPROVED", 120)
        )
        with pytest.raises(DiaryLinkageError, match="STRATEGY then RISK"):
            store.create_order_plan(_plan())


def test_trade_episode_has_one_immutable_primary_setup_link(tmp_path: Path):
    with DiaryDecisionStore.open(tmp_path / "diary.sqlite3") as store:
        store.create_setup_instance(_setup())
        store.append_decision_event(
            _decision("de-strategy", DecisionEventKind.STRATEGY, "STRATEGY_APPROVED", 110)
        )
        store.append_decision_event(
            _decision("de-risk", DecisionEventKind.RISK, "RISK_APPROVED", 120)
        )
        store.create_order_plan(_plan())
        link = TradeEpisodeSetupLink(
            trade_episode_id=TradeEpisodeId("te-1"),
            setup_instance_id=SetupInstanceId("si-1"),
            order_plan_id=OrderPlanId("op-1"),
            linked_at_ms=140,
        )
        assert store.link_trade_episode(link) == link
        assert store.link_trade_episode(link) == link
        conflicting = TradeEpisodeSetupLink(
            trade_episode_id=TradeEpisodeId("te-1"),
            setup_instance_id=SetupInstanceId("si-1"),
            order_plan_id=OrderPlanId("op-1"),
            linked_at_ms=141,
        )
        with pytest.raises(DiaryImmutableConflict):
            store.link_trade_episode(conflicting)
