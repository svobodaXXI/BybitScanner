import pytest

from app.core.instruments import Instrument, InstrumentId


def test_instrument_normalizes_human_readable_catalog_fields():
    item = Instrument(InstrumentId.generate(), " btc/usdt ", " Bitcoin / Tether ", " bybit ", " spot ")
    assert item.symbol == "BTC/USDT"
    assert item.name == "Bitcoin / Tether"
    assert item.exchange == "BYBIT"
    assert item.market == "SPOT"
    assert item.label == "BTC/USDT — Bitcoin / Tether (BYBIT / SPOT)"


def test_instrument_requires_symbol_and_name():
    with pytest.raises(ValueError):
        Instrument(InstrumentId.generate(), "", "Bitcoin")
    with pytest.raises(ValueError):
        Instrument(InstrumentId.generate(), "BTC", "")
