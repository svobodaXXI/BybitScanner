"""Deterministic unpacked-package smoke for native Box Robot SIMULATION."""
from decimal import Decimal
from unittest.mock import patch

from geometry.ikigai_box import IkigaiBoxFormation
from research.historical_market_replay import Candle
from research.simulator_v2.ikigai_observer import IkigaiScannerConfig
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms
from research.simulator_v2.robot_sandbox import ConnectedSimulationRobot
from research.simulator_v2.session import VirtualReplaySession

D = Decimal
M1 = 60_000


def candle(index: int, *, opening="100", high="101", low="99", close="100") -> Candle:
    return Candle(
        start_ms=index * M1,
        interval_ms=M1,
        open=D(opening),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D("1"),
    )


def formation() -> IkigaiBoxFormation:
    return IkigaiBoxFormation(
        direction="LONG",
        impulse_start_index=1,
        impulse_end_index=2,
        box_start_index=3,
        box_end_index=7,
        second_start_index=8,
        as_of_index=31,
        anchor_start_index=1,
        anchor_end_index=2,
        anchor_start_price=112.94498381877023,
        anchor_end_price=100.0,
        box_low=100.0,
        box_high=108.0,
        second_extreme=91.0,
        fibonacci_1_0=100.0,
        fibonacci_1_618=92.0,
        fibonacci_2_618=79.05501618122977,
    )


def terms() -> BoxSimulationRiskTerms:
    return BoxSimulationRiskTerms(
        tick_size=D("0.01"),
        working_quantity=D("8"),
        quantity_step=D("1"),
        minimum_quantity=D("1"),
        maximum_notional_usdt=D("1000"),
        maximum_loss_usdt=D("300"),
        entry_fee_rate=D("0.0002"),
        exit_fee_rate=D("0.0006"),
        adverse_stop_slippage_per_unit=D("0"),
        additional_cost_allowance_usdt=D("0"),
    )


def main() -> None:
    session = VirtualReplaySession(
        simulation_run_id="windows_box_package_smoke",
        symbol="BTCUSDT",
        initial_balance=D("1000"),
        taker_fee_rate=D("0.0006"),
        maker_fee_rate=D("0.0002"),
        ikigai_scanner_config=IkigaiScannerConfig(
            window_bars=50, timeframes=("1m",),
        ),
    )
    with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box", return_value=None):
        for index in range(31):
            session.step(candle(index))
    with patch(
        "research.simulator_v2.ikigai_observer.detect_ikigai_box",
        return_value=formation(),
    ):
        session.step(candle(31))

    observation = session.ikigai_scanner.observations[-1]
    with ConnectedSimulationRobot(
        session, tick_size=D("0.01"), terms=terms(),
    ) as robot:
        robot.admit(observation)
        assert len(session.exchange.robot_limits) == 4

        with patch(
            "research.simulator_v2.ikigai_observer.detect_ikigai_box",
            return_value=None,
        ):
            session.step(candle(
                32, opening="100", high="100", low="93.5", close="94",
            ))
        robot.after_committed_minute()
        assert len(session.account.fills) == 1
        assert sum(not item.reduce_only for item in session.exchange.robot_limits) == 3
        assert sum(item.reduce_only for item in session.exchange.robot_limits) == 1

        with patch(
            "research.simulator_v2.ikigai_observer.detect_ikigai_box",
            return_value=None,
        ):
            session.step(candle(
                33, opening="94", high="95", low="90", close="91",
            ))
        robot.after_committed_minute()

        snapshot = session.account.snapshot(
            as_of_ms=session.virtual_time_ms, mark_price=D("91"),
        )
        assert snapshot.position_quantity == 0
        assert len(session.account.fills) == 2
        assert snapshot.fees > 0
        assert snapshot.realized_net_pnl == (
            snapshot.realized_gross_pnl - snapshot.fees
        )
        assert not session.exchange.robot_limits
        assert session.exchange.robot_stop is None
        trade = robot._store.load_robot_trades_with_events_since(
            robot.account_id, 0,
        )[0]
        assert trade.exit_reason == "STOP"
        assert trade.realized_pnl_usdt == snapshot.realized_gross_pnl
        assert trade.fees_costs_usdt == snapshot.fees

    print(
        "WINDOWS_BOX_LIFECYCLE_SMOKE_OK "
        f"gross={snapshot.realized_gross_pnl} fees={snapshot.fees} "
        f"net={snapshot.realized_net_pnl}"
    )


if __name__ == "__main__":
    main()
