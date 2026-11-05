"""MIRROR-INTEGRATION-6: measure the sidecar's per-cycle database cost (no tracemalloc, no network).

Run from the root of the checkout whose ``mirror_retest_sidecar`` should be measured, so the same script compares
two commits on the same read-only DB copy:

    python <this file> --db COPY --store ENVELOPES --label before|after --out result.json

``--profile`` additionally times each store read used by a cycle (3 calls each, min).
Candles come from an empty offline source (every cycle after the first is an empty cycle) or, with ``--event``,
from a source that serves one strict breakout candle for one tracked candidate, to measure an event cycle.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from mirror_retest_observer import ObservationJournal  # noqa: E402
import mirror_retest_sidecar as sidecar_module  # noqa: E402
from mirror_retest_sidecar import MirrorSidecar  # noqa: E402
from terminal.domain.models import TradingAccountId  # noqa: E402
from terminal.persistence.sqlite_store import SQLiteStore  # noqa: E402

ACCOUNT = TradingAccountId("paper")


class _Sync:
    dropped = 0

    def submit(self, write):
        write()
        return True


class EmptySource:
    def closed_candles(self, candidate_id, symbol, after_close_ms):
        return []


class OneBreakoutSource:
    """Serves, once, a candle that strictly crosses the upper boundary of the first tracked candidate."""

    def __init__(self, sidecar_ref):
        self.ref, self.served = sidecar_ref, False
        self.sidecar = None

    def closed_candles(self, candidate_id, symbol, after_close_ms):
        if self.served or candidate_id != self.ref() or after_close_ms is None:
            return []
        bounds = {b.boundary_id.rsplit(":", 1)[1]: b for b in self.sidecar.tracked[candidate_id].boundaries}
        upper, lower = bounds["upper"], bounds["lower"]

        def mid(t):
            return (upper.price_at(t) + lower.price_at(t)) / 2

        # 1) a flat candle inside the wedge (it may open before as_of: never a breakout, keeps continuity)
        q = after_close_ms
        quiet = {"open_time_ms": q, "close_time_ms": q + 300_000, "open": mid(q), "high": mid(q),
                 "low": mid(q), "close": mid(q), "closed": True}
        # 2) the next candle opens inside the wedge and closes strictly above the upper line
        o = q + 300_000
        close = upper.price_at(o + 300_000) * 1.01
        breakout = {"open_time_ms": o, "close_time_ms": o + 300_000, "open": mid(o), "high": close,
                    "low": mid(o), "close": close, "closed": True}
        self.served = True
        return [quiet, breakout]


def timed(fn):
    cpu, wall = time.process_time(), time.perf_counter()
    result = fn()
    return result, round(time.process_time() - cpu, 3), round(time.perf_counter() - wall, 3)


def profile(db: Path) -> dict:
    import terminal.application.robot_autopilot  # noqa: F401  (import cost outside the timing)
    from terminal.application.paper_daily_equity import paper_daily_equity_facts_in_transaction
    from terminal.domain.models import Symbol

    now = int(time.time() * 1000)
    steps = {
        "count_robot_auto_decisions": lambda r: r.count_robot_auto_decisions(ACCOUNT),
        "load_robot_auto_decision_heads": lambda r: r.load_robot_auto_decision_heads(
            ACCOUNT, keep_mode="PAPER_AUTO", keep_outcome="ALLOW"),
        "paper_daily_equity_facts_in_transaction": lambda r: paper_daily_equity_facts_in_transaction(
            r, ACCOUNT, as_of_ms=now, marks={}, max_mark_age_ms=0),
        "load_robot_auto_decisions_for_admission": lambda r: r.load_robot_auto_decisions_for_admission(
            ACCOUNT, candidate_ref="", source_identity="", policy_version="", business_date_msk="2026-10-19"),
        "load_open_robot_trades": lambda r: r.load_open_robot_trades(ACCOUNT),
        "load_open_position_projections": lambda r: r.load_open_position_projections(ACCOUNT),
        "load_robot_candidates_by_status": lambda r: r.load_robot_candidates_by_status(ACCOUNT, ("APPROVED", "OPEN")),
        "load_active_paper_limits(one symbol)": lambda r: r.load_active_paper_limits(ACCOUNT, Symbol("BTCUSDT")),
        "read_account_facts (whole)": lambda r: sidecar_module.read_account_facts(r, ACCOUNT, now_ms=now),
    }
    out = {}
    for name, step in steps.items():
        runs = []
        for _ in range(3):
            reader = SQLiteStore.open_reader(db)
            try:
                with reader.read_snapshot():
                    _, cpu, wall = timed(lambda: step(reader))
            finally:
                reader.close()
            runs.append((cpu, wall))
        out[name] = {"cpu_s_min": min(c for c, _ in runs), "wall_s_min": min(w for _, w in runs)}
    return out


def build(db, store, journal, candles) -> MirrorSidecar:
    return MirrorSidecar(
        database_path=db, account=ACCOUNT, candidate_store_dir=store, candles=candles,
        journal=ObservationJournal(journal), protection_busy=lambda: False,
        clock_ms=lambda: int(time.time() * 1000), writer=_Sync())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cycles", type=int, default=6)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    db, store, out = Path(args.db), Path(args.store), Path(args.out)
    stat = (db.stat().st_size, db.stat().st_mtime_ns)
    result: dict = {"label": args.label, "sidecar_file": str(Path(sidecar_module.__file__).resolve())}
    if args.profile:
        result["profile"] = profile(db)

    journal = out.with_suffix(".journal.jsonl")
    journal.unlink(missing_ok=True)
    sidecar = build(db, store, journal, EmptySource())
    cycles = []
    for number in range(1, args.cycles + 1):
        _, cpu, wall = timed(sidecar.cycle)
        cycles.append({"cycle": number, "cpu_s": cpu, "wall_s": wall, "tracked": len(sidecar.tracked)})
    result["empty_source_cycles"] = cycles

    # one event cycle: a strict breakout for one tracked candidate (needs account facts for the decision)
    source = OneBreakoutSource(lambda: next(iter(sidecar.tracked)))
    source.sidecar = sidecar
    sidecar.candles = source
    records, cpu, wall = timed(sidecar.cycle)
    result["event_cycle"] = {"cpu_s": cpu, "wall_s": wall, "records": [(r.event, r.decision, list(r.reasons)) for r in records]}
    _, cpu, wall = timed(sidecar.cycle)
    result["after_event_empty_cycle"] = {"cpu_s": cpu, "wall_s": wall}
    result["metrics"] = vars(sidecar.metrics)
    result["db_unchanged"] = (db.stat().st_size, db.stat().st_mtime_ns) == stat
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
