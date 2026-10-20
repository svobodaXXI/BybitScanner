"""MIRROR-INTEGRATION-4 fault injection over the live read-only adapters.

Every test runs the real sidecar on the saved real case through the simulated
Bybit/backend of ``test_mirror_retest_sidecar_live``. Bounded on purpose: the
whole file creates a few hundred small objects and no threads or sleeps.
"""

import ast
from pathlib import Path

import pytest

import mirror_retest_live_sources as live_module
from geometry.naked_retest import EVENT_DATA_GAP, EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN
from mirror_retest_live_sources import (
    BybitClosedKlineSource, CandleSourceUnavailable, ProtectionHealthGate,
)
from mirror_retest_observer import ObservationJournal
from mirror_retest_sidecar import MirrorSidecar, PROTECTION_RECHECK_EVERY, TradingAccountId
from tests.test_mirror_retest_sidecar import SyncWriter, make_db, real_case, upper, write_envelope
from tests.test_mirror_retest_sidecar_live import HEALTHY, Response, SimulatedBackend, SimulatedBybit

FIVE = 300_000


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class LeakyBybit(SimulatedBybit):
    """Ignores the ``end`` bound: the server hands out candles that are still in the future."""

    def __call__(self, url, params=None, timeout=None):
        interval = params["interval"]
        if interval in self.down:
            raise ConnectionError("network failure")
        rows = [[str(c["open_time_ms"]), str(c["open"]), str(c["high"]), str(c["low"]), str(c["close"]), "1", "1"]
                for c in self.rows[interval] if params["start"] <= c["open_time_ms"]]
        return Response({"retCode": 0, "time": self.now, "result": {"list": rows[::-1]}})


def build(tmp_path, *, bybit_cls=SimulatedBybit, now=None, coarse=None, arrivals=None, busy=None):
    data = real_case()
    tmp_path.mkdir(parents=True, exist_ok=True)
    if coarse is not None:
        data = dict(data, coarse_5m=coarse)
    clock = Clock(now if now is not None else data["coarse_5m"][-1]["close_time_ms"] + 1_000)
    bybit = bybit_cls(data, clock.now)
    backend = SimulatedBackend()
    db = tmp_path / "paper.sqlite3"
    refs = arrivals if arrivals is not None else [("ref1", 10, "Rising Wedge")]
    make_db(db, refs)
    for index, (ref, _, _) in enumerate(refs):
        write_envelope(tmp_path / "candidates", ref, data["manifest"], formation=f"f{index}")
    sidecar = MirrorSidecar(
        database_path=db, account=TradingAccountId("paper"), candidate_store_dir=tmp_path / "candidates",
        candles=BybitClosedKlineSource(http_get=bybit, clock_ms=clock),
        journal=ObservationJournal(tmp_path / "observations.jsonl"),
        protection_busy=busy if busy is not None else ProtectionHealthGate(http_get=backend).busy,
        clock_ms=clock, writer=SyncWriter())
    return sidecar, bybit, backend, clock, data


def ids(records):
    return [(r.boundary_id, r.event, r.decision, r.candle_close_time_ms) for r in records]


# --- no look-ahead -----------------------------------------------------------------------------

def test_candles_after_exchange_time_are_never_consumed_even_when_the_server_leaks_them(tmp_path):
    data = real_case()
    breakout_close = data["manifest"]["breakout_close_time_ms"]
    sidecar, bybit, _, clock, _ = build(tmp_path, bybit_cls=LeakyBybit, now=breakout_close + 5_000)

    early = upper(sidecar.cycle())
    assert [(r.event, r.decision) for r in early] == [(EVENT_NAKED_BREAKOUT, "WAIT")]   # the retest is still the future
    assert all(r.candle_close_time_ms <= clock.now for r in early)

    clock.now = bybit.now = data["coarse_5m"][-1]["close_time_ms"] + 1_000
    later = upper(sidecar.cycle())
    assert [r.event for r in later] == [EVENT_RETEST_PROVEN]


def test_observations_at_time_t_do_not_depend_on_data_after_t(tmp_path):
    data = real_case()
    cut = data["manifest"]["breakout_close_time_ms"] + 2 * FIVE + 5_000
    full, *_ = build(tmp_path / "full", bybit_cls=LeakyBybit, now=cut)
    trimmed_coarse = [c for c in data["coarse_5m"] if c["close_time_ms"] <= cut]
    trimmed, *_ = build(tmp_path / "trimmed", now=cut, coarse=trimmed_coarse)

    assert ids(full.cycle()) == ids(trimmed.cycle())


def test_a_local_clock_far_ahead_of_the_exchange_cannot_pull_the_feed_forward(tmp_path):
    data = real_case()
    sidecar, bybit, _, clock, _ = build(tmp_path)
    bybit.now = data["manifest"]["breakout_close_time_ms"]          # exchange is far behind the local clock

    assert sidecar.cycle() == []
    assert sidecar.candles.unavailable >= 1


# --- network errors and continuity ---------------------------------------------------------------

class Flapping:
    """Fails one request in ``period`` (the first of each group): models a flaky proxy."""

    def __init__(self, inner, period):
        self.inner, self.period, self.calls = inner, period, 0

    def __call__(self, url, params=None, timeout=None):
        self.calls += 1
        if self.calls % self.period == 1:
            raise TimeoutError("proxy timeout")
        return self.inner(url, params=params, timeout=timeout)


def test_flapping_network_converges_to_the_fault_free_result_without_duplicates(tmp_path):
    baseline, *_ = build(tmp_path / "base")
    expected = ids(upper(baseline.cycle()))
    assert expected

    flaky, bybit, *_ = build(tmp_path / "flaky")
    flaky.candles._get = Flapping(bybit, 3)
    produced = []
    for _ in range(12):                                    # bounded retry horizon
        produced.extend(upper(flaky.cycle()))
    assert ids(produced) == expected                       # nothing skipped, nothing repeated
    assert flaky.candles.unavailable >= 1


def test_a_permanently_failing_1m_request_blocks_the_retest_but_never_fakes_it(tmp_path):
    baseline, *_ = build(tmp_path / "base")
    expected = ids(upper(baseline.cycle()))

    stuck, bybit, *_ = build(tmp_path / "stuck")
    stuck.candles._get = Flapping(bybit, 2)                # every 1m request lands on the failing slot
    produced = []
    for _ in range(12):
        produced.extend(upper(stuck.cycle()))

    assert ids(produced) == expected[:len(produced)]       # only a prefix of the truth, in order
    assert all(r.event != "RETEST_UNPROVEN" for r in produced)
    assert stuck.metrics.fine_unavailable >= 1


@pytest.mark.parametrize("problem", [
    lambda params: Response({"retCode": 10006, "time": 0}, status=200),     # rate limit as a body
    lambda params: Response({}, status=429),                               # rate limit as HTTP
    lambda params: Response({"retCode": 0, "time": 1, "result": {"list": [["x"]]}}),
    lambda params: Response(None),
])
def test_rate_limits_and_garbage_hold_the_cursor_and_never_raise(tmp_path, problem):
    sidecar, bybit, *_ = build(tmp_path)
    sidecar.candles._get = lambda url, params=None, timeout=None: problem(params)

    assert sidecar.cycle() == [] and sidecar.cycle() == []
    cursor = sidecar.candle_cursor["ref1"]

    sidecar.candles._get = bybit                           # service recovers
    assert upper(sidecar.cycle())
    assert sidecar.candle_cursor["ref1"] > cursor


def test_a_missing_5m_candle_in_the_wire_data_is_a_gap_not_a_continuous_series(tmp_path):
    data = real_case()
    breakout = data["manifest"]["breakout_close_time_ms"]
    holed = [c for c in data["coarse_5m"] if c["close_time_ms"] != breakout + FIVE]
    sidecar, bybit, *_ = build(tmp_path, coarse=holed)

    records = upper(sidecar.cycle())
    assert [r.event for r in records] == [EVENT_NAKED_BREAKOUT, EVENT_DATA_GAP]
    assert upper(sidecar.cycle()) == []                    # held, not re-reported or silently continued

    bybit.rows["5"] = data["coarse_5m"]                    # the exchange now serves the full series
    assert [r.event for r in upper(sidecar.cycle())] == [EVENT_RETEST_PROVEN]


def test_a_hole_in_the_1m_coverage_never_becomes_an_unproven_retest(tmp_path):
    data = real_case()
    sidecar, bybit, *_ = build(tmp_path)
    ordered = sorted(data["fine_1m"], key=lambda c: c["open_time_ms"])
    bybit.rows["1"] = [c for c in ordered if c is not ordered[1]]          # one minute missing

    held = []
    for _ in range(3):
        held.extend(upper(sidecar.cycle()))
    assert all(r.event not in ("RETEST_UNPROVEN", EVENT_RETEST_PROVEN) for r in held)
    assert sidecar.metrics.fine_unavailable >= 1

    bybit.rows["1"] = data["fine_1m"]                                      # complete proof arrives
    assert [r.event for r in upper(sidecar.cycle())] == [EVENT_RETEST_PROVEN]


def test_source_requests_per_call_are_bounded(tmp_path):
    step = 300_000
    calls = []

    def endless(url, params=None, timeout=None):
        calls.append(params)
        count = min(params["limit"], (params["end"] - params["start"]) // step + 1)
        rows = [[str(params["start"] + i * step), "1", "1.1", "0.9", "1", "1", "1"] for i in range(count)]
        return Response({"retCode": 0, "time": NOW, "result": {"list": rows[::-1]}})

    start = 1_700_000_000_000 - 1_700_000_000_000 % step
    NOW = start + 5000 * step + 1_000
    source = BybitClosedKlineSource(http_get=endless, clock_ms=lambda: NOW)

    candles = source.closed_candles("c1", "BTCUSDT", start)
    assert len(calls) <= live_module.MAX_PAGES_PER_CALL
    assert len(candles) <= live_module.MAX_PAGES_PER_CALL * live_module.PAGE_LIMIT


# --- protection fail-closed ----------------------------------------------------------------------

@pytest.mark.parametrize("error", [TimeoutError("t"), OSError("down"), ValueError("bad json"), RuntimeError("x")])
def test_protection_health_errors_mean_busy(error):
    def boom(url, timeout=None):
        raise error

    gate = ProtectionHealthGate(http_get=boom)
    assert gate.busy() is True and gate.last_reason == "backend_unreachable"


def test_protection_turning_busy_mid_cycle_stops_processing_at_once(tmp_path):
    arrivals = [(f"ref{i}", 10 + i, "Rising Wedge") for i in range(PROTECTION_RECHECK_EVERY + 3)]
    state = {"calls": 0}

    def busy():
        state["calls"] += 1
        return state["calls"] > 1                          # idle at the start of the cycle, busy at the first re-check

    sidecar, bybit, *_ = build(tmp_path, arrivals=arrivals, busy=busy)
    advanced = []
    original = sidecar.candles.closed_candles

    def counting(candidate_id, symbol, after_close_ms):
        advanced.append(candidate_id)
        return original(candidate_id, symbol, after_close_ms)

    sidecar.candles.closed_candles = counting
    sidecar.cycle()
    assert len(advanced) == PROTECTION_RECHECK_EVERY       # the remaining candidates were not touched
    assert sidecar.metrics.skipped_for_protection == 1


def test_protection_with_pending_ingress_or_unknown_fields_has_priority():
    for body in ({**HEALTHY, "ingress": {"current_pending": 3}}, {**HEALTHY, "ingress": {}},
                 {k: v for k, v in HEALTHY.items() if k != "unhealthy_symbols"}, {**HEALTHY, "healthy": "true"}):
        gate = ProtectionHealthGate(http_get=lambda url, timeout=None, body=body: Response(body))
        assert gate.busy() is True


# --- no influence on Robot / trading --------------------------------------------------------------

def test_live_adapters_are_read_only_and_import_no_trading_modules():
    source = Path(live_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for forbidden in (".post(", ".put(", ".delete(", "/v5/order", "/v5/position", "/v5/account",
                      "api_key", "api_secret", "sign(", "SQLiteStore", "runtime.call", "admit_", "place_"):
        assert forbidden not in source
    assert live_module.KLINE_URL.endswith("/v5/market/kline")
    assert live_module.PROTECTION_HEALTH_PATH == "/api/robot/protection-health"
    top_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    imported = {getattr(n, "module", None) or a.name for n in top_level for a in getattr(n, "names", [])}
    assert not any(str(m).startswith("terminal") for m in imported)       # only the lazy session factory reaches terminal


def test_sidecar_cycle_under_fault_leaves_the_database_untouched(tmp_path):
    sidecar, bybit, *_ = build(tmp_path)
    path = tmp_path / "paper.sqlite3"
    sidecar.candles._get = Flapping(bybit, 3)
    for _ in range(4):
        sidecar.cycle()
    before = path.read_bytes()
    for _ in range(4):
        sidecar.cycle()
    assert path.read_bytes() == before
