import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

import mirror_retest_sidecar as sidecar_module
from geometry.naked_retest import EVENT_DATA_GAP, EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN
from mirror_retest_observer import AccountFacts, ObservationJournal
from mirror_retest_sidecar import MirrorSidecar
from robot_candidate_store import SCHEMA_VERSION
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotAutoDecisionRecord, SQLiteStore
from terminal.runtime.paper_runtime import _BestEffortDiagnosticsWriter

ACCOUNT = TradingAccountId("paper")
FIXTURE = Path(__file__).parent / "fixtures" / "mirror_integration_2" / "proven_1000luncusdt_upper.json"


def real_case():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def write_envelope(store_dir: Path, ref: str, manifest: dict, *, formation: str = "f1", symbol=None):
    """Envelope whose snapshot reproduces the frozen RETEST-4 upper boundary of the real case."""

    store_dir.mkdir(parents=True, exist_ok=True)
    line = {"slope": manifest["slope_per_ms"] * 60_000, "intercept": manifest["anchor_price"]}
    envelope = {
        "schema_version": SCHEMA_VERSION, "candidate_id": ref, "status": "AVAILABLE",
        "symbol": symbol or manifest["symbol"], "timeframe": "5",
        "created_at": datetime.fromtimestamp(manifest["as_of_ms"] / 1000, timezone.utc).isoformat(),
        "signal_snapshot": {
            "pattern": manifest["pattern"], "scanner_formation_id": formation,
            "robot_geometry": {"robot_coordinate_timeframe": "1", "upper_line": line, "lower_line": line},
            "scanner_geometry_cursor": {"timeframe": "1", "geometry_index": 0,
                                        "source_candle_time_ms": manifest["anchor_time_ms"]},
        },
    }
    (store_dir / f"{ref}.json").write_text(json.dumps(envelope), encoding="utf-8")


def make_db(path: Path, arrivals):
    with SQLiteStore.open(path) as store:
        store.initialize_robot_autopilot_state(ACCOUNT, updated_at_ms=0)
        store.update_robot_autopilot_state(ACCOUNT, mode="SHADOW", expected_version=1, updated_at_ms=1)
        for index, (ref, at_ms, pattern) in enumerate(arrivals):
            store.append_robot_auto_decision(RobotAutoDecisionRecord(
                decision_id=f"d{index}", trading_account_id=ACCOUNT, candidate_ref=ref, pattern=pattern,
                symbol=Symbol("1000LUNCUSDT"), timeframe="5", source_identity=f"{ref}:sha{index}",
                snapshot_sha256=None, mode="SHADOW", policy_version="v1", outcome="WAIT",
                reason_code="CANDIDATE_FRESHNESS_UNKNOWN", evaluated_at_ms=at_ms, resulting_candidate_id=None))


class ListSource:
    def __init__(self, candles):
        self.candles = list(candles)

    def closed_candles(self, candidate_id, symbol, after_close_ms):
        return [c for c in self.candles if after_close_ms is None or c["close_time_ms"] > after_close_ms]


class SyncWriter:
    """Runs submitted writes inline so assertions see the journal immediately."""

    def __init__(self):
        self.dropped = 0

    def submit(self, write):
        write()
        return True


def make_sidecar(tmp_path, *, arrivals=None, candles=None, busy=lambda: False, writer=None, reader_factory=None):
    data = real_case()
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "paper.sqlite3"
    make_db(db, arrivals if arrivals is not None else [("ref1", 10, "Rising Wedge")])
    write_envelope(tmp_path / "candidates", "ref1", data["manifest"])
    kwargs = {}
    if reader_factory is not None:
        kwargs["reader_factory"] = reader_factory
    return MirrorSidecar(
        database_path=db, account=ACCOUNT, candidate_store_dir=tmp_path / "candidates",
        candles=ListSource(candles if candles is not None else data["coarse_5m"]),
        journal=ObservationJournal(tmp_path / "observations.jsonl"), protection_busy=busy,
        clock_ms=lambda: data["manifest"]["as_of_ms"] + 86_400_000,
        writer=writer if writer is not None else SyncWriter(), **kwargs)


def upper(records):
    return [r for r in records if r.boundary_id.endswith(":upper")]


def test_real_saved_case_flows_from_arrival_to_observe_only_records(tmp_path):
    sidecar = make_sidecar(tmp_path)
    records = sidecar.cycle()

    assert sidecar.metrics.candidates_tracked == 1
    events = [(r.event, r.decision) for r in upper(records)]
    assert events == [(EVENT_NAKED_BREAKOUT, "WAIT"), (EVENT_RETEST_PROVEN, "BLOCK")]
    assert upper(records)[0].candle_close_time_ms == real_case()["manifest"]["breakout_close_time_ms"]
    lines = (tmp_path / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(records)
    assert all(not json.loads(line)["executable"] and not json.loads(line)["admission_allowed"] for line in lines)


def test_repeated_candidates_and_formations_are_tracked_once_and_not_re_emitted(tmp_path):
    data = real_case()
    sidecar = make_sidecar(tmp_path, arrivals=[("ref1", 10, "Rising Wedge"), ("ref1", 20, "Rising Wedge"),
                                               ("ref2", 30, "Rising Wedge"), ("box", 40, "IKIGAI_BOX")])
    write_envelope(tmp_path / "candidates", "ref2", data["manifest"], formation="f1")   # same formation
    first = sidecar.cycle()
    second = sidecar.cycle()

    assert sidecar.metrics.candidates_tracked == 1
    assert sidecar.metrics.duplicates_ignored >= 1
    assert first and second == []
    assert len((tmp_path / "observations.jsonl").read_text(encoding="utf-8").splitlines()) == len(first)


def test_missing_candle_after_breakout_records_a_data_gap_wait(tmp_path):
    data = real_case()
    breakout = data["manifest"]["breakout_close_time_ms"]
    candles = [c for c in data["coarse_5m"] if c["close_time_ms"] != breakout + 300_000]
    records = upper(make_sidecar(tmp_path, candles=candles).cycle())

    assert [r.event for r in records] == [EVENT_NAKED_BREAKOUT, EVENT_DATA_GAP]   # the gap is recorded once
    assert records[-1].decision == "WAIT" and "data_unreliable" in records[-1].reasons


def test_gap_holds_the_cursor_until_the_missing_candle_arrives(tmp_path):
    data = real_case()
    breakout = data["manifest"]["breakout_close_time_ms"]
    missing = [c for c in data["coarse_5m"] if c["close_time_ms"] == breakout + 300_000]
    sidecar = make_sidecar(tmp_path, candles=[c for c in data["coarse_5m"] if c not in missing])
    sidecar.cycle()
    assert sidecar.cycle() == []                          # still missing: no repeated gap record
    sidecar.candles.candles = sorted(sidecar.candles.candles + missing, key=lambda c: c["open_time_ms"])
    resumed = upper(sidecar.cycle())
    assert [r.event for r in resumed] == [EVENT_RETEST_PROVEN]


def test_unavailable_r0_waits_and_unreadable_database_observes_nothing(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("gate read failed")

    monkeypatch.setattr(sidecar_module, "read_account_facts", broken)
    records = upper(make_sidecar(tmp_path).cycle())
    assert records[0].decision == "WAIT"
    assert "r0_wait:daily_gate_unavailable" in records[0].reasons

    def no_reader(path):
        raise OSError("database locked")

    failing = make_sidecar(tmp_path / "other", reader_factory=no_reader)
    assert failing.cycle() == [] and failing.metrics.read_failures == 1


def test_real_store_without_paper_account_yields_wait_not_a_permission(tmp_path):
    record = upper(make_sidecar(tmp_path).cycle())[0]

    assert record.r0_decision == "WAIT" and record.r0_usdt is None


def test_daily_headroom_is_only_an_upper_bound_never_an_allow(tmp_path, monkeypatch):
    gate = {"enabled": True, "data_available": True, "latched": False, "block_pct": "-10",
            "baseline_equity_usdt": "5000", "current_adjusted_equity_usdt": "5000"}
    monkeypatch.setattr(sidecar_module, "read_account_facts", lambda *a, **k: AccountFacts(gate, []))
    records = make_sidecar(tmp_path).cycle()

    assert records and all(r.decision in {"WAIT", "BLOCK"} for r in records)
    assert all(r.research_policy != "ALLOW" for r in records)


def test_overloaded_observation_queue_drops_and_counts_without_blocking(tmp_path):
    release, busy_writer = threading.Event(), threading.Event()
    writer = _BestEffortDiagnosticsWriter(limit=1)
    writer.submit(lambda: (busy_writer.set(), release.wait()))   # occupies the writer thread
    assert busy_writer.wait(5)
    writer.submit(lambda: None)                                    # fills the single queue slot
    sidecar = make_sidecar(tmp_path, writer=writer)
    try:
        records = sidecar.cycle()
    finally:
        release.set()

    assert records
    assert sidecar.metrics.observations_dropped == len(records)
    assert sidecar.metrics.observations_submitted == 0


@pytest.mark.parametrize("busy", [lambda: True, lambda: None, lambda: (_ for _ in ()).throw(RuntimeError())])
def test_stop_take_protection_work_preempts_the_whole_cycle(tmp_path, busy):
    opened = []

    def reader(path):
        opened.append(path)
        return SQLiteStore.open_reader(path)

    sidecar = make_sidecar(tmp_path, busy=busy, reader_factory=reader)

    assert sidecar.cycle() == []
    assert opened == [] and sidecar.metrics.skipped_for_protection == 1


def test_sidecar_has_no_trading_or_owner_path():
    source = Path(sidecar_module.__file__).read_text(encoding="utf-8")

    for forbidden in ("runtime.call", "admit_", "submit_initial_protection", "_robot_cancel_limit",
                      "place_", "paper_limit(", "SQLiteStore.open(", "open_writer"):
        assert forbidden not in source
