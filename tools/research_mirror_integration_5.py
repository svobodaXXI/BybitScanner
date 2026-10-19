"""MIRROR-INTEGRATION-5: bounded read-only trial of the OBSERVE_ONLY path on real public candles.

Reuses the existing components unchanged: ``MirrorSidecar`` (candidate tracking, frozen boundaries, naked breakout /
retest state machine through ``geometry.naked_retest``), ``BybitClosedKlineSource`` (public closed candles) and
``ProtectionHealthGate``. Candidates and the account facts come from a READ-ONLY copy of the PAPER DB and a copy of the
candidate envelopes; nothing is written there. The only network traffic is ``GET /v5/market/kline`` (public) and, in phase
A, ``GET <backend>/api/robot/protection-health`` (expected to be unreachable: the backend is stopped).

Phases: A) real gate, backend down -> fail-closed, zero candle requests; B) idle gate injected (offline trial only: no
backend means no protection work exists) -> catch-up over real candles; C) same candidates again under an injected outage
and flapping -> must converge to B; D) restart on the same journal -> no duplicates. Then independent checks on the raw
recorded responses (continuity, freshness, look-ahead, strict body breakout, 1m physical contact for every proven retest).

Usage (repo root):  python -m tools.research_mirror_integration_5 --db DB --store DIR --out DIR
"""

from __future__ import annotations

import argparse
import json
import socket
import time
import tracemalloc
from pathlib import Path

from mirror_retest_live_sources import (
    KLINE_URL, BybitClosedKlineSource, ProtectionHealthGate, _default_session,
)
from mirror_retest_observer import ObservationJournal
from mirror_retest_sidecar import MirrorSidecar, read_new_wedge_arrivals
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore

FIVE, ONE = 300_000, 60_000
ACCOUNT = TradingAccountId("paper")


class Recorder:
    """Paced, whitelisted GET wrapper that records every raw kline response (and optional injected faults)."""

    def __init__(self, session, *, pause_s: float, fault=None):
        self.session, self.pause_s, self.fault = session, pause_s, fault
        self.calls = 0
        self.errors: dict[str, int] = {}
        self.urls: set[str] = set()
        self.rows: dict[tuple[str, str], dict[int, list]] = {}
        self.delivered: dict[tuple[str, str, int], int] = {}
        self.latency_ms: list[float] = []
        self.exchange_ms: int = 0

    def __call__(self, url, params=None, timeout=None):
        if url != KLINE_URL:
            raise RuntimeError("only the public kline endpoint is allowed in this trial")
        self.urls.add(url)
        self.calls += 1
        time.sleep(self.pause_s)
        if self.fault is not None:
            self.fault(self.calls)                       # may raise to simulate an outage
        started = time.perf_counter()
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            self.errors[type(exc).__name__] = self.errors.get(type(exc).__name__, 0) + 1
            raise
        finally:
            self.latency_ms.append((time.perf_counter() - started) * 1000)
        exchange = payload.get("time") if isinstance(payload, dict) else None
        if isinstance(exchange, int):
            self.exchange_ms = max(self.exchange_ms, exchange)
            key = (params["symbol"], params["interval"])
            bucket = self.rows.setdefault(key, {})
            for row in (payload.get("result") or {}).get("list", []):
                start = int(row[0])
                bucket.setdefault(start, row)
                self.delivered.setdefault((key[0], key[1], start), exchange)
        return _Replay(payload)


class _Replay:
    def __init__(self, payload):
        self._payload, self.status_code = payload, 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def backend_listening(port: int = 8765) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def build(db: Path, store: Path, journal: Path, recorder, busy, arrival_cursor: int) -> MirrorSidecar:
    return MirrorSidecar(
        database_path=db, account=ACCOUNT, candidate_store_dir=store,
        candles=BybitClosedKlineSource(http_get=recorder), journal=ObservationJournal(journal),
        protection_busy=busy, clock_ms=lambda: int(time.time() * 1000),
        arrival_cursor_ms=arrival_cursor, writer=_Sync())


class _Sync:
    dropped = 0

    def submit(self, write):
        write()
        return True


def converge(sidecar: MirrorSidecar, *, max_cycles: int) -> dict:
    cycles, produced = [], []
    for number in range(1, max_cycles + 1):
        before = dict(sidecar.candle_cursor)
        cpu = time.process_time()
        records = sidecar.cycle()
        produced.extend(records)
        cycles.append({"cycle": number, "new_observations": len(records),
                       "cpu_s": round(time.process_time() - cpu, 3),
                       "progressed": sum(1 for k, v in sidecar.candle_cursor.items() if v != before.get(k))})
        if number > 1 and not cycles[-1]["progressed"] and not records:
            break
    return {"cycles": cycles, "produced": produced}


def load_journal(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def signature(lines: list[dict], ceiling_ms: int) -> list[tuple]:
    return sorted((r["observation_id"], r["event"], r["decision"]) for r in lines
                  if int(r["candle_close_time_ms"]) <= ceiling_ms)


def owner_rule_breakout(boundary, row, close_ms: int) -> bool:
    """Owner rule (plan 2.1), recomputed from a raw Bybit row: the body crosses the level strictly.

    UP: open < line(t_open) and close > line(t_close); DOWN mirrors it. Wicks and equality do not count.
    """

    o, c = float(row[1]), float(row[4])
    at_open, at_close = boundary.price_at(close_ms - FIVE), boundary.price_at(close_ms)
    return (o < at_open and c > at_close) or (o > at_open and c < at_close)


def verify_events(events_path: Path, store: Path, pause_s: float) -> dict:
    """Post-hoc, fully independent: re-fetch each breakout candle and recompute with the owner rule."""

    from mirror_retest_observer import boundaries_from_candidate_snapshot
    from robot_candidate_store import load_candidate
    from mirror_retest_sidecar import _iso_ms

    recorder = Recorder(_default_session(), pause_s=pause_s)
    cache: dict[str, dict] = {}
    result = {"breakouts_checked": 0, "owner_rule_confirmed": 0, "mismatches": [], "fetch_failures": []}
    for event in json.loads(events_path.read_text(encoding="utf-8")):
        if event["event"] != "NAKED_BREAKOUT":
            continue
        ref = event["boundary_id"].split(":")[0]
        if ref not in cache:
            envelope = load_candidate(ref, store_dir=store)
            cache[ref] = {b.boundary_id: b for b in boundaries_from_candidate_snapshot(
                candidate_id=ref, created_at_ms=_iso_ms(envelope["created_at"]),
                signal_snapshot=envelope["signal_snapshot"])}
            cache[ref]["_symbol"] = envelope["symbol"]
        boundary, symbol = cache[ref][event["boundary_id"]], cache[ref]["_symbol"]
        close = int(event["candle_close_time_ms"])
        result["breakouts_checked"] += 1
        try:
            recorder(KLINE_URL, params={"category": "linear", "symbol": symbol, "interval": "5",
                                        "start": close - FIVE, "end": close - 1, "limit": 1}, timeout=10)
        except Exception as exc:
            result["fetch_failures"].append((symbol, close, type(exc).__name__))
            continue
        row = recorder.rows.get((symbol, "5"), {}).get(close - FIVE)
        if row is not None and owner_rule_breakout(boundary, row, close):
            result["owner_rule_confirmed"] += 1
        else:
            result["mismatches"].append((symbol, close))
    return result


def independent_checks(sidecar: MirrorSidecar, recorder: Recorder, lines: list[dict], ceiling_ms: int) -> dict:
    boundaries = {b.boundary_id: b for t in sidecar.tracked.values() for b in t.boundaries}
    symbol_of = {b.boundary_id: t.symbol for t in sidecar.tracked.values() for b in t.boundaries}
    result = {"continuity_gaps": [], "lookahead_violations": 0, "stale_candidates": [], "strict_body_mismatch": [],
              "proven_without_1m_contact": [], "checked_candles": 0, "checked_observations": 0}
    newest_close = (ceiling_ms // FIVE) * FIVE
    for ref, tracked in sidecar.tracked.items():
        cursor = sidecar.candle_cursor.get(ref)
        raw = recorder.rows.get((tracked.symbol, "5"), {})
        start = None
        for boundary in tracked.boundaries:
            start = boundary.as_of_time_ms - boundary.as_of_time_ms % FIVE if start is None else start
        if cursor is None or start is None:
            continue
        for open_ms in range(start, cursor, FIVE):
            result["checked_candles"] += 1
            if open_ms not in raw:
                result["continuity_gaps"].append((tracked.symbol, open_ms))
            elif recorder.delivered[(tracked.symbol, "5", open_ms)] < open_ms + FIVE:
                result["lookahead_violations"] += 1
        if cursor < newest_close - 2 * FIVE:
            result["stale_candidates"].append((tracked.symbol, ref, cursor))
    for record in lines:
        close = int(record["candle_close_time_ms"])
        if close > ceiling_ms:
            continue
        result["checked_observations"] += 1
        symbol, boundary = symbol_of.get(record["boundary_id"]), boundaries.get(record["boundary_id"])
        if boundary is None:
            continue
        if recorder.delivered.get((symbol, "5", close - FIVE), 0) < close:
            result["lookahead_violations"] += 1
        if record["event"] == "NAKED_BREAKOUT":
            row = recorder.rows.get((symbol, "5"), {}).get(close - FIVE)
            if row:
                if not owner_rule_breakout(boundary, row, close):
                    result["strict_body_mismatch"].append((symbol, close))
        if record["event"] == "RETEST_PROVEN":
            touched = False
            for open_ms in range(close - FIVE, close, ONE):
                row = recorder.rows.get((symbol, "1"), {}).get(open_ms)
                if row:
                    low, high = float(row[3]), float(row[2])
                    ends = [boundary.price_at(open_ms), boundary.price_at(open_ms + ONE)]
                    if low <= max(ends) and high >= min(ends):
                        touched = True
                        break
            if not touched:
                result["proven_without_1m_contact"].append((symbol, close))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--verify-events", help="events.json of an earlier run: re-check its breakouts independently and exit")
    parser.add_argument("--max-candidates", type=int, default=30)
    parser.add_argument("--max-cycles", type=int, default=12)
    parser.add_argument("--pause-s", type=float, default=0.35)
    args = parser.parse_args()
    db, store, out = Path(args.db), Path(args.store), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.verify_events:
        verdict = verify_events(Path(args.verify_events), store, args.pause_s)
        (out / "verify_breakouts.json").write_text(json.dumps(verdict, indent=1, default=str), encoding="utf-8")
        print(json.dumps(verdict, indent=1, default=str))
        return 0
    db_stat = (db.stat().st_size, db.stat().st_mtime_ns)
    report: dict = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "backend_listening": backend_listening()}
    tracemalloc.start()
    cpu0 = time.process_time()

    reader = SQLiteStore.open_reader(db)
    with reader.read_snapshot():
        arrivals = [item for item in read_new_wedge_arrivals(reader, ACCOUNT, after_ms=0)
                    if (store / f"{item[0]}.json").exists()]
    reader.close()
    chosen = arrivals[-args.max_candidates:]
    arrival_cursor = chosen[0][1] - 1
    report["arrivals_available_with_envelope"] = len(arrivals)
    report["candidates_selected"] = len(chosen)
    report["selected_window_utc"] = [time.strftime("%Y-%m-%d %H:%M", time.gmtime(chosen[0][1] / 1000)),
                                     time.strftime("%Y-%m-%d %H:%M", time.gmtime(chosen[-1][1] / 1000))]

    session = _default_session()

    # A) real gate against the stopped backend: fail-closed, no candle request at all
    rec_a = Recorder(session, pause_s=args.pause_s)
    gate = ProtectionHealthGate()
    side_a = build(db, store, out / "journal_A.jsonl", rec_a, gate.busy, arrival_cursor)
    produced_a = [r for _ in range(3) for r in side_a.cycle()]
    report["A_gate_closed"] = {"produced": len(produced_a), "kline_requests": rec_a.calls, "gate_reason": gate.last_reason,
                               "skipped_for_protection": side_a.metrics.skipped_for_protection,
                               "candidates_tracked": side_a.metrics.candidates_tracked}

    # B) idle gate injected (offline trial only): catch-up over real public candles
    rec_b = Recorder(session, pause_s=args.pause_s)
    journal_b = out / "journal_B.jsonl"
    journal_b.unlink(missing_ok=True)
    side_b = build(db, store, journal_b, rec_b, lambda: False, arrival_cursor)
    run_b = converge(side_b, max_cycles=args.max_cycles)
    ceiling = rec_b.exchange_ms
    lines_b = load_journal(journal_b)
    report["B_catch_up"] = {
        "cycles": run_b["cycles"], "kline_requests": rec_b.calls, "errors": rec_b.errors,
        "median_latency_ms": round(sorted(rec_b.latency_ms)[len(rec_b.latency_ms) // 2], 1) if rec_b.latency_ms else None,
        "metrics": vars(side_b.metrics), "source_unavailable": side_b.candles.unavailable, "source_stale": side_b.candles.stale,
        "exchange_time_ceiling_ms": ceiling,
        "events": {event: sum(1 for r in lines_b if r["event"] == event) for event in sorted({r["event"] for r in lines_b})},
        "decisions": {d: sum(1 for r in lines_b if r["decision"] == d) for d in sorted({r["decision"] for r in lines_b})},
        "all_observe_only_non_executable": all(r["mode"] == "OBSERVE_ONLY" and not r["executable"]
                                               and not r["admission_allowed"] for r in lines_b),
    }
    report["B_independent_checks"] = independent_checks(side_b, rec_b, lines_b, ceiling)

    # C) the same candidates under an injected outage then flapping: must converge to B
    def outage(call_number: int) -> None:
        if call_number <= 4 or call_number % 7 == 0:
            raise ConnectionError("injected outage")

    rec_c = Recorder(session, pause_s=args.pause_s, fault=outage)
    journal_c = out / "journal_C.jsonl"
    journal_c.unlink(missing_ok=True)
    side_c = build(db, store, journal_c, rec_c, lambda: False, arrival_cursor)
    run_c = converge(side_c, max_cycles=args.max_cycles * 3)
    lines_c = load_journal(journal_c)
    report["C_recovery"] = {
        "kline_requests": rec_c.calls, "injected_failures_seen": side_c.candles.unavailable,
        "cycles": len(run_c["cycles"]),
        "same_observations_as_B_up_to_ceiling": signature(lines_b, ceiling) == signature(lines_c, ceiling),
        "b_count": len(signature(lines_b, ceiling)), "c_count": len(signature(lines_c, ceiling)),
    }

    # D) restart on the same journal: nothing may be duplicated
    before = len(load_journal(journal_b))
    rec_d = Recorder(session, pause_s=args.pause_s)
    side_d = build(db, store, journal_b, rec_d, lambda: False, arrival_cursor)
    converge(side_d, max_cycles=args.max_cycles)
    after_lines = load_journal(journal_b)
    ids = [r["observation_id"] for r in after_lines]
    report["D_restart_dedupe"] = {
        "lines_before": before, "lines_after": len(after_lines), "duplicate_ids": len(ids) - len(set(ids)),
        "new_lines_all_after_ceiling": all(int(r["candle_close_time_ms"]) > ceiling for r in after_lines[before:]),
    }

    peak = tracemalloc.get_traced_memory()[1]
    report["resources"] = {"cpu_s_total": round(time.process_time() - cpu0, 2), "tracemalloc_peak_mb": round(peak / 1e6, 1)}
    report["safety"] = {"urls_hit": sorted(rec_b.urls | rec_c.urls | rec_d.urls | rec_a.urls),
                        "db_unchanged": (db.stat().st_size, db.stat().st_mtime_ns) == db_stat}
    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "summary.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str), encoding="utf-8")
    events = [{k: r[k] for k in ("boundary_id", "event", "decision", "candle_close_time_ms", "reasons")} for r in lines_b]
    (out / "events.json").write_text(json.dumps(events, indent=1, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k not in ("B_catch_up",)}, indent=1, default=str)[:6000])
    print("B events:", report["B_catch_up"]["events"], "decisions:", report["B_catch_up"]["decisions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
