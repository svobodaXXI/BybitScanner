"""Opt-in two-closed-M1 Impulse Scanner producer using the EXISTING hub.

No second WebSocket, order executor, DB writer, or standalone Robot. Only the
canonical Scanner candidate handoff and PAPER Autopilot observer are called.
The Bybit publicTrade sequence is NOT gap-free. Eligibility needs two windows
whose exact REST execution IDs + facts AND independent exchange M1
OHLC/volume/turnover totals agree. If full brackets/trades are unavailable,
no candidate is emitted. Source proof is *bounded*, not perpetual WS health.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from decimal import Decimal
from typing import Callable, Mapping

from robot_entry_flow_evidence import (
    TakerPrint, aggregate_taker_prints, compare_flow_windows,
    recognize_impulse_signal, permits_paper_entry,
)
from robot_candidate_store import RobotCandidateNotFound, load_candidate
from pattern_robot_integration import (
    prepare_robot_handoff, robot_candidate_observer,
)
from terminal.market_data.impulse_observation import (
    ObservedPrint, audit_closed_m1_triple_parity,
    audit_closed_m1_receipt_cutoff,
)
import robot_impulse


LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.bybit.com"
SYMBOLS_ENV = "BYBITSCANNER_ROBOT_IMPULSE_SYMBOLS"
MAX_SYMBOLS = 4
MIN_FINALIZE_DELAY_MS = 2_000
RETRY_INTERVAL_MS = 8_000


def configured_symbols(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    values = os.environ if environ is None else environ
    if not robot_impulse.paper_enabled(values):
        return ()
    raw = values.get(SYMBOLS_ENV, "").strip()
    if not raw:
        return ()
    symbols = tuple(x.strip() for x in raw.split(","))
    if (len(symbols) > MAX_SYMBOLS or len(symbols) != len(set(symbols))
            or any(not x.isascii() or not x.isalnum() or
                   x != x.upper() or not x.endswith("USDT")
                   for x in symbols)):
        raise ValueError("Impulse PAPER symbols must be 1..4 unique linear USDT names")
    return symbols


def certified_snapshot(
    observation: object,
    recent_response: object,
    previous_kline: object,
    current_kline: object,
    *, closed_at_ms: int, decision_ms: int,
) -> dict | None:
    """Pure, bounded Scanner candidate; NULL unless every independent fence holds.

    The caller must obtain both REST endpoints with verified Bybit TLS in the
    same pass, after closure. This code never turns a diagnostic 'timely WS
    observed only' into a completeness claim without full independent facts.
    """
    if (type(closed_at_ms) is not int or closed_at_ms <= 120_000
            or closed_at_ms % 60_000 or type(decision_ms) is not int
            or not closed_at_ms <= decision_ms <=
            closed_at_ms + robot_impulse.MAX_SIGNAL_AGE_MS):
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
    if signal is None or not permits_paper_entry(signal.direction, transition, oi_mode="OFF"):
        return None

    evidence = "\n".join(
        f"{p.trade_id}|{p.timestamp_ms}|{p.side}|{p.price}|{p.quantity}"
        for p in (*previous_raw, *current_raw)
    )
    digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
    return {
        "pattern": robot_impulse.PATTERN,
        "symbol": symbol,
        "timeframe": "1",
        "scanner_source_timeframe": "1",
        "robot_handoff_ready": True,
        "scanner_observational_only": False,
        "impulse": {
            "direction": signal.direction,
            "known_at_ms": decision_ms,
            "closed_price": str(signal.closed_price),
            "structural_extreme": str(signal.structural_extreme),
        },
        "impulse_source": {
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


class ImpulsePaperScannerWorker:
    """Bounded opt-in producer reusing Bybit WS hub + normal Scanner handoff.

    HTTP reads run off the serialized PAPER owner. One immutable candidate per
    symbol/minute; no order placement and no Direct SQLite writes here.
    """

    def __init__(
        self, hub, rest_session, emit: Callable[[str], None],
        *, symbols: tuple[str, ...], clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if (not isinstance(symbols, tuple) or not symbols
                or len(symbols) > MAX_SYMBOLS):
            raise ValueError("bounded opt-in Impulse symbols required")
        self._hub = hub
        self._rest = rest_session
        self._emit = emit
        self._symbols = symbols
        self._clock = clock_ms or (lambda: int(time.time() * 1000))
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="paper-impulse-scanner", daemon=True,
        )
        self._attempted: dict[tuple[str, int], int] = {}
        self._complete: set[tuple[str, int]] = set()
        self._contexts = []

    def start(self) -> None:
        if not robot_impulse.paper_enabled():
            return
        # The hub owns the ONLY public WS. A light disconnect listener keeps
        # our four opt-in contexts from being discarded on workspace switching.
        for symbol in self._symbols:
            context = self._hub.subscribe(symbol)
            context.add_disconnect_listener("impulse-paper", lambda *_: None)
            self._contexts.append(context)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=15)
        for context in self._contexts:
            context.remove_disconnect_listener("impulse-paper")
            self._hub.discard(context)
        self._contexts.clear()
        self._rest.close()

    def _json(self, path: str, *, params: dict) -> dict:
        # Session.verify defaults to CA-verified TLS. No redirects to another
        # venue or untrusted hostname, no alternate source or mutable config.
        if getattr(self._rest, "verify", True) is False:
            raise ValueError("unverified REST TLS cannot certify Impulse")
        response = self._rest.get(
            BASE_URL + path, params=params, timeout=(3, 5),
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("Bybit REST did not provide an exact 200 response")
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Bybit REST response is invalid")
        return data

    def _candidate_id(self, symbol: str, close_ms: int) -> str:
        digest = hashlib.sha256(
            f"IMPULSE_FLOW|{symbol}|{close_ms}".encode("ascii")
        ).hexdigest()[:32]
        return "impulse-" + digest

    def once(self) -> tuple[str, ...]:
        if not robot_impulse.paper_enabled():
            return ()
        now = self._clock()
        closed = now // 60_000 * 60_000
        if now - closed < MIN_FINALIZE_DELAY_MS:
            return ()
        if now - closed > robot_impulse.MAX_SIGNAL_AGE_MS:
            return ()
        emitted: list[str] = []
        for context in tuple(self._contexts):
            if self._stop.is_set():
                break
            symbol = context.symbol
            identity = (symbol, closed)
            if identity in self._complete:
                continue
            last = self._attempted.get(identity)
            if last is not None and now - last < RETRY_INTERVAL_MS:
                continue
            self._attempted[identity] = now
            # Do not try REST on unsubscribed/reconnecting/invalid WS source.
            if (context.trades_subscription_state != "SUBSCRIBED"
                    or context.trade_bootstrap_complete is not True):
                continue
            observed = context.impulse_observation.snapshot()
            selected = observed.get("prints")
            if (not isinstance(selected, tuple) or
                    not any(closed - 120_000 <= p.timestamp_ms < closed - 60_000
                            for p in selected) or
                    not any(closed - 60_000 <= p.timestamp_ms < closed
                            for p in selected)):
                continue
            candidate_id = self._candidate_id(symbol, closed)
            try:
                load_candidate(candidate_id)
            except RobotCandidateNotFound:
                pass
            else:
                self._complete.add(identity)
                continue
            try:
                recent = self._json("/v5/market/recent-trade", params={
                    "category": "linear", "symbol": symbol, "limit": 1000,
                })
                previous = self._json("/v5/market/kline", params={
                    "category": "linear", "symbol": symbol, "interval": "1",
                    "start": closed - 120_000, "end": closed - 60_001, "limit": 1,
                })
                current = self._json("/v5/market/kline", params={
                    "category": "linear", "symbol": symbol, "interval": "1",
                    "start": closed - 60_000, "end": closed - 1, "limit": 1,
                })
                decision = self._clock()
                # If reconnect/truncation/invalid frame changed the WS
                # generation during the HTTP reads, all evidence is stale.
                if context.impulse_observation.snapshot() != observed:
                    # Stream could legitimately append new next-minute prints.
                    # Compare only strict *within-window* identity, generation,
                    # and invalid counts; ignore later prints after close.
                    latest = context.impulse_observation.snapshot()
                    if (latest.get("generation") != observed.get("generation")
                            or latest.get("invalid_frames") != observed.get("invalid_frames")
                            or any(p.timestamp_ms < closed for p in latest.get("prints", ())
                                   if p.trade_id not in {
                                       x.trade_id for x in observed.get("prints", ())
                                   })):
                        continue
                signal = certified_snapshot(
                    observed, recent, previous, current,
                    closed_at_ms=closed, decision_ms=decision,
                )
                if signal is None:
                    continue
                if not robot_impulse.paper_enabled():
                    continue
                with robot_candidate_observer(self._emit):
                    result = prepare_robot_handoff(
                        signal, timeframe="1", enabled=True,
                        candidate_id=candidate_id,
                    )
                if result.candidate_id:
                    self._complete.add(identity)
                    emitted.append(result.candidate_id)
            except Exception as error:
                LOGGER.warning(
                    "Impulse Scanner skipped %s: %s",
                    symbol, type(error).__name__,
                )
        # Keep only the current/current-previous minute in bounded memory.
        self._attempted = {k: v for k, v in self._attempted.items()
                           if k[1] >= closed - 60_000}
        self._complete = {k for k in self._complete
                          if k[1] >= closed - 60_000}
        return tuple(emitted)

    def _run(self) -> None:
        while not self._stop.wait(5):
            try:
                self.once()
            except Exception:
                LOGGER.exception("Bounded Impulse Scanner pass failed; no candidate")
