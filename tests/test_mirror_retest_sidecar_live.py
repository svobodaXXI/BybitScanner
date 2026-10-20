"""Sidecar with the live input adapters, fed by the real saved case through a simulated Bybit/backend."""

import pytest

from geometry.naked_retest import EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN, EVENT_RETEST_UNPROVEN
from mirror_retest_live_sources import BybitClosedKlineSource, ProtectionHealthGate
from tests.test_mirror_retest_sidecar import SyncWriter, make_db, real_case, upper, write_envelope
from mirror_retest_observer import ObservationJournal
from mirror_retest_sidecar import MirrorSidecar, TradingAccountId

HEALTHY = {"ok": True, "healthy": True, "unhealthy_symbols": {}, "ingress": {"current_pending": 0}}


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError("HTTP error")

    def json(self):
        return self.body


class SimulatedBybit:
    """Serves the saved candles in Bybit's wire format; failures are switchable per interval."""

    def __init__(self, data, now):
        self.rows = {"5": data["coarse_5m"], "1": data["fine_1m"]}
        self.now, self.down = now, set()

    def __call__(self, url, params=None, timeout=None):
        interval = params["interval"]
        if interval in self.down:
            raise ConnectionError("network failure")
        rows = [[str(c["open_time_ms"]), str(c["open"]), str(c["high"]), str(c["low"]), str(c["close"]), "1", "1"]
                for c in self.rows[interval] if params["start"] <= c["open_time_ms"] <= params["end"]]
        return Response({"retCode": 0, "time": self.now, "result": {"list": rows[::-1]}})


class SimulatedBackend:
    def __init__(self):
        self.body, self.up = dict(HEALTHY), True

    def __call__(self, url, timeout=None):
        if not self.up:
            raise ConnectionError("backend down")
        return Response(self.body)


def build(tmp_path):
    data = real_case()
    now = data["coarse_5m"][-1]["close_time_ms"] + 1_000
    bybit, backend = SimulatedBybit(data, now), SimulatedBackend()
    db = tmp_path / "paper.sqlite3"
    make_db(db, [("ref1", 10, "Rising Wedge")])
    write_envelope(tmp_path / "candidates", "ref1", data["manifest"])
    sidecar = MirrorSidecar(
        database_path=db, account=TradingAccountId("paper"), candidate_store_dir=tmp_path / "candidates",
        candles=BybitClosedKlineSource(http_get=bybit, clock_ms=lambda: now),
        journal=ObservationJournal(tmp_path / "observations.jsonl"),
        protection_busy=ProtectionHealthGate(http_get=backend).busy,
        clock_ms=lambda: now, writer=SyncWriter())
    return sidecar, bybit, backend


def test_live_adapters_reproduce_the_saved_case(tmp_path):
    sidecar, _, _ = build(tmp_path)
    records = upper(sidecar.cycle())

    assert [(r.event, r.decision) for r in records] == [(EVENT_NAKED_BREAKOUT, "WAIT"), (EVENT_RETEST_PROVEN, "BLOCK")]
    assert all(not r.executable and not r.admission_allowed for r in records)
    assert upper(sidecar.cycle()) == []


def test_network_failure_holds_the_cursor_and_recovers(tmp_path):
    sidecar, bybit, _ = build(tmp_path)
    bybit.down.add("5")
    assert sidecar.cycle() == []
    assert sidecar.candles.unavailable >= 1

    bybit.down.clear()
    assert [r.event for r in upper(sidecar.cycle())] == [EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN]


@pytest.mark.parametrize("problem", ["down", "unhealthy", "pending"])
def test_unknown_or_busy_protection_stops_all_processing(tmp_path, problem):
    sidecar, bybit, backend = build(tmp_path)
    if problem == "down":
        backend.up = False
    elif problem == "unhealthy":
        backend.body = {**HEALTHY, "healthy": False}
    else:
        backend.body = {**HEALTHY, "ingress": {"current_pending": 2}}
    calls_before = len(getattr(bybit, "calls", []))

    assert sidecar.cycle() == []
    assert sidecar.metrics.skipped_for_protection == 1 and sidecar.metrics.candidates_tracked == 0
    assert len(getattr(bybit, "calls", [])) == calls_before

    backend.up, backend.body = True, dict(HEALTHY)
    assert [r.event for r in upper(sidecar.cycle())] == [EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN]


def test_missing_1m_proof_never_turns_into_an_unproven_retest(tmp_path):
    sidecar, bybit, _ = build(tmp_path)
    bybit.down.add("1")
    first = upper(sidecar.cycle())

    assert [r.event for r in first] == [EVENT_NAKED_BREAKOUT]
    assert sidecar.metrics.fine_unavailable >= 1
    assert all(r.event != EVENT_RETEST_UNPROVEN for r in first)

    bybit.down.clear()
    assert [r.event for r in upper(sidecar.cycle())] == [EVENT_RETEST_PROVEN]
