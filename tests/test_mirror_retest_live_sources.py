import pytest

from mirror_retest_live_sources import (
    KLINE_URL,
    BybitClosedKlineSource,
    CandleSourceUnavailable,
    ProtectionHealthGate,
    parse_closed_klines,
)

FIVE, ONE = 300_000, 60_000
T0 = 1_792_400_000_000 - 1_792_400_000_000 % FIVE     # aligned 5m boundary


def row(start, o="1.0", h="1.2", l="0.9", c="1.1"):
    return [str(start), o, h, l, c, "10", "10"]


def payload(rows, exchange_ms, ret=0):
    return {"retCode": ret, "time": exchange_ms, "result": {"list": list(reversed(rows))}}   # Bybit: newest first


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeGet:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.handler(url, params or {})


# parse_closed_klines: closedness, sequence, validation.

def test_only_candles_closed_at_exchange_time_are_returned_in_order():
    rows = [row(T0), row(T0 + FIVE), row(T0 + 2 * FIVE)]            # the last one is still forming
    candles = parse_closed_klines(payload(rows, T0 + 2 * FIVE + 1_000), "5", local_now_ms=T0 + 2 * FIVE + 1_000)

    assert [c["open_time_ms"] for c in candles] == [T0, T0 + FIVE]
    assert all(c["close_time_ms"] <= T0 + 2 * FIVE for c in candles)


def test_a_missing_interval_is_passed_through_for_the_gap_detector():
    candles = parse_closed_klines(payload([row(T0), row(T0 + 2 * FIVE)], T0 + 4 * FIVE), "5",
                                  local_now_ms=T0 + 4 * FIVE)

    assert [c["open_time_ms"] for c in candles] == [T0, T0 + 2 * FIVE]


@pytest.mark.parametrize("body", [
    payload([row(T0), row(T0)], T0 + 3 * FIVE),                              # duplicate interval
    payload([row(T0 + 7)], T0 + 3 * FIVE),                                   # misaligned start
    payload([row(T0, h="0.95")], T0 + 3 * FIVE),                             # high below close
    payload([row(T0, o="abc")], T0 + 3 * FIVE),                              # not numeric
    payload([row(T0, l="0")], T0 + 3 * FIVE),                                # non-positive
    payload([["x"]], T0 + 3 * FIVE),                                         # malformed row
    payload([row(T0)], T0 + 3 * FIVE, ret=10001),                            # rejected request
    {"retCode": 0, "result": {"list": []}},                                  # no exchange time
    {"retCode": 0, "time": T0, "result": {}},                                # no list
])
def test_untrustworthy_responses_are_unavailable(body):
    with pytest.raises(CandleSourceUnavailable):
        parse_closed_klines(body, "5", local_now_ms=body.get("time") or T0)


def test_clock_disagreement_beyond_one_interval_is_unavailable():
    body = payload([row(T0)], T0 + 3 * FIVE)
    with pytest.raises(CandleSourceUnavailable):
        parse_closed_klines(body, "5", local_now_ms=T0 + 3 * FIVE + FIVE + 1)


# BybitClosedKlineSource: freshness, failures, 1m coverage.

def source_for(rows_by_interval, now, *, fail=None):
    def handler(url, params):
        assert url == KLINE_URL and params["category"] == "linear"
        if fail is not None:
            return fail(params)
        interval = params["interval"]
        rows = [r for r in rows_by_interval[interval] if params["start"] <= int(r[0]) <= params["end"]]
        return Response(payload(rows, now))
    get = FakeGet(handler)
    return BybitClosedKlineSource(http_get=get, clock_ms=lambda: now), get


def test_live_source_returns_fresh_closed_candles_after_the_cursor():
    now = T0 + 3 * FIVE + 5_000
    source, get = source_for({"5": [row(T0 + i * FIVE) for i in range(4)]}, now)
    candles = source.closed_candles("c1", "BTCUSDT", T0)

    assert [c["open_time_ms"] for c in candles] == [T0, T0 + FIVE, T0 + 2 * FIVE]   # T0+3*FIVE still forming
    assert get.calls[0][1]["start"] == T0


def test_stale_feed_returns_nothing_and_is_counted():
    now = T0 + 10 * FIVE
    source, _ = source_for({"5": [row(T0), row(T0 + FIVE)]}, now)

    assert source.closed_candles("c1", "BTCUSDT", T0) == []
    assert source.stale == 1


@pytest.mark.parametrize("failure", [
    lambda params: (_ for _ in ()).throw(ConnectionError("proxy down")),
    lambda params: Response({}, status=503),
    lambda params: Response(ValueError("not json")),
    lambda params: Response({"retCode": 10006, "time": T0}),
])
def test_network_failures_never_yield_candles(failure):
    source, _ = source_for({}, T0 + 3 * FIVE, fail=failure)

    assert source.closed_candles("c1", "BTCUSDT", T0) == []
    assert source.unavailable == 1


@pytest.mark.parametrize("failure", [
    lambda params: (_ for _ in ()).throw(ConnectionError("proxy down")),
    lambda params: Response({}, status=503),
    lambda params: Response({"retCode": 10006, "time": T0}),
])
def test_strict_trading_source_raises_on_unavailable_history(failure):
    now = T0 + 3 * FIVE
    _, get = source_for({}, now, fail=failure)
    trading = BybitClosedKlineSource(http_get=get, clock_ms=lambda: now, strict_availability=True)
    with pytest.raises(CandleSourceUnavailable):
        trading.closed_candles("c1", "BTCUSDT", T0)
    assert trading.unavailable == 1


def test_strict_trading_source_raises_on_stale_or_missing_expected_candles():
    stale_now = T0 + 10 * FIVE
    _, stale_get = source_for({"5": [row(T0), row(T0 + FIVE)]}, stale_now)
    trading = BybitClosedKlineSource(http_get=stale_get, clock_ms=lambda: stale_now,
                                    strict_availability=True)
    with pytest.raises(CandleSourceUnavailable, match="stale"):
        trading.closed_candles("c1", "BTCUSDT", T0)
    assert trading.stale == 1

    now = T0 + 2 * FIVE
    _, missing_get = source_for({"5": []}, now)
    missing = BybitClosedKlineSource(http_get=missing_get, clock_ms=lambda: now,
                                    strict_availability=True)
    with pytest.raises(CandleSourceUnavailable, match="expected"):
        missing.closed_candles("c1", "BTCUSDT", T0)

    before_next_close = T0 + 1_000
    _, idle_get = source_for({"5": []}, before_next_close)
    idle = BybitClosedKlineSource(http_get=idle_get, clock_ms=lambda: before_next_close,
                                 strict_availability=True)
    assert idle.closed_candles("c1", "BTCUSDT", T0) == []
    assert not idle_get.calls                  # no missing candle while the next one is still forming


def test_live_source_requires_a_cursor():
    source, _ = source_for({"5": []}, T0)
    with pytest.raises(CandleSourceUnavailable):
        source.closed_candles("c1", "BTCUSDT", None)


def test_fine_candles_must_cover_the_whole_closed_5m_candle():
    coarse = {"open_time_ms": T0, "close_time_ms": T0 + FIVE}
    full, _ = source_for({"1": [row(T0 + i * ONE) for i in range(5)]}, T0 + 2 * FIVE)
    assert [c["open_time_ms"] for c in full.fine_candles("BTCUSDT", coarse)] == [T0 + i * ONE for i in range(5)]

    holed, _ = source_for({"1": [row(T0 + i * ONE) for i in (0, 1, 3, 4)]}, T0 + 2 * FIVE)
    with pytest.raises(CandleSourceUnavailable):
        holed.fine_candles("BTCUSDT", coarse)


# ProtectionHealthGate.

HEALTHY = {"ok": True, "healthy": True, "unhealthy_symbols": {}, "ingress": {"current_pending": 0}}


def gate_with(handler):
    return ProtectionHealthGate(http_get=FakeGet(lambda url, params: handler()))


def test_gate_opens_only_for_a_healthy_idle_protection():
    gate = gate_with(lambda: Response(HEALTHY))

    assert gate.busy() is False and gate.last_reason is None


@pytest.mark.parametrize(("body", "reason"), [
    ({**HEALTHY, "healthy": False}, "protection_unhealthy"),
    ({**HEALTHY, "healthy": None}, "protection_unhealthy"),
    ({**HEALTHY, "ok": False}, "not_ok"),
    ({**HEALTHY, "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"}}, "unhealthy_symbols"),
    ({**HEALTHY, "unhealthy_symbols": None}, "unhealthy_symbols"),
    ({**HEALTHY, "ingress": {"current_pending": 3}}, "ingress_pending_unknown_or_nonzero"),
    ({**HEALTHY, "ingress": {}}, "ingress_pending_unknown_or_nonzero"),
    ({**HEALTHY, "ingress": None}, "ingress_pending_unknown_or_nonzero"),
    ([], "not_ok"),
])
def test_unknown_or_unhealthy_protection_has_priority(body, reason):
    gate = gate_with(lambda: Response(body))

    assert gate.busy() is True and gate.last_reason == reason


@pytest.mark.parametrize("handler", [
    lambda: (_ for _ in ()).throw(ConnectionError("backend down")),
    lambda: Response(HEALTHY, status=503),
    lambda: Response(ValueError("not json")),
])
def test_unreachable_backend_means_busy(handler):
    gate = gate_with(handler)

    assert gate.busy() is True
