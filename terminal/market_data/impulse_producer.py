"""Read-only two-M1 Bybit taker-flow certificate for EXISTING Robot patterns.

Pure audit helper: source certification never creates a Scanner candidate,
Robot signal, order, admission, STOP or TAKE. The caller must bind a proved
observation to an existing candidate identity before considering entry timing.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from robot_entry_flow_evidence import (
    TakerPrint, aggregate_taker_prints, compare_flow_windows,
    recognize_impulse_signal, permits_paper_entry,
)
from terminal.market_data.impulse_observation import (
    ObservedPrint, audit_closed_m1_triple_parity,
    audit_closed_m1_receipt_cutoff,
)

MAX_CERTIFICATION_DELAY_MS = 60_000

def certified_snapshot(
    observation: object,
    recent_response: object,
    previous_kline: object,
    current_kline: object,
    *, closed_at_ms: int, decision_ms: int,
    source_only: bool = False,
) -> dict | None:
    """Pure, bounded source evidence; NULL unless every independent fence holds.

    The caller must obtain both REST endpoints with verified Bybit TLS in the
    same pass, after closure. This code never turns a diagnostic 'timely WS
    observed only' into a completeness claim without full independent facts.
    """
    if type(source_only) is not bool:
        return None
    if (type(closed_at_ms) is not int or closed_at_ms <= 120_000
            or closed_at_ms % 60_000 or type(decision_ms) is not int
            or not closed_at_ms <= decision_ms <=
            closed_at_ms + MAX_CERTIFICATION_DELAY_MS):
        return None
    if (not isinstance(observation, dict)
            or type(observation.get("generation")) is not int
            or observation.get("subscription_state") == "DEGRADED"
            or observation.get("invalid_frames") != 0
            or observation.get("order_authority") is not False
            or observation.get("continuity") != "UNPROVEN"):
        return None
    symbol = observation.get("symbol")
    prints = observation.get("prints")
    if (not isinstance(symbol, str) or not symbol.endswith("USDT")
            or not isinstance(prints, tuple)):
        return None

    before = closed_at_ms - 120_000
    current = closed_at_ms - 60_000
    for start, kline in ((before, previous_kline), (current, current_kline)):
        parity = audit_closed_m1_triple_parity(
            observation, recent_response, kline,
            start_ms=start, observed_at_ms=decision_ms,
        )
        receipt = audit_closed_m1_receipt_cutoff(
            observation, start_ms=start, decision_ms=decision_ms,
        )
        if (parity.status != "EXACT_CLOSED_M1_TRIPLE_PARITY"
                or receipt.status != "TIMELY_OBSERVED_ONLY"
                or parity.matched_prints != receipt.observed_prints):
            return None

    previous_raw = tuple(
        p for p in prints if before <= p.timestamp_ms < current
    )
    current_raw = tuple(
        p for p in prints if current <= p.timestamp_ms < closed_at_ms
    )
    if not previous_raw or not current_raw:
        return None
    def convert(raw: tuple[ObservedPrint, ...]) -> tuple[TakerPrint, ...]:
        return tuple(TakerPrint(
            symbol, p.trade_id, p.timestamp_ms, p.side, p.price, p.quantity,
        ) for p in raw)

    previous_window = aggregate_taker_prints(
        convert(previous_raw), symbol=symbol,
        start_ms=before, end_ms=current,
    )
    current_window = aggregate_taker_prints(
        convert(current_raw), symbol=symbol,
        start_ms=current, end_ms=closed_at_ms,
    )
    if previous_window is None or current_window is None:
        return None
    transition = compare_flow_windows(
        previous_window, current_window, decision_ms=decision_ms,
    )
    row = current_kline["result"]["list"][0]
    candle_open, high, low, close = (Decimal(x) for x in row[1:5])
    signal = recognize_impulse_signal(
        transition, closed_at_ms=closed_at_ms,
        candle_open=candle_open, candle_close=close,
        candle_high=high, candle_low=low, decision_ms=decision_ms,
    )
    if not source_only and (
        signal is None
        or not permits_paper_entry(signal.direction, transition, oi_mode="OFF")
    ):
        return None

    evidence = "\n".join(
        f"{p.trade_id}|{p.timestamp_ms}|{p.side}|{p.price}|{p.quantity}"
        for p in (*previous_raw, *current_raw)
    )
    digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
    return {
        "symbol": symbol,
        "flow_observation": {
            "transition": transition,
            # A source-only fact is NOT a fresh directional entry signal.
            # Consumers must bind the transition to their original host.
            "direction": (signal.direction if not source_only else None),
            "known_at_ms": decision_ms,
            "closed_price": str(close),
            "structural_extreme": (
                str(signal.structural_extreme)
                if signal is not None and not source_only else None
            ),
        },
        "flow_source": {
            "kind": "BYBIT_TRIPLE_CLOSED_M1_CERTIFIED",
            "scope": "TWO_CLOSED_M1",
            "closed_at_ms": closed_at_ms,
            "decision_ms": decision_ms,
            "source_complete": True,
            "receipt_cutoff_proven": True,
            "transport_generation_proven": True,
            "generation": observation["generation"],
            "previous_start_ms": before,
            "current_start_ms": current,
            "print_count": len(previous_raw) + len(current_raw),
            "print_facts_sha256": digest,
            "oi_mode": "OFF",
        },
    }

