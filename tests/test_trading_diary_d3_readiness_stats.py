from decimal import Decimal

from terminal.diary import (
    DiaryEnvironment,
    DiaryReadiness,
    DiaryStatisticsEngine,
    PnLComponents,
    PnLSource,
    TradeAnalyticsRecord,
    TradeEpisodeReconstructor,
    pnl_from_episode,
)
from terminal.domain.models import (
    Category,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    OrderId,
    OrderSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)


def _execution(exec_id: str, side: OrderSide, qty: str, price: str, fee: str, ts: int) -> Execution:
    return Execution(
        dedup_key=ExecutionDedupKey(
            TradingAccountId("acct"), Category.LINEAR, ExecutionId(exec_id)
        ),
        order_id=OrderId(f"order-{exec_id}"),
        symbol=Symbol("BTCUSDT"),
        side=side,
        price=Price(Decimal(price)),
        quantity=Quantity(Decimal(qty)),
        fee=Decimal(fee),
        exchange_timestamp_ms=ts,
    )


def _closed_episode(*, environment: DiaryEnvironment = DiaryEnvironment.LIVE, win: bool = True):
    exit_price = "110" if win else "90"
    return TradeEpisodeReconstructor().reconstruct(
        (
            _execution("e1" if win else "l1", OrderSide.BUY, "1", "100", "1", 1),
            _execution("e2" if win else "l2", OrderSide.SELL, "1", exit_price, "1", 2),
        ),
        environment=environment,
    )[0]


def _ready_record(*, win: bool = True, pattern: str = "Falling Wedge", entry_mode: str = "breakout"):
    episode = _closed_episode(win=win)
    return TradeAnalyticsRecord(
        episode=episode,
        pnl=pnl_from_episode(
            episode,
            funding=Decimal("0"),
            other_exchange_costs=Decimal("0"),
            manual_external_costs=Decimal("0"),
        ),
        pattern=pattern,
        setup_id="FW-LOWER-EDGE",
        entry_mode=entry_mode,
    )


def test_missing_cost_is_unknown_not_zero_and_blocks_ready_state():
    episode = _closed_episode()
    record = TradeAnalyticsRecord(
        episode=episode,
        pnl=pnl_from_episode(
            episode,
            funding=None,
            other_exchange_costs=Decimal("0"),
            manual_external_costs=Decimal("0"),
        ),
    )

    assert record.readiness is DiaryReadiness.CLOSED_INCOMPLETE
    assert record.pnl.net_pnl is None
    assert record.pnl.missing_components == ("funding",)
    assert record.missing_reasons == ("MISSING_FUNDING",)


def test_true_zero_costs_are_valid_and_closed_episode_becomes_ready():
    episode = _closed_episode()
    record = _ready_record()

    assert record.readiness is DiaryReadiness.CLOSED_READY
    assert record.pnl.source is PnLSource.DERIVED_FROM_EXECUTIONS
    assert record.pnl.net_pnl == Decimal("8")


def test_open_trade_is_excluded_even_when_cost_components_are_known():
    episode = TradeEpisodeReconstructor().reconstruct(
        (_execution("open-1", OrderSide.BUY, "1", "100", "1", 1),),
        environment=DiaryEnvironment.PAPER,
    )[0]
    record = TradeAnalyticsRecord(
        episode=episode,
        pnl=pnl_from_episode(
            episode,
            funding=Decimal("0"),
            other_exchange_costs=Decimal("0"),
            manual_external_costs=Decimal("0"),
        ),
    )

    assert record.readiness is DiaryReadiness.OPEN
    assert record.missing_reasons == ("TRADE_OPEN",)
    assert record.pnl.source is PnLSource.PAPER_SIMULATED


def test_statistics_use_only_closed_ready_and_report_coverage():
    win = _ready_record(win=True)
    loss = _ready_record(win=False)
    incomplete_episode = _closed_episode(environment=DiaryEnvironment.PAPER)
    incomplete = TradeAnalyticsRecord(
        episode=incomplete_episode,
        pnl=pnl_from_episode(
            incomplete_episode,
            funding=None,
            other_exchange_costs=Decimal("0"),
            manual_external_costs=Decimal("0"),
        ),
        pattern="Falling Wedge",
        setup_id="FW-LOWER-EDGE",
        entry_mode="breakout",
    )
    open_episode = TradeEpisodeReconstructor().reconstruct(
        (_execution("open-2", OrderSide.BUY, "1", "100", "1", 3),),
        environment=DiaryEnvironment.LIVE,
    )[0]
    open_record = TradeAnalyticsRecord(
        episode=open_episode,
        pnl=pnl_from_episode(
            open_episode,
            funding=Decimal("0"),
            other_exchange_costs=Decimal("0"),
            manual_external_costs=Decimal("0"),
        ),
        pattern="Falling Wedge",
        setup_id="FW-LOWER-EDGE",
        entry_mode="breakout",
    )

    stats = DiaryStatisticsEngine().summarize((win, loss, incomplete, open_record))

    assert stats.eligible_closed_ready == 2
    assert stats.excluded_incomplete == 1
    assert stats.excluded_open == 1
    assert stats.wins == 1
    assert stats.losses == 1
    assert stats.breakeven == 0
    assert stats.net_pnl == Decimal("-4")
    assert stats.average_net_pnl == Decimal("-2")
    assert stats.profit_factor == Decimal("8") / Decimal("12")
    assert stats.coverage_ratio == Decimal("0.5")


def test_cohort_filters_do_not_silently_pool_entry_modes():
    breakout = _ready_record(win=True, entry_mode="breakout")
    retest = _ready_record(win=False, entry_mode="breakout_retest")

    stats = DiaryStatisticsEngine().summarize(
        (breakout, retest),
        pattern="Falling Wedge",
        entry_mode="breakout",
    )

    assert stats.eligible_closed_ready == 1
    assert stats.wins == 1
    assert stats.losses == 0
    assert stats.net_pnl == Decimal("8")
    assert stats.coverage_ratio == Decimal("1")


def test_pnl_component_identity_must_match_episode():
    episode = _closed_episode()
    other = _closed_episode(win=False)
    pnl = PnLComponents(
        trade_episode_id=other.trade_episode_id,
        realized_price_pnl=Decimal("1"),
        execution_fees=Decimal("0"),
        funding=Decimal("0"),
        other_exchange_costs=Decimal("0"),
        manual_external_costs=Decimal("0"),
        source=PnLSource.DERIVED_FROM_EXECUTIONS,
    )

    try:
        TradeAnalyticsRecord(episode=episode, pnl=pnl)
    except ValueError as exc:
        assert "another trade episode" in str(exc)
    else:
        raise AssertionError("mismatched PnL identity must fail closed")
