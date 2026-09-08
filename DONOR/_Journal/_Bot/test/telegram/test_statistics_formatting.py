import asyncio
from contextlib import suppress
from decimal import Decimal
from types import SimpleNamespace

from app.telegram.formatting import compact_statistics_text, statistics_decimal_text
from app.telegram.bot import bybit_sync_loop, run_bybit_incremental_sync
from app.telegram.bot import BotSingletonLock
from app.telegram.config import TelegramSettings


def summary(**values):
    defaults = dict(
        trade_count=3, net_pnl=Decimal("-1.2020386"), win_rate=Decimal("0.375"),
        profit_factor=Decimal("1.276666666"), expectancy=Decimal("-1.125497056666666666666"),
        currency="USDT", ready_count=3, excluded_incomplete_count=44, open_count=1,
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_statistics_display_bounds_decimal_values_without_float_conversion():
    text = compact_statistics_text(summary(), "Сегодня")
    assert "Net PnL: -1.202 USDT" in text
    assert "Win Rate: 37.5%" in text
    assert "Profit Factor: 1.28" in text
    assert "Expectancy: -1.1255 USDT" in text
    assert "Открытых: 1" in text
    assert "666666" not in text


def test_statistics_display_normalizes_negative_zero_and_trims_zeros():
    assert statistics_decimal_text(Decimal("-0.00001"), decimal_places=4) == "0"
    assert statistics_decimal_text(Decimal("1.2000"), decimal_places=4) == "1.2"
    assert statistics_decimal_text(Decimal("0"), decimal_places=2) == "0"


def test_temporary_bybit_error_is_safe_and_does_not_escape_sync_wrapper():
    class Runtime:
        async def sync_bybit_incremental(self, **kwargs):
            raise RuntimeError("temporary exchange failure")

    settings = TelegramSettings("token", 1, "db", None)
    assert __import__("asyncio").run(run_bybit_incremental_sync(Runtime(), settings, phase="interval")) is None


def test_local_bot_singleton_rejects_second_process_lock(tmp_path):
    first = BotSingletonLock(tmp_path / "telegram.lock")
    second = BotSingletonLock(tmp_path / "telegram.lock")
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_sync_loop_retries_on_next_tick_and_cancels_cleanly():
    class Runtime:
        def __init__(self):
            self.calls = 0

        async def sync_bybit_incremental(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary exchange failure")
            return None

    async def exercise():
        runtime = Runtime()
        settings = TelegramSettings("token", 1, "db", None, bybit_sync_interval_seconds=0.005)
        task = asyncio.create_task(bybit_sync_loop(runtime, settings))
        await asyncio.sleep(0.05)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert runtime.calls >= 2

    asyncio.run(exercise())
