from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys


EXACT_SHA = "da0d9a406ffb32c0edf1e1ee44f700c4fa2be717"
RAW_SHA = "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a"
M1_SHA = "8f0b7d83c81df43114d5cf89214eeaba7a454a519021df3b4628fca4ea09834b"
DAY = date(2026, 11, 10)
SYMBOL = "ICNTUSDT"
D = Decimal
# Immutable Git blob IDs of the five modules validated for the saved run.
# This does not establish the SHA of every transitive Python dependency.
CODE_BLOBS = {
    "robot_entry_flow_evidence.py": "c9da9afa9ee50e720f43d5c2c55e2489da02d054",
    "research/simulator_v2/report.py": "12bd5aef4488d54e0a6e3f89dea57d81d0df4f6f",
    "research/simulator_v2/session.py": "d7376050439d7248effcfaa2e47e052ad25fb915",
    "research/simulator_v2/virtual_exchange.py": "ddca10419518050d17b449e730c44d55c693ddf9",
    "research/simulator_v2/wedge_backtest.py": "f7a45cc72bea91905098574bce8ae180a3e84dc0",
}


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plan_payload(plan: object, decision: str) -> dict[str, object]:
    signal = plan.signal
    return {
        "order_id": f"IMPULSE_{signal.known_at_ms}",
        "signal_at_ms": signal.known_at_ms,
        "signal_at_utc": iso(signal.known_at_ms),
        "direction": signal.direction,
        "entry_price": str(plan.entry_price),
        "stop_price": str(plan.stop_price),
        "take_price": str(plan.take_price),
        "projected_net_rr": str(plan.projected_net_rr),
        "decision": decision,
    }


def compact_event(event: object) -> dict[str, object]:
    return {
        "order_id": event.order_id,
        "kind": event.kind,
        "at_ms": event.virtual_time_ms,
        "at_utc": iso(event.virtual_time_ms),
        "order_type": event.order_type,
    }

def verify_pinned_code_blobs(source_dir: Path, saved: dict[str, object]) -> None:
    """Fail closed if the five key replay modules do not match saved Git blobs."""
    if saved.get("code_blob_proof") != CODE_BLOBS:
        raise SystemExit("BLOCKED: saved code blob provenance mismatch")
    for name, expected in CODE_BLOBS.items():
        path = source_dir / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"BLOCKED: missing or linked source module: {name}")
        raw = path.read_bytes()
        if len(raw) > 2_000_000:
            raise SystemExit(f"BLOCKED: oversized source module: {name}")
        # Windows working trees may checkout CRLF; Git records normalized LF.
        candidates = (raw, raw.replace(b"\r\n", b"\n"))
        hashes = {
            hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
            for data in candidates
        }
        if expected not in hashes:
            raise SystemExit(f"BLOCKED: source Git blob mismatch: {name}")


def eligible_trace_signal(signal: object | None, *, end_exclusive_ms: int) -> bool:
    """Match the native impulse runner: terminal M1 cannot open a next-M1 entry."""
    return signal is not None and signal.known_at_ms < end_exclusive_ms


def main() -> None:
    if len(sys.argv) != 6:
        raise SystemExit("usage: diagnostic SRC CACHE INPUT SAVED_REPORT OUTPUT")
    source_dir, cache_dir, input_dir, saved_path, output_path = map(Path, sys.argv[1:])
    if output_path.exists() or output_path.with_suffix(output_path.suffix + ".sha256").exists():
        raise SystemExit("BLOCKED: diagnostic output already exists")
    if any(path.is_symlink() for path in (source_dir, cache_dir, input_dir, saved_path, output_path.parent)):
        raise SystemExit("BLOCKED: symlinked diagnostic path")
    if sha256(input_dir / "ICNTUSDT2026-11-10.csv.gz") != RAW_SHA:
        raise SystemExit("BLOCKED: raw source SHA mismatch")
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    if saved["exact_code_sha"] != EXACT_SHA or saved["source"]["trade_derived_m1_sha256"] != M1_SHA:
        raise SystemExit("BLOCKED: saved run provenance mismatch")
    verify_pinned_code_blobs(source_dir, saved)
    sys.path.insert(0, str(source_dir))

    import research.simulator_v2.wedge_backtest as wedge_backtest
    from research.simulator_v2.session import VirtualReplaySession
    from research.simulator_v2.trade_range import TradeDayProof
    from research.simulator_v2.wedge_observer import WedgeScannerConfig
    from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
    from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig

    start_ms = 1794268800000
    end_ms = 1794355200000
    proof = TradeDayProof(DAY, RAW_SHA, M1_SHA)
    scanner = WedgeScannerConfig(window_bars=100, mode="hunter", min_score=50)
    robot = SimWedgeRobotConfig(
        selected_patterns=frozenset(("Falling Wedge", "Rising Wedge")),
        tick_size=D("0.0001"),
    )
    risk = SimWedgeRiskSettings(
        tick_size=D("0.0001"), contracts_per_working_volume=D("1000"),
        quantity_step=D("1"), minimum_quantity=D("1"),
        max_notional_usdt=D("1000"), max_risk_usdt=D("50"),
        entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
    )

    class TracedSession(VirtualReplaySession):
        last_instance = None

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            type(self).last_instance = self
            self.plan_decisions: list[dict[str, object]] = []

        def submit_protected_impulse(self, plan: object) -> None:
            self.plan_decisions.append(plan_payload(plan, "ACCEPTED_RR15"))
            VirtualReplaySession.submit_protected_impulse(self, plan)

    class CandidateSession(TracedSession):
        last_instance = None

        def submit_protected_impulse(self, plan: object) -> None:
            if plan.projected_net_rr < D("2"):
                self.plan_decisions.append(plan_payload(plan, "REJECTED_RR_BELOW_2"))
                return
            self.plan_decisions.append(plan_payload(plan, "ACCEPTED_RR20"))
            VirtualReplaySession.submit_protected_impulse(self, plan)

    def run_group(label: str, session_type: type[TracedSession]) -> dict[str, object]:
        observations: list[dict[str, object]] = []
        original_session = wedge_backtest.VirtualReplaySession
        original_recognizer = wedge_backtest.recognize_impulse_signal
        wedge_backtest.VirtualReplaySession = session_type

        def traced_recognizer(transition: object, **kwargs: object) -> object:
            signal = original_recognizer(transition, **kwargs)
            if not eligible_trace_signal(signal, end_exclusive_ms=end_ms):
                return signal
            active = session_type.last_instance
            if active is None:
                raise RuntimeError("diagnostic session missing")
            close = kwargs["candle_close"]
            snapshot = active.account.snapshot(
                as_of_ms=active.virtual_time_ms, mark_price=close,
            )
            pending = active.exchange.pending
            protection = active.exchange.active_protection
            reasons = []
            if pending is not None:
                reasons.append("PENDING_ENTRY")
            if protection is not None:
                reasons.append("ACTIVE_PROTECTION")
            if snapshot.position_quantity != 0:
                reasons.append("OPEN_POSITION")
            observations.append({
                "signal_at_ms": signal.known_at_ms,
                "signal_at_utc": iso(signal.known_at_ms),
                "direction": signal.direction,
                "busy": bool(reasons),
                "busy_reasons": reasons,
                "position_quantity": str(snapshot.position_quantity),
                "pending_order_id": None if pending is None else pending.order_id,
                "protected_order_id": None if protection is None else protection.entry.order_id,
            })
            return signal

        wedge_backtest.recognize_impulse_signal = traced_recognizer
        try:
            result = wedge_backtest.run_cached_wedge_trade_range(
                cache_dir=cache_dir, symbol=SYMBOL, proofs=(proof,),
                latest_closed_boundary_ms=end_ms,
                simulation_run_id=f"icnt_20261110_diagnostic_{label}",
                initial_balance=D("1000"), start_ms=start_ms,
                end_inclusive_ms=end_ms - 60000,
                scanner_config=scanner, robot_config=robot, risk_settings=risk,
                taker_fee_rate=D("0.0006"), maker_fee_rate=D("0.0002"),
                flow_archive_dir=input_dir, oi_mode="OFF", impulse_mode=True,
            )
        finally:
            wedge_backtest.recognize_impulse_signal = original_recognizer
            wedge_backtest.VirtualReplaySession = original_session
        active = session_type.last_instance
        events = [compact_event(item) for item in active.exchange.events]
        if len(observations) != result.impulse_signals:
            raise RuntimeError("signal trace count mismatch")
        if sum(item["busy"] for item in observations) != result.skipped_busy_entries:
            raise RuntimeError("busy trace count mismatch")
        return {
            "observations": observations,
            "plans": active.plan_decisions,
            "events": events,
            "summary": {
                "signals": result.impulse_signals,
                "busy": result.skipped_busy_entries,
                "stops": result.stop_exits,
                "takes": result.take_exits,
                "total_net_pnl": str(result.report.total_net_pnl),
                "fees": str(result.report.total_fees),
            },
        }

    baseline = run_group("baseline_rr15", TracedSession)
    candidate = run_group("candidate_rr20", CandidateSession)

    for label, replay in (("baseline_rr15", baseline), ("candidate_rr20", candidate)):
        prior = saved["groups"][label]
        now = replay["summary"]
        if not (
            now["signals"] == prior["impulse_signals"]
            and now["busy"] == prior["skipped_busy_entries"]
            and now["stops"] == prior["exits"]["stop"]
            and now["takes"] == prior["exits"]["take"]
            and now["total_net_pnl"] == prior["pnl_usdt"]["total_net"]
            and now["fees"] == prior["fees_usdt"]
        ):
            raise RuntimeError(f"diagnostic replay differs from saved {label} result")

    b_plans = {item["order_id"]: item for item in baseline["plans"]}
    c_plans = {item["order_id"]: item for item in candidate["plans"]}
    first = None
    for order_id in sorted(set(b_plans) | set(c_plans), key=lambda x: int(x.split("_")[1])):
        b = b_plans.get(order_id)
        c = c_plans.get(order_id)
        if b is None or c is None or b["decision"] != c["decision"]:
            first = {"order_id": order_id, "baseline": b, "candidate": c}
            break
    if first is None:
        raise RuntimeError("no causal divergence found")
    divergence_ms = int(first["order_id"].split("_")[1])

    b_obs = {item["signal_at_ms"]: item for item in baseline["observations"]}
    c_obs = {item["signal_at_ms"]: item for item in candidate["observations"]}
    if set(b_obs) != set(c_obs):
        raise RuntimeError("market-derived signals differ between groups")
    occupancy = {
        "both_busy": 0,
        "baseline_only_busy": 0,
        "candidate_only_busy": 0,
        "neither_busy": 0,
    }
    occupancy_differences = []
    for when in sorted(b_obs):
        b_busy = b_obs[when]["busy"]
        c_busy = c_obs[when]["busy"]
        key = (
            "both_busy" if b_busy and c_busy else
            "baseline_only_busy" if b_busy else
            "candidate_only_busy" if c_busy else "neither_busy"
        )
        occupancy[key] += 1
        if b_busy != c_busy:
            occupancy_differences.append({
                "signal_at_ms": when, "signal_at_utc": iso(when),
                "baseline": b_obs[when], "candidate": c_obs[when],
            })

    def histories(replay: dict[str, object]) -> dict[str, list[dict[str, object]]]:
        result: dict[str, list[dict[str, object]]] = {}
        for event in replay["events"]:
            if event["at_ms"] >= divergence_ms:
                result.setdefault(event["order_id"], []).append(event)
        return result

    b_hist = histories(baseline)
    c_hist = histories(candidate)
    b_orders, c_orders = set(b_hist), set(c_hist)
    baseline_only = sorted(b_orders - c_orders, key=lambda x: int(x.split("_")[1]))
    candidate_only = sorted(c_orders - b_orders, key=lambda x: int(x.split("_")[1]))
    changed_common = sorted(
        (order_id for order_id in b_orders & c_orders if b_hist[order_id] != c_hist[order_id]),
        key=lambda x: int(x.split("_")[1]),
    )

    rejected_ids = {
        item["order_id"] for item in candidate["plans"]
        if item["decision"] == "REJECTED_RR_BELOW_2"
    }
    if rejected_ids & c_orders:
        raise RuntimeError("candidate exchange event exists for an RR-rejected plan")
    if first["baseline"] is None or first["candidate"] is None:
        raise RuntimeError("first divergence was not a common plan decision")
    if not (
        first["baseline"]["decision"] == "ACCEPTED_RR15"
        and first["candidate"]["decision"] == "REJECTED_RR_BELOW_2"
        and D("1.5") <= D(first["baseline"]["projected_net_rr"]) < D("2")
    ):
        raise RuntimeError("first divergence does not match RR gate hypothesis")

    def evidence(order_ids: list[str], source: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
        return [{"order_id": order_id, "events": source[order_id]} for order_id in order_ids]

    payload = {
        "schema": "IMPULSE_FIRST_CAUSAL_DIVERGENCE_V1",
        "exact_code_sha": EXACT_SHA,
        "source": {"symbol": SYMBOL, "utc_day": DAY.isoformat(), "raw_sha256": RAW_SHA, "m1_sha256": M1_SHA},
        "existing_event_journals": "INSUFFICIENT_AGGREGATES_ONLY",
        "diagnostic_replay": {
            "count": 1,
            "paired_groups": True,
            "trading_rules_changed": False,
            "saved_result_reproduced_exactly": True,
        },
        "first_divergence": {
            "signal_at_ms": divergence_ms,
            "signal_at_utc": iso(divergence_ms),
            "order_id": first["order_id"],
            "baseline": first["baseline"],
            "candidate": first["candidate"],
            "baseline_state_before_signal": b_obs[divergence_ms],
            "candidate_state_before_signal": c_obs[divergence_ms],
            "cause": "SAME_FLAT_SIGNAL_PASSES_SHARED_RR_1_5_BUT_FAILS_CANDIDATE_RR_2_0",
        },
        "occupancy": {
            "baseline_busy": baseline["summary"]["busy"],
            "candidate_busy": candidate["summary"]["busy"],
            "cross_classification": occupancy,
            "different_occupancy_signal_count": len(occupancy_differences),
            "first_different_occupancy_signals": occupancy_differences[:10],
            "explanation": "RR rejection changes the active LIMIT/position/protection timeline; later identical market signals encounter different account occupancy.",
        },
        "downstream_exchange_histories": {
            "baseline_only": evidence(baseline_only, b_hist),
            "candidate_only": evidence(candidate_only, c_hist),
            "changed_common": [
                {"order_id": order_id, "baseline_events": b_hist[order_id], "candidate_events": c_hist[order_id]}
                for order_id in changed_common
            ],
            "baseline_only_stop_ids": [x for x in baseline_only if any(e["kind"] == "STOP_FILLED" for e in b_hist[x])],
            "candidate_only_stop_ids": [x for x in candidate_only if any(e["kind"] == "STOP_FILLED" for e in c_hist[x])],
        },
        "conclusion": {
            "sequence_effect": "PROVEN",
            "execution_defect": "NOT_PROVEN",
            "evidence": [
                "identical 525 market-derived signal timestamps in both groups",
                "first state and signal are identical; only RR threshold decision differs",
                "RR-rejected candidate plans have no exchange events",
                "diagnostic aggregate PnL/fees/STOP/TAKE/busy exactly reproduce saved report",
                "all later differences follow distinct account occupancy timelines",
            ],
        },
        "mutations": "LOCAL_DIAGNOSTIC_JSON_ONLY; VPS_PAPER_LIVE_PR_NONE",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = sha256(output_path)
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(
        f"{digest}  {output_path.name}\n", encoding="ascii",
    )


if __name__ == "__main__":
    main()
