"""One-day real-trade-derived MIRROR Scanner→Robot SIMULATION probe.

Input is an existing LOCAL Bybit public trade CSV.gz. No downloads, secrets,
PAPER service, network client, injected levels, fabricated fills, or strategy
rules in this module. The native Scanner is explicitly in automatic mode.
Economics are *illustrative* until verified instrument terms are supplied.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import resource
from time import perf_counter

import mirror_scanner
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms
from research.simulator_v2.robot_sandbox import ConnectedSimulationRobot
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.trade_archive import parse_local_trade_day

SYMBOL = "ICNTUSDT"
DAY = date(2026, 11, 7)
EXPECTED_ARCHIVE_SHA256 = (
    "6d81de558d1b4c1fe8c43caa8e1cdd9c1211feffcae3325dfff9909e999bcec8"
)
EXPECTED_DERIVED_M1_SHA256 = (
    "cd8c8544fb9adecf3b090a39b4f234eef004f7fbfab055e1134f6b31c1b43a1c"
)
# Allow only two independently verified public source archives. The second
# day's derived M1 checksum is emitted by this reproducible import and both
# counterfactual runs must prove exactly the same M1 digest.
ARCHIVE_SHA256_BY_DAY = {
    date(2026, 11, 7): EXPECTED_ARCHIVE_SHA256,
    date(2026, 11, 8): "797a84c3483f894b4041159ea6a8d2ef7e3377fbc6aac46b5fed28da357d3e6d",
}
# Explicitly hypothetical local size/tick assumptions; not actual Bybit
# instrument specs and not evidence of profitable deployable trading.
TERMS = BoxSimulationRiskTerms(
    tick_size=Decimal("0.0001"),
    working_quantity=Decimal("1"),
    quantity_step=Decimal("1"),
    minimum_quantity=Decimal("1"),
    maximum_notional_usdt=Decimal("1000"),
    maximum_loss_usdt=Decimal("100"),
    entry_fee_rate=Decimal("0.0006"),
    exit_fee_rate=Decimal("0.0006"),
    adverse_stop_slippage_per_unit=Decimal("0"),
    additional_cost_allowance_usdt=Decimal("0"),
)


def run_real_trade_day(
    archive: Path, *, one_filled_trade_per_campaign: bool = False,
    utc_day: date = DAY,
    next_day_archive: Path | None = None,
) -> dict[str, object]:
    if type(utc_day) is not date or utc_day not in ARCHIVE_SHA256_BY_DAY:
        raise ValueError("unapproved real-trades research UTC day")
    if type(one_filled_trade_per_campaign) is not bool:
        raise TypeError("explicit local comparison option must be boolean")
    if not isinstance(archive, Path) or archive.is_symlink() or not archive.is_file():
        raise ValueError("existing regular Bybit public trades archive required")
    end = int(datetime.combine(utc_day + timedelta(days=1),
                               datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    chunk, archive_sha = parse_local_trade_day(
        archive, symbol=SYMBOL, utc_day=utc_day, latest_closed_boundary_ms=end,
    )
    if archive_sha != ARCHIVE_SHA256_BY_DAY[utc_day]:
        raise ValueError("archive SHA mismatch; never substitute a different source")
    if (len(chunk.candles) != 1440 or
            (utc_day == DAY and chunk.sha256 != EXPECTED_DERIVED_M1_SHA256)):
        raise ValueError("derived M1 SHA/day coverage mismatch")
    second = None
    next_sha = None
    if next_day_archive is not None:
        next_day = utc_day + timedelta(days=1)
        if next_day not in ARCHIVE_SHA256_BY_DAY:
            raise ValueError("unapproved next UTC day")
        next_end = int(datetime.combine(
            next_day + timedelta(days=1), datetime.min.time(),
            tzinfo=timezone.utc,
        ).timestamp() * 1000)
        second, next_sha = parse_local_trade_day(
            next_day_archive, symbol=SYMBOL, utc_day=next_day,
            latest_closed_boundary_ms=next_end,
        )
        if next_sha != ARCHIVE_SHA256_BY_DAY[next_day] or len(second.candles) != 1440:
            raise ValueError("next-day archive SHA/M1 coverage mismatch")
        if chunk.end_ms != second.start_ms:
            raise ValueError("cross-day M1 continuity is not proven")
    # One continuous VirtualReplaySession/Scanner/Robot; no midnight reset.
    candles = chunk.candles + (second.candles if second is not None else ())
    history_end_ms = second.end_ms if second is not None else chunk.end_ms
    period_end = (utc_day + timedelta(days=1) if second is not None else utc_day)

    session = VirtualReplaySession(
        simulation_run_id=(
            f"icnt_{utc_day:%Y%m%d}_{period_end:%Y%m%d}_native_mirror_"
            + ("one_fill" if one_filled_trade_per_campaign else "original")
        ),
        symbol=SYMBOL, initial_balance=Decimal("1000"),
        taker_fee_rate=Decimal("0.0006"),
        maker_fee_rate=Decimal("0.0002"),
    )
    started = perf_counter()
    peak_equity = Decimal("1000")
    maximum_drawdown_pct = Decimal(0)
    with ConnectedSimulationRobot(
        session, tick_size=TERMS.tick_size, terms=TERMS,
        mirror_working_volume_usdt=Decimal("250"),
        mirror_risk_limit_usdt=Decimal("100"),
        mirror_auto_scan=True,
        mirror_one_filled_trade_per_campaign=one_filled_trade_per_campaign,
        mirror_research_skip_ambiguous=second is not None,
    ) as robot:
        for candle in candles:
            session.step(candle)
            robot.after_committed_minute()
            snapshot = session.account.snapshot(
                as_of_ms=session.virtual_time_ms, mark_price=candle.close,
            )
            if snapshot.equity > peak_equity:
                peak_equity = snapshot.equity
            drawdown = (peak_equity - snapshot.equity) / peak_equity * 100
            maximum_drawdown_pct = max(maximum_drawdown_pct, drawdown)

        market_end = candles[-1].close
        ending = session.account.snapshot(
            as_of_ms=session.virtual_time_ms, mark_price=market_end,
        )
        state = mirror_scanner.load_state(SYMBOL, "5", robot._mirror_root)
        signal_rows = state.get("standalone_entries") or ()
        candidates = tuple(robot._source_candidate_ids)
        trades = []
        # Public, post-replay diagnostics only. These immutable evidence rows
        # do not feed back into Scanner, Robot, virtual time, or execution.
        m5 = robot._mirror_source.recent_closed_m5()
        for candidate_id in candidates:
            trade = robot._store.get_robot_trade("robot-trade-" + candidate_id)
            if trade is None:
                continue
            candidate = robot._store.get_robot_candidate(candidate_id)
            if candidate is None or not isinstance(candidate.signal_snapshot, dict):
                raise ValueError("durable source candidate proof unavailable")
            frozen = candidate.signal_snapshot.get("mirror_entry")
            if not isinstance(frozen, dict) or not isinstance(frozen.get("confirmation"), dict):
                raise ValueError("native frozen MIRROR entry evidence unavailable")
            level_id = frozen.get("level_id")
            registry_level = next((item for item in state["registry"]["levels"]
                                   if item.get("level_id") == level_id), None)
            record = state["records"].get(level_id)
            if registry_level is None or record is None:
                raise ValueError("frozen MIRROR source level provenance missing")
            confirmation_ms = frozen["confirmation"]["close_time_ms"]
            # A counterfactual may end with an open virtual position; preserve
            # its causal evidence only up to the verified archive boundary.
            exit_boundary_ms = (trade.exit_time_ms if trade.exit_time_ms is not None
                                else history_end_ms)
            def m1_view(item):
                return {
                    "open_time_ms": item.start_ms, "close_time_ms": item.end_ms,
                    "open": str(item.open), "high": str(item.high),
                    "low": str(item.low), "close": str(item.close),
                }
            surrounding_m1 = [
                m1_view(c) for c in candles
                if confirmation_ms - 3 * 60_000 <= c.end_ms
                <= exit_boundary_ms + 60_000
            ]
            nearby_m5 = [
                {key: value for key, value in row.items()
                 if key in ("open_time_ms", "close_time_ms", "open", "high", "low", "close")}
                for row in m5
                if confirmation_ms - 12 * 300_000 <= row["close_time_ms"]
                <= exit_boundary_ms + 300_000
            ]
            trades.append({
                "candidate_id": candidate_id,
                "frozen_entry": frozen,
                "source_level": registry_level,
                "source_state_at_end": {
                    "status": record.get("status"),
                    "lifecycle": record.get("lifecycle"),
                    "candidate": record.get("candidate"),
                    "rejection": record.get("rejection"),
                    "breakout": (record.get("naked_retest") or {}).get("breakout"),
                    "retest": (record.get("naked_retest") or {}).get("retest"),
                    "breakout_evidence": record.get("breakout_evidence"),
                    "superseding_extremum": record.get("superseding_extremum"),
                },
                "m1_confirmation_to_exit": surrounding_m1,
                "m5_context": nearby_m5,
                "entry_time_ms": trade.entry_time_ms,
                "exit_time_ms": trade.exit_time_ms,
                "direction": trade.direction,
                "entry_quantity": str(trade.entry_quantity),
                "entry_price": str(trade.average_entry),
                "exit_price": str(trade.exit_price) if trade.exit_price is not None else None,
                "exit_reason": trade.exit_reason,
                "realized_pnl_gross_usdt": str(trade.realized_pnl_usdt) if trade.realized_pnl_usdt is not None else None,
                "fees_usdt": str(trade.fees_costs_usdt) if trade.fees_costs_usdt is not None else None,
                "pnl_percent_net": str(trade.realized_pnl_pct) if trade.realized_pnl_pct is not None else None,
            })
        # A diagnostic artifact must never silently omit the actual filled
        # episodes; all of their frozen source snapshots are mandatory.
        if len(trades) != sum(
            robot._store.get_robot_trade("robot-trade-" + cid) is not None
            for cid in candidates
        ):
            raise ValueError("incomplete native MIRROR trade diagnostics")
        closed_trades = [x for x in trades if x["exit_time_ms"] is not None]
        per_side = {
            "STOP": sum(x["exit_reason"] == "STOP" for x in closed_trades),
            "TAKE": sum(x["exit_reason"] == "TAKE" for x in closed_trades),
        }
        elapsed = perf_counter() - started
        return {
            "schema": "MIRROR_NATIVE_REAL_TRADES_REPLAY_V1",
            "simulated_only": True,
            "source": "BYBIT_PUBLIC_TRADES_DERIVED_M1_NOT_OFFICIAL_KLINE",
            "symbol": SYMBOL,
            "utc_day": utc_day.isoformat(),
            "utc_day_end": period_end.isoformat(),
            "archive_sha256": archive_sha,
            "archive_sha256_next_day": next_sha,
            "derived_m1_sha256": (
                chunk.sha256 if second is None
                else chunk.sha256 + ":" + second.sha256
            ),
            "closed_m1": len(candles),
            "closed_m5": robot._mirror_source._last_close_ms // 300_000 - chunk.start_ms // 300_000,
            "history_price_min": str(min(c.low for c in candles)),
            "history_price_max": str(max(c.high for c in candles)),
            "native_mirror_levels": len(state["registry"].get("levels") or {}),
            "native_confirmations": len(signal_rows),
            "native_robot_candidates": len(candidates),
            "experiment_one_filled_trade_per_campaign": one_filled_trade_per_campaign,
            "experiment_suppressed_confirmations": len(robot.mirror_experiment_suppressed),
            "experiment_suppressed_entry_ids": list(robot.mirror_experiment_suppressed),
            "research_skipped_ambiguous_events": [
                {"closed_m1_time_ms": ts, "candidate_entry_ids": list(ids)}
                for ts, ids in robot.mirror_ambiguous_research_events
            ],
            "research_skipped_ambiguous_minutes": len(robot.mirror_ambiguous_research_events),
            "virtual_fills": len(session.account.fills),
            "trades_with_attested_entry": len(trades),
            "trades_closed": len(closed_trades),
            "trades_open": len(trades) - len(closed_trades),
            "exit_counts": per_side,
            "initial_balance_usdt": "1000",
            "final_equity_usdt": str(ending.equity),
            "realized_net_pnl_usdt": str(ending.realized_net_pnl),
            "unrealized_pnl_usdt": str(ending.unrealized_pnl),
            "total_net_pnl_usdt": str(ending.total_net_pnl),
            "total_fees_usdt": str(ending.fees),
            "return_percent": str((ending.equity - ending.initial_balance) / ending.initial_balance * 100),
            "max_drawdown_percent": str(maximum_drawdown_pct),
            "final_position_quantity": str(ending.position_quantity),
            "pending_order": session.exchange.pending is not None,
            "stop_armed": session.exchange.robot_stop is not None,
            "take_armed": session.exchange.robot_take is not None,
            "runtime_seconds": round(elapsed, 3),
            "processed_minutes_per_second": round(len(candles) / elapsed, 2) if elapsed else None,
            "peak_rss_mib_linux": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
            "trades": trades,
            "limitations": [
                "one day and one symbol, no out-of-sample profitability inference",
                "instrument tick/step/min and 1-WV risk are hypothetical local research terms",
                "trade-derived M1 is not official Bybit kline; tied timestamps may differ",
                "OHLC trade-through does not prove book queue, depth, actual slippage",
                "scanner quality has no owner-labeled ground-truth precision/recall here",
                "neither VPS PAPER nor user PC integration was changed or accepted",
                "for consecutive days, simultaneous confirmations are excluded as whole minutes; no priority rule is inferred",
            ],
        }


def compare_campaign_fill_limit(
    archive: Path, *, utc_day: date = DAY,
    next_day_archive: Path | None = None,
) -> dict[str, object]:
    """Paired full independent historical replays, not post-hoc PnL deletion."""
    original = run_real_trade_day(
        archive, one_filled_trade_per_campaign=False, utc_day=utc_day,
        next_day_archive=next_day_archive,
    )
    restricted = run_real_trade_day(
        archive, one_filled_trade_per_campaign=True, utc_day=utc_day,
        next_day_archive=next_day_archive,
    )
    for key in ("archive_sha256", "archive_sha256_next_day",
                "derived_m1_sha256", "closed_m1",
                "native_mirror_levels", "native_confirmations"):
        if original[key] != restricted[key]:
            raise RuntimeError(f"comparison diverged before native Robot execution: {key}")
    if original["experiment_suppressed_confirmations"] != 0:
        raise RuntimeError("baseline MIRROR auto path was not unchanged")
    if (original["research_skipped_ambiguous_events"]
            != restricted["research_skipped_ambiguous_events"]):
        raise RuntimeError("counterfactual variants skipped different ambiguous groups")
    count_by_campaign: dict[tuple[str, int], int] = {}
    for trade in restricted["trades"]:
        if trade["entry_time_ms"] is None:
            continue
        frozen = trade["frozen_entry"]
        key = frozen["level_id"], frozen["level_breakout_close_ms"]
        count_by_campaign[key] = count_by_campaign.get(key, 0) + 1
    if any(count > 1 for count in count_by_campaign.values()):
        raise RuntimeError("experimental one-filled-trade invariant violated")
    if bool(original["trades"]) != bool(restricted["trades"]):
        raise RuntimeError("experiment changed whether the first trade filled")
    if original["trades"]:
        first_fields = ("entry_time_ms", "exit_time_ms", "direction",
                        "entry_price", "exit_price", "exit_reason", "entry_quantity",
                        "realized_pnl_gross_usdt", "fees_usdt", "pnl_percent_net")
        if any(original["trades"][0][key] != restricted["trades"][0][key]
               for key in first_fields):
            raise RuntimeError("experiment changed the original first fill or protection")
        if (original["trades"][0]["frozen_entry"]["level_id"]
                != restricted["trades"][0]["frozen_entry"]["level_id"]):
            raise RuntimeError("first native MIRROR source level unexpectedly changed")
    original_pnl = Decimal(original["total_net_pnl_usdt"])
    restricted_pnl = Decimal(restricted["total_net_pnl_usdt"])
    return {
        "schema": "MIRROR_REAL_CAMPAIGN_ONE_FILL_COMPARISON_V1",
        "utc_day": utc_day.isoformat(),
        "utc_day_end": original["utc_day_end"],
        "trade_source_sha256": original["archive_sha256"],
        "trade_source_sha256_next_day": original["archive_sha256_next_day"],
        "derived_m1_sha256": original["derived_m1_sha256"],
        "baseline": original,
        "first_filled_trade_only": restricted,
        "delta_net_pnl_usdt": str(restricted_pnl - original_pnl),
        "suppressed_confirmations": restricted["experiment_suppressed_confirmations"],
        "research_skipped_ambiguous_minutes": original["research_skipped_ambiguous_minutes"],
        "note": (
            "Pure SIMULATION hypothesis, risk/fees hypothetical; two "
            "independent native Scanner/Robot replays over identical verified M1."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Real public trade archive MIRROR SIMULATION")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--utc-day", default=DAY.isoformat(),
                        choices=tuple(sorted(d.isoformat() for d in ARCHIVE_SHA256_BY_DAY)))
    parser.add_argument("--next-day-archive", type=Path)
    parser.add_argument("--compare-one-fill", action="store_true")
    args = parser.parse_args()
    selected_day = date.fromisoformat(args.utc_day)
    report = (compare_campaign_fill_limit(
        args.archive, utc_day=selected_day,
        next_day_archive=args.next_day_archive,
    ) if args.compare_one_fill else run_real_trade_day(
        args.archive, utc_day=selected_day,
        next_day_archive=args.next_day_archive,
    ))
    if args.report.exists() or args.report.is_symlink():
        raise ValueError("report destination must not overwrite user-owned data")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("MIRROR_REAL_TRADES_COMPARISON_OK" if args.compare_one_fill
          else "MIRROR_REAL_TRADES_REPLAY_PROVENANCE_OK")
    if args.compare_one_fill:
        for name in ("baseline", "first_filled_trade_only"):
            item = report[name]
            print(
                f"{name}: fills={item['virtual_fills']}"
                f" closed={item['trades_closed']}"
                f" net_usdt={item['total_net_pnl_usdt']}"
                f" confirmed={item['native_confirmations']}"
                f" suppressed={item['experiment_suppressed_confirmations']}"
                f" seconds={item['runtime_seconds']}",
                flush=True,
            )
        print(f"delta_net_pnl_usdt={report['delta_net_pnl_usdt']}", flush=True)
        print(f"research_skipped_ambiguous_minutes={report['research_skipped_ambiguous_minutes']}", flush=True)
    else:
        for field in (
            "symbol", "closed_m1", "native_mirror_levels",
            "native_confirmations", "native_robot_candidates",
            "virtual_fills", "trades_closed", "total_net_pnl_usdt",
            "max_drawdown_percent", "runtime_seconds", "peak_rss_mib_linux",
        ):
            print(f"{field}={report[field]}", flush=True)


if __name__ == "__main__":
    main()
