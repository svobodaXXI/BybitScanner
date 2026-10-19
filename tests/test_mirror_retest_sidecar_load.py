"""MIRROR-INTEGRATION-6: the sidecar pays for database reads only when something can have changed."""

import json

import mirror_retest_sidecar as sidecar_module
from geometry.naked_retest import EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN
from mirror_retest_observer import ObservationJournal
from mirror_retest_sidecar import MirrorSidecar
from terminal.domain.models import Symbol
from terminal.persistence.sqlite_store import RobotAutoDecisionRecord, SQLiteStore
from tests.test_mirror_retest_sidecar import ACCOUNT, ListSource, SyncWriter, make_sidecar, real_case, upper, write_envelope


class Spy:
    def __init__(self, monkeypatch):
        self.arrivals, self.account = 0, 0
        real_arrivals, real_account = sidecar_module.read_new_wedge_arrivals, sidecar_module.read_account_facts

        def arrivals(*args, **kwargs):
            self.arrivals += 1
            return real_arrivals(*args, **kwargs)

        def account(*args, **kwargs):
            self.account += 1
            return real_account(*args, **kwargs)

        monkeypatch.setattr(sidecar_module, "read_new_wedge_arrivals", arrivals)
        monkeypatch.setattr(sidecar_module, "read_account_facts", account)


def split_at_breakout(data):
    breakout = data["manifest"]["breakout_close_time_ms"]
    before = [c for c in data["coarse_5m"] if c["close_time_ms"] < breakout]
    rest = [c for c in data["coarse_5m"] if c["close_time_ms"] >= breakout]
    return before, rest


def add_arrival(db, ref, index, at_ms):
    with SQLiteStore.open(db) as store:
        store.append_robot_auto_decision(RobotAutoDecisionRecord(
            decision_id=f"d{index}", trading_account_id=ACCOUNT, candidate_ref=ref, pattern="Falling Wedge",
            symbol=Symbol("1000LUNCUSDT"), timeframe="5", source_identity=f"{ref}:sha{index}",
            snapshot_sha256=None, mode="SHADOW", policy_version="v1", outcome="WAIT",
            reason_code="CANDIDATE_FRESHNESS_UNKNOWN", evaluated_at_ms=at_ms, resulting_candidate_id=None))


def test_empty_cycles_read_neither_arrivals_nor_account_facts(tmp_path, monkeypatch):
    spy = Spy(monkeypatch)
    before, _ = split_at_breakout(real_case())
    sidecar = make_sidecar(tmp_path, candles=before)

    assert upper(sidecar.cycle()) == []                  # first cycle: arrivals read once, no event
    for _ in range(5):
        assert sidecar.cycle() == []
    assert spy.arrivals == 1 and spy.account == 0
    assert sidecar.metrics.arrival_reads == 1 and sidecar.metrics.arrival_reads_skipped == 5


def test_account_facts_are_read_only_for_the_decision_that_needs_them_and_never_reused(tmp_path, monkeypatch):
    spy = Spy(monkeypatch)
    data = real_case()
    before, rest = split_at_breakout(data)
    sidecar = make_sidecar(tmp_path, candles=before)
    sidecar.cycle()

    sidecar.candles.candles = before + rest[:1]          # the breakout candle closes
    records = upper(sidecar.cycle())
    assert [r.event for r in records] == [EVENT_NAKED_BREAKOUT] and spy.account == 1

    sidecar.candles.candles = data["coarse_5m"]          # the retest: campaign ends, no R0 needed
    records = upper(sidecar.cycle())
    assert [r.event for r in records] == [EVENT_RETEST_PROVEN] and spy.account == 1
    assert sidecar.metrics.account_reads == 1


def test_lazy_facts_are_fresh_per_cycle(tmp_path, monkeypatch):
    spy = Spy(monkeypatch)
    data = real_case()
    sidecar = make_sidecar(tmp_path, arrivals=[("ref1", 10, "Rising Wedge"), ("ref2", 11, "Rising Wedge")])
    write_envelope(tmp_path / "candidates", "ref2", data["manifest"], formation="f2", symbol="OTHERUSDT")
    before, rest = split_at_breakout(data)
    sidecar.candles.candles = before + rest[:1]
    sidecar.cycle()                                       # both candidates break out in one cycle: one read
    assert spy.account == 1

    sidecar.candles = ListSource(before + rest[:1])
    add_arrival(tmp_path / "paper.sqlite3", "ref3", 7, 12)
    write_envelope(tmp_path / "candidates", "ref3", data["manifest"], formation="f3", symbol="THIRDUSDT")
    sidecar.cycle()                                       # a later breakout reads the account again
    assert spy.account == 2


def test_a_new_arrival_is_picked_up_on_the_next_cycle(tmp_path, monkeypatch):
    spy = Spy(monkeypatch)
    data = real_case()
    sidecar = make_sidecar(tmp_path)
    sidecar.cycle()
    sidecar.cycle()
    assert spy.arrivals == 1

    write_envelope(tmp_path / "candidates", "ref2", data["manifest"], formation="f2", symbol="OTHERUSDT")
    add_arrival(tmp_path / "paper.sqlite3", "ref2", 5, 50)
    records = upper(sidecar.cycle())

    assert spy.arrivals == 2 and "ref2" in sidecar.tracked
    assert [r.event for r in records if r.boundary_id.startswith("ref2")] == [EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN]


def test_read_errors_change_nothing_and_the_next_cycle_recovers(tmp_path):
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("database busy")
        return SQLiteStore.open_reader(path)

    sidecar = make_sidecar(tmp_path, reader_factory=flaky)
    assert sidecar.cycle() == []
    assert sidecar.metrics.read_failures == 1 and sidecar.audit_rows_seen is None and not sidecar.tracked

    assert [r.event for r in upper(sidecar.cycle())] == [EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN]


def test_a_failed_account_read_waits_and_is_counted(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("gate read failed")

    monkeypatch.setattr(sidecar_module, "read_account_facts", broken)
    sidecar = make_sidecar(tmp_path)
    records = upper(sidecar.cycle())

    assert records[0].decision == "WAIT" and any(r.startswith("r0_wait") for r in records[0].reasons)
    assert sidecar.metrics.account_read_failures == 1


def test_restart_reads_arrivals_again_and_duplicates_nothing(tmp_path):
    first = make_sidecar(tmp_path)
    produced = upper(first.cycle())
    journal = tmp_path / "observations.jsonl"
    lines = journal.read_text(encoding="utf-8").splitlines()

    second = MirrorSidecar(
        database_path=tmp_path / "paper.sqlite3", account=ACCOUNT, candidate_store_dir=tmp_path / "candidates",
        candles=ListSource(real_case()["coarse_5m"]), journal=ObservationJournal(journal),
        protection_busy=lambda: False, clock_ms=first.clock_ms, writer=SyncWriter())
    again = upper(second.cycle())

    assert second.metrics.arrival_reads == 1 and [r.observation_id for r in again] == [r.observation_id for r in produced]
    assert journal.read_text(encoding="utf-8").splitlines() == lines
    assert all(not json.loads(line)["executable"] for line in lines)
