from app.core.trades.enums import TradeDirection, TradeSide
from app.core.trades.execution_side import ExecutionSide


def test_execution_side_reuses_buy_sell_concept() -> None:
    assert ExecutionSide is TradeSide
    assert {item.value for item in ExecutionSide} == {"BUY", "SELL"}
    assert not issubclass(ExecutionSide, TradeDirection)
