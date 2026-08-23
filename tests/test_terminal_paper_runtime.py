import tempfile
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    ClientActionId,
    CommandResultStatus,
    MarketCommandRequest,
    VolumeRequest,
    VolumeUnit,
)
from terminal.domain.models import OrderSide
from terminal.runtime.paper_runtime import PaperRuntime


def test_composed_paper_runtime_market_buy_completes():
    with tempfile.TemporaryDirectory() as temp:
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
        try:
            result = runtime.api.market(
                MarketCommandRequest(
                    ClientActionId("runtime-buy-1"),
                    "BTCUSDT",
                    OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("50")),
                    Decimal("64250"),
                    "Percent",
                    Decimal("0.5"),
                )
            )

            assert result.status is CommandResultStatus.COMPLETED
            assert result.command_id is not None
            assert result.reconciliation_required is False
            assert len(runtime.store.load_executions()) == 1
        finally:
            runtime.close()
