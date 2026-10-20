"""Focused tests for the OBSERVE_ONLY observation projection (MIRROR, pure, read-only)."""

import json
import shutil
from pathlib import Path

import pytest

import mirror_retest_projection as projection
from mirror_retest_projection import MAX_LIMIT, ProjectionUnavailable, ProjectionViolation, project_observations
from tests.test_mirror_retest_sidecar import make_sidecar, real_case, upper

SAVED = Path(__file__).parent / "fixtures" / "mirror_integration_5" / "journal_B.jsonl"   # 60 real INTEGRATION-5 records
NOW = 1_792_500_000_000


def record(n, **over):
    base = {
        "observation_id": f"o{n:03d}", "strategy_id": "MIRROR_RETEST", "boundary_id": f"ref{n}:upper", "symbol": "XUSDT",
        "candle_close_time_ms": 1_792_400_000_000 + n * 300_000, "event": "NAKED_BREAKOUT", "phase": "RETEST_CAMPAIGN_ACTIVE",
        "campaign_direction": "LONG", "decision": "WAIT", "reasons": ["observe_only"], "r0_decision": "WAIT", "r0_usdt": None,
        "research_policy": "WAIT", "exit_intent": None, "executable": False, "admission_allowed": False,
        "mode": "OBSERVE_ONLY", "facts": {"r0": {"decision": "WAIT", "r0_usdt": 12.5}},
    }
    return {**base, **over}


def write(path, records, *, tail=b""):
    path.write_bytes(b"".join((json.dumps(r, sort_keys=True) + "\n").encode() for r in records) + tail)
    return path


def project(path, **kwargs):
    return project_observations(path, now_ms=NOW, **kwargs)


# --- the 60 saved INTEGRATION-5 observations ------------------------------------------------------

def test_saved_journal_projects_all_60_in_order_without_internal_facts():
    result = project(SAVED, limit=MAX_LIMIT)

    rows = result["observations"]
    assert [r["seq"] for r in rows] == list(range(1, 61)) and result["total_lines"] == 60
    assert sum(r["event"] == "NAKED_BREAKOUT" for r in rows) == 31 and sum(r["event"] == "RETEST_PROVEN" for r in rows) == 29
    assert {r["decision"] for r in rows} <= {"WAIT", "BLOCK"}
    assert all(r["mode"] == "OBSERVE_ONLY" and r["executable"] is False and r["admission_allowed"] is False for r in rows)
    assert result["malformed_lines"] == result["duplicate_lines"] == 0 and not result["truncated"] and not result["cursor_reset"]
    dumped = json.dumps(result)
    assert '"facts"' not in dumped and "r0_usdt" not in dumped and "r0_decision" not in dumped
    assert len(dumped.encode()) < 110_000                       # bounded: 60 records ≈ 31 KB


def test_legacy_records_get_derived_identity_and_honest_unknowns():
    first = project(SAVED, limit=1)["observations"][0]

    assert first["candidate_ref"] == first["boundary_id"].rsplit(":", 1)[0]
    assert first["boundary_side"] in ("upper", "lower")
    assert first["pattern"] is None and first["timeframe"] is None and first["recorded_at_ms"] is None   # never guessed
    assert first["account_id"] is None


def test_cursor_pages_cover_the_journal_exactly_once():
    seen, after, pages = [], 0, 0
    while True:
        result = project(SAVED, after=after, limit=7)
        pages += 1
        seen.extend(r["seq"] for r in result["observations"])
        after = result["next_seq"]
        if not result["truncated"]:
            break
    assert seen == list(range(1, 61)) and pages == 9
    assert project(SAVED, after=60, limit=7)["observations"] == [] and project(SAVED, after=60)["next_seq"] == 60


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": MAX_LIMIT + 1}, {"limit": True}, {"after": -1}, {"after": "1"}])
def test_invalid_cursor_or_limit_is_rejected(kwargs):
    with pytest.raises(ValueError):
        project(SAVED, **kwargs)


# --- sequence, duplicates, damaged lines ------------------------------------------------------------

def test_duplicates_and_malformed_lines_are_skipped_and_counted_but_keep_their_seq(tmp_path):
    path = tmp_path / "j.jsonl"
    lines = [json.dumps(record(1), sort_keys=True), "not json {", json.dumps(record(1), sort_keys=True), "[1, 2]",
             json.dumps({"hello": "world"}), json.dumps(record(2, event="BOGUS")), json.dumps(record(3, reasons="x")),
             json.dumps(record(4, candle_close_time_ms=True)), json.dumps(record(5), sort_keys=True)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = project(path)

    assert [r["seq"] for r in result["observations"]] == [1, 9]            # seq is the line number, gaps are visible
    assert result["total_lines"] == 9 and result["duplicate_lines"] == 1 and result["malformed_lines"] == 6


def test_a_half_written_last_line_is_an_append_in_flight_not_an_error(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(1), record(2)], tail=b'{"observation_id": "o003", "strat')

    result = project(path)

    assert [r["seq"] for r in result["observations"]] == [1, 2] and result["partial_tail"] is True
    assert result["malformed_lines"] == 0 and result["total_lines"] == 2
    write(path, [record(1), record(2), record(3)])                             # the append completes
    assert [r["seq"] for r in project(path, after=2)["observations"]] == [3]


def test_foreign_account_lines_are_skipped_and_counted(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(1, account_id="paper"), record(2, account_id="live-x"), record(3)])

    result = project(path)

    assert [r["observation_id"] for r in result["observations"]] == ["o001", "o003"]
    assert result["foreign_account_lines"] == 1 and result["observations"][0]["account_id"] == "paper"


# --- truncation / replacement --------------------------------------------------------------------

def test_a_shorter_file_resets_the_cursor_and_restarts_at_seq_1(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(n) for n in range(1, 6)])
    cursor = project(path)["next_seq"]
    write(path, [record(1), record(2)])                                        # rotated / truncated

    result = project(path, after=cursor)

    assert result["cursor_reset"] is True and [r["seq"] for r in result["observations"]] == [1, 2] and result["next_seq"] == 2


def test_a_replaced_file_of_equal_or_greater_length_is_detected_by_journal_id(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(n) for n in range(1, 4)])
    first = project(path)
    assert project(path, after=first["next_seq"], journal_id=first["journal_id"])["cursor_reset"] is False

    write(path, [record(n, observation_id=f"new{n}") for n in range(10, 16)])   # different head, longer

    replaced = project(path, after=first["next_seq"], journal_id=first["journal_id"])
    assert replaced["cursor_reset"] is True and replaced["observations"][0]["seq"] == 1 and replaced["journal_id"] != first["journal_id"]


def test_missing_journal_is_an_explicit_empty_source_and_unreadable_is_unavailable(tmp_path):
    missing = project(tmp_path / "nope.jsonl", after=3)
    assert missing["ok"] and missing["journal_present"] is False and missing["observations"] == [] and missing["next_seq"] == 3

    folder = tmp_path / "dir.jsonl"
    folder.mkdir()
    with pytest.raises(ProjectionUnavailable):
        project(folder)


def test_a_journal_over_the_scan_limit_fails_closed(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(n) for n in range(1, 6)])
    with pytest.raises(ProjectionUnavailable):
        project(path, max_scan_bytes=200)


# --- trading permission ------------------------------------------------------------------------------

@pytest.mark.parametrize("override", [
    {"executable": True}, {"admission_allowed": True}, {"executable": None}, {"admission_allowed": "false"},
    {"mode": "PAPER_AUTO"}, {"mode": None}, {"decision": "ALLOW"}, {"decision": "allow"}, {"decision": None},
])
def test_any_trading_permission_or_foreign_mode_refuses_the_whole_projection(tmp_path, override):
    path = write(tmp_path / "j.jsonl", [record(1), record(2, **override), record(3)])

    with pytest.raises(ProjectionViolation):
        project(path)
    with pytest.raises(ProjectionViolation):
        project(path, after=2)                                  # also when the offending line is before the page


def test_a_violation_after_the_requested_page_is_still_detected(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(1), record(2), record(3, decision="ALLOW")])

    with pytest.raises(ProjectionViolation):
        project(path, limit=1)                                  # the page ends at line 1; line 3 is checked anyway


def test_internal_account_numbers_never_leave_the_projection(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(1, r0_usdt=987.65, facts={"r0": {"r0_usdt": 987.65}, "daily_loss_gate": {"equity": 4321}})])

    dumped = json.dumps(project(path))

    for secret in ("987.65", "4321", "facts", "daily_loss_gate", "r0_usdt"):
        assert secret not in dumped


# --- new records written by the sidecar ---------------------------------------------------------------

def test_sidecar_records_carry_identity_time_and_pattern_and_old_lines_still_project(tmp_path):
    sidecar = make_sidecar(tmp_path / "sc")
    produced = upper(sidecar.cycle())
    assert produced and all(r.candidate_ref == "ref1" and r.pattern == "Rising Wedge" and r.timeframe == "5"
                            and r.account_id == "paper" and r.recorded_at_ms == sidecar.clock_ms() for r in produced)

    journal = tmp_path / "sc" / "observations.jsonl"
    with journal.open("a", encoding="utf-8") as handle:                 # a legacy line after the new ones
        handle.write(json.dumps(record(9)) + "\n")
    result = project(journal)

    new = [r for r in result["observations"] if r["candidate_ref"] == "ref1"]
    assert new and all(r["pattern"] == "Rising Wedge" and r["timeframe"] == "5" and r["account_id"] == "paper"
                       and r["recorded_at_ms"] == produced[0].recorded_at_ms for r in new)
    assert result["observations"][-1]["pattern"] is None                # legacy line: unknown stays unknown
    assert len({r["observation_id"] for r in result["observations"]}) == len(result["observations"])


def test_the_new_fields_do_not_change_observation_ids_or_idempotency(tmp_path):
    first = make_sidecar(tmp_path / "a")
    ids = [r.observation_id for r in first.cycle()]
    second = make_sidecar(tmp_path / "b")
    assert [r.observation_id for r in second.cycle()] == ids
    first.journal.append(first.cycle())                                   # nothing new, journal unchanged
    assert len((tmp_path / "a" / "observations.jsonl").read_text(encoding="utf-8").splitlines()) == len(ids)


# --- read-only by construction ------------------------------------------------------------------------

def test_projection_never_modifies_the_journal(tmp_path):
    path = write(tmp_path / "j.jsonl", [record(n) for n in range(1, 4)], tail=b"partial")
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    project(path)
    project(path, after=2, limit=1)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_projection_module_is_read_only_and_terminal_free():
    source = Path(projection.__file__).read_text(encoding="utf-8")

    assert '.open("rb")' in source
    for forbidden in ("open(\"w", "open('w", ".write(", "write_text", "write_bytes", "unlink", "rename", "os.replace",
                      "import terminal", "from terminal", "sqlite", "requests", "runtime.call"):
        assert forbidden not in source
