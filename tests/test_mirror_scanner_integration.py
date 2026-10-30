"""#613 Scanner integration of the universal MIRROR detector (mirror_scanner + main hook).

Synthetic contracts for the lifecycle, dedup, FVG neutrality, restart and the
Telegram/Terminal surfaces, plus real public Bybit candles already frozen in
tests/fixtures (HORN KNCUSDT 5m, geometry gold Triangle / Box cases, CAKEUSDT
L-shape window) run through the Scanner's own engines.
"""
from pathlib import Path
import json
import subprocess
import sys
import threading
import types
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import pandas as pd
import pytest

import mirror_scanner as ms
from mirror_levels.levels import SOURCE_SWING_ZONE, horizontal_level, line_level
from mirror_levels.tracker import STATUS_RETESTED, STATUS_UNTESTED, STATUS_WAITING

M = 60_000
FIXTURES = Path(__file__).parent / "fixtures"

# config.py is machine-local and ignored; Scanner modules get only this import-time surface.
CONFIG = types.SimpleNamespace(
    TELEGRAM_TOKEN="test-token", TELEGRAM_CHAT_ID="42", TELEGRAM_CHAT_IDS=("42",),
    TELEGRAM_ENABLED=True, TELEGRAM_TEST_MODE=False, TIMEFRAME="1", CANDLE_LIMIT=200,
    MODE="hunter", MIN_SCORE=30, MAX_SYMBOLS=None, BYBIT_CATEGORY="linear",
)


@pytest.fixture
def config_stub(monkeypatch):
    if "config" not in sys.modules or not hasattr(sys.modules["config"], "TIMEFRAME"):
        monkeypatch.setitem(sys.modules, "config", CONFIG)
    return sys.modules["config"]


def frame(bars, step=M):
    """Scanner frame from (o, h, l, c) tuples plus one trailing open candle."""
    rows = [{"time": i * step, "open": o, "high": h, "low": l, "close": c}
            for i, (o, h, l, c) in enumerate(bars)]
    last = rows[-1]["close"]
    rows.append({"time": len(bars) * step, "open": last, "high": last, "low": last, "close": last})
    return pd.DataFrame(rows)


def flat_bars(n, price=100.0, spread=0.5):
    return [(price, price + spread, price - spread, price)] * n


def level_at(price, confirmed_ms, *, side="upper", source=SOURCE_SWING_ZONE, pattern=None, symbol="TESTUSDT"):
    return horizontal_level(symbol=symbol, timeframe="1", source=source, pattern=pattern, side=side,
                            price=price, anchor_time_ms=0, confirmed_at_ms=confirmed_ms)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv(ms.ROOT_ENV, str(tmp_path))
    return tmp_path


@pytest.fixture
def fixed_levels(monkeypatch):
    """Replace the snapshot detectors by a fixed list; everything after them is the real path."""
    holder = {"levels": [], "original": ms.collect_levels}
    monkeypatch.setattr(ms, "collect_levels", lambda *a, **k: list(holder["levels"]))
    return holder


def observe(df, root, **kwargs):
    return ms.observe_mirror_levels("TESTUSDT", df, timeframe="1", root=root,
                                    now_ms=int(df["time"].iloc[-1]), **kwargs)


def breakout_bars(n_before=30, level=101.0, body=3.0):
    """Quiet range under ``level``, then one large full-body candle through it."""
    bars = flat_bars(n_before)
    bars.append((100.0, 100.0 + body + 0.2, 99.9, 100.0 + body))     # opens below, closes far above
    return bars


# --- lifecycle --------------------------------------------------------------------------------------

def test_level_without_parent_fresh_breakout_becomes_candidate_and_first_retest_is_terminal(root, fixed_levels):
    level = level_at(101.0, 5 * M)
    fixed_levels["levels"] = [level]
    bars = breakout_bars()
    summary = observe(frame(bars), root)
    assert summary["new_candidates"] == 1
    assert [item["kind"] for item in summary["pending"]] == ["breakout"]
    record = ms.load_state("TESTUSDT", "1", root)["records"][level.level_id]
    assert record["status"] == STATUS_UNTESTED and record["candidate"] is True
    assert record["freshness"] == "FRESH" and record["rejection"] is None
    assert record["sources"][0]["parent_pattern"] is None                  # no parent pattern

    # First retest: price returns to the level.
    bars += [(103.0, 103.2, 102.0, 102.5), (102.5, 102.6, 100.9, 101.5)]
    summary = observe(frame(bars), root)
    record = ms.load_state("TESTUSDT", "1", root)["records"][level.level_id]
    assert record["status"] == STATUS_RETESTED and record["lifecycle"] == ms.LIFECYCLE_DONE
    assert record["naked_retest"]["retest"]["open_time_ms"] == (len(bars) - 1) * M
    assert [p["kind"] for p in summary["pending"]] == ["breakout"]  # terminal retest is durable, not a card

    # Repeated retests never re-arm the level or produce new events.
    bars += [(101.5, 102.0, 100.5, 101.0), (101.0, 104.0, 100.8, 103.5), (103.5, 103.6, 100.7, 101.2)]
    summary = observe(frame(bars), root)
    assert summary["events"] == [] and summary["new_candidates"] == 0
    record = ms.load_state("TESTUSDT", "1", root)["records"][level.level_id]
    assert record["status"] == STATUS_RETESTED
    assert record["naked_retest"]["retest"]["open_time_ms"] == (len(bars) - 4) * M


def test_stale_and_weak_breakouts_are_tracked_with_a_rejection_reason_never_as_candidates(root, fixed_levels):
    stale = level_at(101.0, 5 * M)
    fixed_levels["levels"] = [stale]
    bars = breakout_bars() + [(103.0, 103.5, 102.8, 103.2)] * 5         # Scanner saw it 5 candles late
    observe(frame(bars), root)
    record = ms.load_state("TESTUSDT", "1", root)["records"][stale.level_id]
    assert record["status"] == STATUS_UNTESTED and record["candidate"] is False
    assert record["freshness"] == "STALE" and record["rejection"].startswith("stale_breakout:5")

    weak = level_at(100.05, 5 * M, symbol="TESTUSDT")
    fixed_levels["levels"] = [weak]
    ms.state_path("TESTUSDT", "1", root).unlink()
    observe(frame(flat_bars(30) + [(99.99, 100.2, 99.9, 100.1)]), root)  # full body, tiny vs ATR 1.0
    record = ms.load_state("TESTUSDT", "1", root)["records"][weak.level_id]
    assert record["candidate"] is False and record["rejection"].startswith("weak_breakout_body")
    assert ms.load_state("TESTUSDT", "1", root)["pending_notifications"] == []


def test_waiting_level_expires_and_history_gap_rejects(root, fixed_levels):
    level = level_at(150.0, 5 * M)
    fixed_levels["levels"] = [level]
    observe(frame(flat_bars(ms.WAITING_EXPIRY_CANDLES + 10)), root)
    record = ms.load_state("TESTUSDT", "1", root)["records"][level.level_id]
    assert record["lifecycle"] == ms.LIFECYCLE_REJECTED and record["rejection"] == "expired_before_breakout"

    gapped = level_at(160.0, 5 * M)
    fixed_levels["levels"] = [gapped]
    observe(frame(flat_bars(20)), root)
    later = frame(flat_bars(60)).iloc[40:].reset_index(drop=True)         # 20 candles missing
    observe(later, root)
    record = ms.load_state("TESTUSDT", "1", root)["records"][gapped.level_id]
    assert record["lifecycle"] == ms.LIFECYCLE_REJECTED and record["rejection"] == "history_gap"


# --- dedup ------------------------------------------------------------------------------------------

def test_one_real_level_from_several_sources_and_repeated_scans_is_one_candidate(root, fixed_levels):
    swing = level_at(101.0, 5 * M)
    box_top = level_at(101.1, 8 * M, source="pattern_boundary", pattern="IKIGAI_BOX")
    l_shape = level_at(100.95, 9 * M, source="pattern_boundary", pattern="L-shape")
    fixed_levels["levels"] = [box_top, swing, l_shape]
    bars = flat_bars(30)
    observe(frame(bars), root)
    observe(frame(bars), root)                                             # same snapshot again
    bars = breakout_bars()
    summary = observe(frame(bars), root)
    state = ms.load_state("TESTUSDT", "1", root)
    assert list(state["records"]) == [swing.level_id]                      # first registered wins
    assert {s["level_id"] for s in state["records"][swing.level_id]["sources"]} == {
        swing.level_id, box_top.level_id, l_shape.level_id}
    assert summary["new_candidates"] == 1 and len(summary["pending"]) == 1

    # A Scanner re-fit of one sloped boundary (new second anchor, same line) is the same level.
    first = line_level(symbol="TESTUSDT", timeframe="1", pattern="Falling Wedge", side="upper",
                       first=(0, 110.0), second=(10 * M, 108.0), confirmed_at_ms=12 * M)
    refit = line_level(symbol="TESTUSDT", timeframe="1", pattern="Triangle Compression", side="upper",
                       first=(0, 110.0), second=(14 * M, 107.2), confirmed_at_ms=16 * M)
    other = line_level(symbol="TESTUSDT", timeframe="1", pattern="Falling Wedge", side="upper",
                       first=(0, 110.0), second=(14 * M, 105.0), confirmed_at_ms=16 * M)
    fixed_levels["levels"] = [first, refit, other]
    observe(frame(breakout_bars() + [(103.0, 103.5, 102.8, 103.2)]), root)
    records = ms.load_state("TESTUSDT", "1", root)["records"]
    assert first.level_id in records and refit.level_id not in records and other.level_id in records


# --- FVG / Robot neutrality -------------------------------------------------------------------------

def test_fvg_is_a_quality_attribute_that_never_creates_or_admits_a_candidate(root, fixed_levels):
    level = level_at(101.0, 5 * M)
    fixed_levels["levels"] = [level]
    # Same breakout, once inside a bullish FVG (candle 3 low above candle 1 high) and once without.
    with_gap = flat_bars(30) + [(100.0, 100.4, 99.9, 100.3), (100.3, 103.4, 100.2, 103.2),
                                (103.2, 103.6, 101.5, 103.4)]
    observe(frame(with_gap), root)
    gapped = ms.load_state("TESTUSDT", "1", root)["records"][level.level_id]
    assert gapped["imbalance"] and gapped["imbalance"][0]["direction"] == "BULLISH"
    robot = gapped["robot"]
    assert robot["executable"] is False and robot["admission_allowed"] is False
    assert robot["mode"] == "OBSERVE_ONLY" and robot["risk_reason"] == "robot_execution_not_authorized"
    assert robot["robot_handoff_executable"] is False and robot["paper_admission"] == "NOT_AUTHORIZED"

    ms.state_path("TESTUSDT", "1", root).unlink()
    observe(frame(breakout_bars()), root)                                 # no third candle: no gap
    plain =ms.load_state("TESTUSDT", "1", root)["records"][level.level_id]
    assert plain["imbalance"] == [] and plain["candidate"] is gapped["candidate"] is True

    # A gap next to a weak breakout does not rescue it.
    weak = level_at(100.05, 5 * M)
    fixed_levels["levels"] = [weak]
    ms.state_path("TESTUSDT", "1", root).unlink()
    observe(frame(flat_bars(30) + [(99.6, 99.7, 99.55, 99.65), (99.99, 100.2, 99.9, 100.1),
                                   (100.1, 100.3, 99.8, 100.2)]), root)
    assert ms.load_state("TESTUSDT", "1", root)["records"][weak.level_id]["candidate"] is False


def test_detection_never_touches_the_robot_candidate_store_or_paper(root, fixed_levels, monkeypatch):
    import robot_candidate_store

    def forbidden(*args, **kwargs):
        raise AssertionError("MIRROR detection must not persist a Robot candidate")

    monkeypatch.setattr(robot_candidate_store, "create_signal_snapshot", forbidden)
    fixed_levels["levels"] = [level_at(101.0, 5 * M)]
    assert observe(frame(breakout_bars()), root)["new_candidates"] == 1
    # The detector module itself needs no PAPER runtime or candidate store at all.
    code =("import sys, mirror_scanner; "
            "assert not any(m.startswith('terminal.runtime') or m == 'robot_candidate_store' "
            "for m in sys.modules), sorted(m for m in sys.modules if 'terminal' in m)")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).parents[1])


# --- restart / durability ---------------------------------------------------------------------------

def test_resume_from_durable_state_equals_one_replay(root, fixed_levels, tmp_path):
    fixed_levels["levels"] = [level_at(101.0, 5 * M), level_at(99.0, 5 * M, side="lower")]
    bars = breakout_bars() + [(103.0, 103.2, 102.0, 102.5), (102.5, 102.6, 100.9, 101.5)]
    other = tmp_path / "one_shot"
    ms.observe_mirror_levels("TESTUSDT", frame(bars), timeframe="1", root=other, now_ms=0)
    for end in range(25, len(bars) + 1):                                   # one process start per candle
        observe(frame(bars[:end]), root)
    resumed = ms.load_state("TESTUSDT", "1", root)
    one_shot = ms.load_state("TESTUSDT", "1", other)
    for level_id, record in one_shot["records"].items():
        keep = ("status", "naked_retest", "breakout_evidence", "imbalance")
        assert {k: resumed["records"][level_id][k] for k in keep} == {k: record[k] for k in keep}


def test_unreadable_state_is_never_overwritten_and_skips_the_symbol(root, fixed_levels):
    fixed_levels["levels"] = [level_at(101.0, 5 * M)]
    path = ms.state_path("TESTUSDT", "1", root)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert observe(frame(breakout_bars()), root) is None
    assert path.read_text(encoding="utf-8") == "{not json"
    events = [json.loads(line) for line in (root / ms.EVENTS_FILE).read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event"] == "mirror_state_unreadable"


# --- Telegram / Terminal surfaces ---------------------------------------------------------------------

@pytest.fixture
def telegram(monkeypatch, config_stub):
    sent = []
    monkeypatch.setattr(config_stub, "TELEGRAM_ENABLED", True, raising=False)
    import notification
    import mirror_event_chart
    import telegram_bot

    outcome = {"ok": True}
    monkeypatch.setattr(notification, "build_tradingview_keyboard", lambda *a, **k: {"inline_keyboard": []})
    monkeypatch.setattr(notification, "get_telegram_chat_ids", lambda: ("42",))
    monkeypatch.setattr(notification, "get_telegram_owner_chat_id", lambda: "42")

    def fake_render(snapshot, output_path):
        Path(output_path).write_bytes(b"fake-png")
    monkeypatch.setattr(mirror_event_chart, "render_mirror_chart", fake_render)
    def fake_photo(*args, **kwargs):
        sent.append(kwargs["caption"])
        return {"ok": outcome["ok"]}
    monkeypatch.setattr(telegram_bot, "send_photo", fake_photo)
    return sent, outcome


def test_pending_card_survives_a_failed_send_and_is_delivered_exactly_once(root, fixed_levels, telegram):
    sent, outcome = telegram
    level = line_level(symbol="TESTUSDT", timeframe="1", pattern="Rising Wedge", side="lower",
                       first=(0, 100.0), second=(10 * M, 100.5), confirmed_at_ms=12 * M,
                       provenance={"parent_pattern": "Rising Wedge", "parent_formation_id": "0:60000"})
    fixed_levels["levels"] = [level]
    bars = [(c + 0.5, c + 0.7, c + 0.3, c + 0.5) for c in (100 + 0.05 * i for i in range(30))]
    bars.append((101.9, 102.0, 97.5, 97.8))
    observe(frame(bars), root)

    outcome["ok"] = False
    assert ms.send_mirror_notifications("TESTUSDT", "1", root=root) == 0
    assert ms.load_state("TESTUSDT", "1", root)["pending_notifications"]
    outcome["ok"] = True
    assert ms.send_mirror_notifications("TESTUSDT", "1", root=root) == 1
    assert ms.send_mirror_notifications("TESTUSDT", "1", root=root) == 0
    assert len(sent) == 2
    assert sent[-1] == "🪞 MIRROR · TESTUSDT · 1m\\nГраница паттерна"
    state = ms.load_state("TESTUSDT", "1", root)
    assert state["pending_notifications"] == []
    assert state["records"][level.level_id]["notified"] == [{"kind": "breakout", "result": True}]


def test_mirror_caption_has_only_level_or_pattern_and_no_diagnostics():
    level = {"source": "swing_zone"}
    row = {"symbol": "TESTUSDT", "timeframe": "5", "level": level, "sources": []}
    assert ms.mirror_caption(row, "breakout") == "🪞 MIRROR · TESTUSDT · 5m\\nЗеркальный уровень"
    row["level"] = {"source": "pattern_boundary"}
    assert ms.mirror_caption(row, "breakout") == "🪞 MIRROR · TESTUSDT · 5m\\nГраница паттерна"
    assert ms.mirror_caption(row, "first_retest") == ms.mirror_caption(row, "breakout")


def test_terminal_route_projects_mirror_levels_read_only(root, fixed_levels):
    from terminal.runtime.paper_http_server import PaperHttpHandler

    fixed_levels["levels"] = [level_at(101.0, 5 * M), level_at(130.0, 5 * M)]
    observe(frame(breakout_bars()), root)
    before = ms.state_path("TESTUSDT", "1", root).read_bytes()
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urlopen(f"http://{host}:{port}/api/scanner/mirror-levels", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        with urlopen(f"http://{host}:{port}/api/scanner/mirror-levels?include_waiting=1", timeout=5) as response:
            everything = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert payload["ok"] is True and payload["paper_admission"] == "NOT_AUTHORIZED"
    assert payload["counts"] == {STATUS_UNTESTED: 1, STATUS_WAITING: 1}
    (row,) = payload["levels"]
    assert row["candidate"] is True and row["breakout"]["direction"] == "UP"
    assert row["level_geometry_text"] == "горизонталь 101" and row["parent_patterns"] == []
    assert row["first_retest_text"].startswith("ещё не было")
    assert len(everything["levels"]) == 2
    assert ms.state_path("TESTUSDT", "1", root).read_bytes() == before


def test_scan_finished_message_reports_mirror_candidates(config_stub):
    import main

    text = main.build_scan_finished_message(1, 2, 3, 0, 5, mirror_candidate_count=4)
    assert "MIRROR (наблюдение): новых кандидатов 4" in text
    assert "MIRROR" not in main.build_scan_finished_message(1, 2, 3, 0, 5)


def test_scanner_hook_feeds_5m_with_the_same_pass_1m_candles(monkeypatch, root, config_stub):
    import main

    calls = []
    monkeypatch.setattr(ms, "observe_mirror_levels",
                        lambda symbol, candles, **kw: calls.append((kw["timeframe"], kw["fine_candles"]))
                        or {"new_candidates": 1, "pending": []})
    monkeypatch.setattr(ms, "send_mirror_notifications", lambda *a, **k: 0)
    inputs = {tf: {"candles": frame(flat_bars(10), step=step), "wedge_result": None,
                   "horn_observation": None, "l_shape_observation": None}
              for tf, step in (("5", 5 * M), ("1", M))}
    assert main.observe_mirror_symbol("TESTUSDT", inputs) == (2, 0, 0)
    assert [tf for tf, _ in calls] == ["1", "5"]
    assert calls[0][1] is None and len(calls[1][1]) == 10 and calls[1][1][1]["close_time_ms"] == 2 * M


def test_ambiguous_5m_retest_of_a_sloped_level_is_settled_by_1m_candles(root, fixed_levels):
    step = 5 * M
    # Rising line; after an UP breakout a 5m candle whose low lies between the line's open/close values.
    level = line_level(symbol="TESTUSDT", timeframe="5", pattern="Rising Wedge", side="upper",
                       first=(0, 100.0), second=(10 * step, 101.0), confirmed_at_ms=12 * step)
    fixed_levels["levels"] = [level]
    bars = [(p - 1.0, p - 0.6, p - 1.4, p - 1.0) for p in (100 + 0.1 * i for i in range(30))]
    bars.append((102.6, 106.4, 102.5, 106.2))                              # i=30 line 103.0..103.1
    bars.append((106.0, 106.2, 103.15, 105.0))                             # line 103.1..103.2: ambiguous
    df = frame(bars, step=step)
    t = 31 * step
    fine = [{"open_time_ms": t + k * M, "close_time_ms": t + (k + 1) * M, "open": 105.0, "high": 105.2,
             "low": low, "close": 105.0, "closed": True}
            for k, low in enumerate((105.0, 104.0, 103.0, 104.5, 104.8))]  # 3rd minute dips through
    ms.observe_mirror_levels("TESTUSDT", df, timeframe="5", root=root, now_ms=0, fine_candles=fine)
    record = ms.load_state("TESTUSDT", "5", root)["records"][level.level_id]
    assert record["status"] == STATUS_RETESTED

    ms.state_path("TESTUSDT", "5", root).unlink()
    ms.observe_mirror_levels("TESTUSDT", df, timeframe="5", root=root, now_ms=0, fine_candles=None)
    record = ms.load_state("TESTUSDT", "5", root)["records"][level.level_id]
    assert record["status"] == "RETEST_UNPROVEN"                           # fail-closed without 1m proof


# --- pivots performance refactor ---------------------------------------------------------------------

def test_find_pivots_output_is_identical_to_the_previous_implementation():
    source = subprocess.check_output(["git", "show", "51d23a22:pivots.py"],
                                     cwd=Path(__file__).parents[1]).decode("utf-8")
    previous = types.ModuleType("previous_pivots")
    exec(source, previous.__dict__)
    import pivots

    frames = []
    for path in sorted((FIXTURES / "geometry_gold").glob("*_20261012.json"))[:3]:
        raw = json.loads(path.read_text())
        frames.append(pd.DataFrame(raw["candles"], columns=raw["columns"]))
    frames.append(pd.DataFrame(json.loads((FIXTURES / "l_shape_currency" / "CAKEUSDT_5m_window.json")
                                          .read_text())["candles"]))
    for df in frames:
        for min_change in (0.003, 0):
            old = previous.find_pivots(df.copy(), min_change=min_change)
            new = pivots.find_pivots(df.copy(), min_change=min_change)
            assert old == new
            assert [type(p["price"]) for p in old[0] + old[1]] == [type(p["price"]) for p in new[0] + new[1]]


# --- real candles ---------------------------------------------------------------------------------

def _real_frame(candles):
    return pd.DataFrame({"time": [c["open_time_ms"] for c in candles],
                         "open": [c["open"] for c in candles], "high": [c["high"] for c in candles],
                         "low": [c["low"] for c in candles], "close": [c["close"] for c in candles]})


def test_real_horn_kncusdt_5m_boundary_breakout_through_the_full_scanner_path(root):
    raw = json.loads((FIXTURES / "mirror_levels" / "horn_KNCUSDT_5_1792842000000.json").read_text())
    event, df = raw["event"], _real_frame(raw["candles"])
    decision = next(i for i, c in enumerate(raw["candles"]) if c["open_time_ms"] == event["decision_time_ms"])
    for end in range(decision + 2, len(df) + 1):                          # one Scanner pass per candle
        window = df.iloc[max(0, end - 200):end].reset_index(drop=True)
        ms.observe_mirror_levels("KNCUSDT", window, timeframe="5", root=root, box_source=False,
                                 horn_observation=event if end == decision + 2 else None,
                                 now_ms=int(window["time"].iloc[-1]))
    rows = {(r["level_label"], r["status"]): r for r in ms.project_mirror_levels(root, include_waiting=True)["levels"]}
    lower = rows[("Broadening lower", STATUS_UNTESTED)]
    assert lower["candidate"] is True and lower["breakout"]["direction"] == "DOWN"
    assert [list(a) for a in lower["level"]["anchors"]] == [
        [event["lower_line"]["anchor_time_ms"], event["lower_line"]["anchor_price"]],
        [event["lower_line"]["second_time_ms"], event["lower_line"]["second_price"]]]
    assert lower["parent_patterns"] == [{"pattern": "Broadening", "formation_id": event["identity"]}]
    assert lower["breakout_evidence"]["kind"] == "FULL_BODY" and lower["robot"]["executable"] is False
    assert any(r["parent_patterns"] == [] for r in rows.values())        # swing levels without a parent
    state = ms.load_state("KNCUSDT", "5", root)
    breakouts = [p["level_id"] for p in state["pending_notifications"] if p["kind"] == "breakout"]
    assert len(breakouts) == len(set(breakouts))                          # one card per level, not per pass
    # Swing zone 0.12429 and L-shape level 0.12424 broke on one candle: one MIRROR event.
    duplicates = [(k, r) for k, r in state["records"].items()
                  if (r.get("rejection") or "").startswith("duplicate_breakout_of:")]
    assert len(duplicates) == 1
    duplicate_id, duplicate = duplicates[0]
    primary = duplicate["rejection"].split(":", 1)[1]
    assert state["records"][primary]["candidate"] is True and primary in breakouts
    assert duplicate_id not in breakouts
    registered = [json.loads(line) for line in (root / ms.EVENTS_FILE).read_text(encoding="utf-8").splitlines()
                  if '"mirror_level_registered"' in line]
    assert len(registered) == len({e["level_id"] for e in registered}) == len(state["records"])


def test_real_drift_wedge_5m_boundaries_breakout_and_first_retest(root, fixed_levels, monkeypatch):
    raw = json.loads((FIXTURES / "mirror_levels" / "wedge_DRIFTUSDT_d954e71a03.json").read_text())
    snapshot, step = raw["signal_snapshot"], 5 * M
    # The Scanner frame index base follows from the formation id (anchor timestamps of indices 87 / 65).
    upper_ms, lower_ms = (int(x) for x in snapshot["scanner_formation_id"].split(":"))
    base = upper_ms - snapshot["geometry"]["upper_line"]["anchor_index"] * step
    assert base + snapshot["geometry"]["lower_line"]["anchor_index"] * step == lower_ms
    scanner_frame = pd.DataFrame({"time": [base + i * step for i in range(201)],
                                  "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})
    assert scanner_frame["time"][199] == snapshot["scanner_source_candle_time_ms"]
    monkeypatch.setattr(ms, "swing_levels", lambda *a, **k: ())
    wedge_levels = [lv for lv in fixed_levels["original"]("DRIFTUSDT", "5", scanner_frame,
                                                          wedge_result=snapshot, box_source=False)
                    if lv.pattern == "Falling Wedge"]
    assert {lv.side for lv in wedge_levels} == {"upper", "lower"}
    upper = next(lv for lv in wedge_levels if lv.side == "upper")
    assert upper.anchors == ((upper_ms, 0.0145), (base + 128 * step, 0.01434))
    assert upper.provenance["parent_formation_id"] == snapshot["scanner_formation_id"]

    one_minute = pd.DataFrame(raw["candles"])
    one_minute["bucket"] = one_minute["open_time_ms"] // step * step
    five = one_minute.groupby("bucket").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                            close=("close", "last"), n=("open", "size")).reset_index()
    five = five[five["n"] == 5].rename(columns={"bucket": "time"})[["time", "open", "high", "low", "close"]]
    fixed_levels["levels"] = wedge_levels
    for end in range(30, len(five) + 1, 4):
        window = five.iloc[:end].reset_index(drop=True)
        ms.observe_mirror_levels("DRIFTUSDT", window, timeframe="5", root=root, now_ms=0)
    records = ms.load_state("DRIFTUSDT", "5", root)["records"]
    upper_record = records[upper.level_id]
    assert upper_record["status"] == STATUS_RETESTED
    assert upper_record["naked_retest"]["breakout"]["direction"] == "UP"
    assert upper_record["naked_retest"]["breakout"]["open_time_ms"] == 1792844400000
    assert upper_record["naked_retest"]["retest"]["open_time_ms"] == 1792844700000
    lower_record = next(r for k, r in records.items() if k != upper.level_id)
    assert lower_record["status"] == STATUS_UNTESTED


def _gold_frame(name):
    raw = json.loads((FIXTURES / "geometry_gold" / name).read_text())
    df = (pd.DataFrame(raw["candles"], columns=raw["columns"]) if isinstance(raw["candles"][0], list)
          else pd.DataFrame(raw["candles"]))
    for key in ("open", "high", "low", "close"):
        df[key] = df[key].astype(float)
    df["time"] = df["time"].astype("int64")
    return df[["time", "open", "high", "low", "close"]]


def _scanner_wedge(window):
    from pivots import find_pivots
    from wedge import analyze_wedge

    highs, lows = find_pivots(window.copy())
    return analyze_wedge(highs, lows, current_index=len(window) - 1, candles=window)


@pytest.mark.parametrize("name,end", [("RSRUSDT_5m_triangle_owner_reference_20261012.json", 200),
                                      ("MEGAUSDT_5m_triangle_local_positive_20261012.json", 200)])
def test_real_triangle_boundaries_become_sloped_levels_with_both_anchors(root, name, end, config_stub):
    df = _gold_frame(name)
    window = df.iloc[max(0, end - 200):end].reset_index(drop=True)
    wedge = _scanner_wedge(window)
    assert wedge["pattern"] == "Triangle Compression"
    levels = [lv for lv in ms.collect_levels("XUSDT", "5", window, wedge_result=wedge, box_source=False)
              if lv.pattern == "Triangle Compression"]
    assert {lv.side for lv in levels} == {"upper", "lower"}
    times = list(window["time"])
    for lv in levels:
        line = wedge["geometry"][f"{lv.side}_line"]
        assert [t for t, _ in lv.anchors] == [times[line["anchor_index"]], times[line["second_index"]]]
        assert lv.confirmed_at_ms == times[-2] + 5 * M                     # known at the latest closed close
        assert lv.provenance["parent_pattern"] == "Triangle Compression"
    summary = ms.observe_mirror_levels("XUSDT", window, timeframe="5", wedge_result=wedge,
                                       box_source=False, root=root, now_ms=0)
    # Re-fits of the same triangle on the next candles reconcile into the registered lines.
    for later in range(end + 1, len(df) + 1):
        w = df.iloc[max(0, later - 200):later].reset_index(drop=True)
        ms.observe_mirror_levels("XUSDT", w, timeframe="5", wedge_result=_scanner_wedge(w),
                                 box_source=False, root=root, now_ms=0)
    state = ms.load_state("XUSDT", "5", root)
    triangle = [r for r in state["records"].values()
                if any(s["parent_pattern"] == "Triangle Compression" for s in r["sources"])]
    assert len(triangle) == 2 and summary["levels"] >= 2


def test_real_box_cpusdt_and_l_shape_levels_come_from_the_scanner_engines(root):
    box_window = _gold_frame("CPUSDT_5m_historical_first_impulse_20260923.json").iloc[:183]
    box_levels = [lv for lv in ms.collect_levels("CPUSDT", "5", box_window.reset_index(drop=True),
                                                 box_source=True) if lv.pattern == "IKIGAI_BOX"]
    assert {lv.side for lv in box_levels} == {"upper", "lower"} and all(lv.is_horizontal for lv in box_levels)
    assert not [lv for lv in ms.collect_levels("CPUSDT", "5", box_window.reset_index(drop=True),
                                               box_source=False) if lv.pattern == "IKIGAI_BOX"]

    l_window = _gold_frame("RPLUSDT_5m_historical_first_impulse_20260923.json").iloc[:183].reset_index(drop=True)
    (l_level,) = [lv for lv in ms.collect_levels("RPLUSDT", "5", l_window, box_source=False)
                  if lv.pattern == "L-shape"]
    breakout_open = int(l_window["time"].iloc[-2])
    assert l_level.confirmed_at_ms == breakout_open                        # known when the breakout candle opens
    ms.observe_mirror_levels("RPLUSDT", l_window, timeframe="5", box_source=False, root=root, now_ms=0)
    record = ms.load_state("RPLUSDT", "5", root)["records"]
    l_record = next(r for r in record.values() if any(s["parent_pattern"] == "L-shape" for s in r["sources"]))
    assert l_record["status"] == STATUS_UNTESTED                          # the L-shape breakout candle itself
    assert l_record["naked_retest"]["breakout"]["open_time_ms"] == breakout_open
