"""Native MIRROR Scanner on local *committed* M1/M5, with PAPER handoff OFF.

Reuse mirror_scanner's level collection, breakout tracker and reversal pattern
matcher. The local orchestrator supplies only bounded historical frames,
private temporary state and one exact-time candidate handoff to the original
Robot. No exchange calls, production candidate store or Telegram messages.
"""
from __future__ import annotations

from pathlib import Path

from geometry.naked_retest import retest_contact
from mirror_levels.levels import LevelRegistry
from mirror_levels.tracker import STATUS_UNTESTED
import mirror_scanner
from research.simulator_v2.mirror_candles import FIVE_MS, MINUTE_MS, LocalMirrorClosedCandles
from retest_calibration import causal_atr_series


class LocalMirrorAutoScanner:
    """Incremental native source and confirmation replay for one virtual run."""

    def __init__(self, source: LocalMirrorClosedCandles, *, root: Path) -> None:
        if not isinstance(source, LocalMirrorClosedCandles):
            raise TypeError("committed local M1/M5 source required")
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("absolute private Scanner root required")
        self.source = source
        self.root = root
        self._scanned_m5_close: int | None = None

    def _scan_new_m5(self, now_ms: int) -> None:
        rows = self.source.recent_closed_m5()
        if len(rows) < 2 or rows[-1]["close_time_ms"] != now_ms:
            return
        import pandas as pd

        # Exactly the production Scanner frame contract: closed prefix and
        # one explicit unclosed placeholder, NEVER a fabricated future candle.
        data = [
            {"time": row["open_time_ms"], "open": row["open"],
             "high": row["high"], "low": row["low"], "close": row["close"]}
            for row in rows
        ]
        last = rows[-1]
        data.append({
            "time": now_ms, "open": last["close"], "high": last["close"],
            "low": last["close"], "close": last["close"],
        })
        mirror_scanner.observe_mirror_levels(
            self.source.symbol, pd.DataFrame(data), timeframe="5",
            fine_candles=self.source.recent_closed_m1(),
            now_ms=now_ms, root=self.root, handoff=False,
        )
        self._scanned_m5_close = now_ms

    def _scan_closed_m1_confirmation(self, now_ms: int) -> None:
        if self._scanned_m5_close is None:
            return
        if not (self._scanned_m5_close < now_ms
                < self._scanned_m5_close + FIVE_MS):
            raise ValueError("local MIRROR fine scan requires next committed M1")
        state = mirror_scanner.load_state(self.source.symbol, "5", self.root)
        if state.get("updated_at_ms") != self._scanned_m5_close and (
            type(state.get("updated_at_ms")) is not int
            or not self._scanned_m5_close <= state["updated_at_ms"] <= now_ms
        ):
            raise ValueError("MIRROR scanner state is not current")
        fine = self.source.recent_closed_m1()
        if not fine or fine[-1]["close_time_ms"] != now_ms:
            raise ValueError("MIRROR fine confirmation lacks current closed M1")
        coarse = self.source.recent_closed_m5()
        if not coarse or coarse[-1]["close_time_ms"] != self._scanned_m5_close:
            raise ValueError("MIRROR coarse/fine scan history disagrees")
        atr = causal_atr_series(coarse, mirror_scanner.ATR_PERIOD)[-1]
        tolerance = mirror_scanner.MERGE_TOLERANCE_ATR * (atr or 0.0)
        registry = LevelRegistry.from_dict(state["registry"])
        entries = state.setdefault("standalone_entries", [])
        mutated = False
        for level_id, record in state["records"].items():
            level = registry.levels.get(level_id)
            if (level is None or record.get("candidate") is not True
                    or record.get("lifecycle") != mirror_scanner.LIFECYCLE_TRACKING
                    or record.get("status") != STATUS_UNTESTED):
                continue
            breakout = (record.get("naked_retest") or {}).get("breakout")
            if not isinstance(breakout, dict):
                continue
            # The current incomplete M5 must not hide an already proven
            # post-breakout touch. Use the original contact rule with the
            # latest causally known M5 ATR zone; ambiguous touch also blocks.
            partial = (
                row for row in fine
                if self._scanned_m5_close < row["close_time_ms"] <= now_ms
            )
            if any(retest_contact(
                level.boundary, breakout["direction"], row,
                tolerance=tolerance,
            ) is not None for row in partial):
                continue
            before = dict(record.get("entry_cursors") or {})
            found = mirror_scanner._standalone_confirmations(
                level, record, {"1": fine}, now_ms,
            )
            mutated = mutated or before != record.get("entry_cursors")
            for item in found:
                if (item["timeframe"] != "1"
                        or item["confirmation_close_ms"] != now_ms
                        or item["terms"] is None):
                    continue
                entry_id = f"{level_id}@1@{now_ms}"
                if not any(e.get("entry_id") == entry_id for e in entries):
                    entries.append({
                        "entry_id": entry_id, "terms": item["terms"],
                        "handoff": "PENDING", "candidate_id": None,
                    })
                    mutated = True
        if mutated:
            state["updated_at_ms"] = now_ms
            mirror_scanner.save_state(state, root=self.root)

    def observe_committed(self, *, now_ms: int) -> tuple[str, ...]:
        """Return only newly proven entry IDs at this exact committed close."""
        if (type(now_ms) is not int
                or self.source.last_close_ms != now_ms):
            raise ValueError("automatic MIRROR scan requires committed M1")
        if now_ms % FIVE_MS == 0:
            self._scan_new_m5(now_ms)
        else:
            self._scan_closed_m1_confirmation(now_ms)
        if self._scanned_m5_close is None:
            return ()
        state = mirror_scanner.load_state(self.source.symbol, "5", self.root)
        eligible = []
        for entry in state.get("standalone_entries") or ():
            if (entry.get("handoff") != "PENDING"
                    or not isinstance(entry.get("terms"), dict)):
                continue
            confirmation = entry["terms"].get("confirmation")
            if (not isinstance(confirmation, dict)
                    or confirmation.get("close_time_ms") != now_ms):
                continue
            if mirror_scanner.verified_standalone_snapshot(
                self.source.symbol, state, entry,
            ) is not None:
                eligible.append(entry["entry_id"])
        return tuple(sorted(set(eligible)))
