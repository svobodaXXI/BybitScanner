"""G2a research evidence: source pivots, closed-bar causality, no integration."""
import copy
import unittest
from unittest.mock import patch

import pandas as pd

from geometry.pre_pattern import (
    collect_impulse_terminal_evidence,
    detect_pre_pattern_impulse,
)
from pivots import find_pivots


class ImpulseTerminalEvidenceTests(unittest.TestCase):
    def candles(self, timeframe=1, down=False):
        close = [104, 102, 101, 107, 112, 115, 119, 117, 115, 114, 116, 113, 112]
        if down:
            close = [220 - value for value in close]
        return pd.DataFrame({
            "time": [1_700_000_000_000 + i * timeframe * 60_000 for i in range(len(close))],
            "open": close, "high": [value + 1 for value in close],
            "low": [value - 1 for value in close], "close": close,
        })

    def scan(self, frame, right=2):
        return find_pivots(frame.copy(deep=True), left=1, right=right, min_change=0)

    def evidence(self, frame, highs=None, lows=None, **overrides):
        if highs is None or lows is None:
            highs, lows = self.scan(frame)
        options = dict(start_index=6, as_of_index=8, right=2)
        options.update(overrides)
        return collect_impulse_terminal_evidence(frame, highs, lows, **options)

    def point(self, frame, index, side):
        return {"index": index, "price": float(frame.iloc[index][side]), "type": side}

    def candidate(self, evidence, index, side, pending=False):
        key = "pending_candidates" if pending else "candidates"
        return next(p for p in evidence[key] if p["index"] == index and p["side"] == side)

    def test_terminal_high_after_up_swing_from_existing_scanner_pivots(self):
        frame = self.candles()
        result = self.evidence(frame)
        self.assertEqual(result["status"], "EVIDENCE_AVAILABLE")
        terminal = self.candidate(result, 6, "HIGH")
        self.assertEqual(terminal["price"], 120)
        self.assertEqual(terminal["time_ms"], frame.iloc[6]["time"])
        self.assertEqual(terminal["previous_opposing_index"], 2)
        self.assertEqual(terminal["previous_opposing_time_ms"], frame.iloc[2]["time"])
        self.assertEqual(terminal["direction"], "UP")
        self.assertAlmostEqual(terminal["displacement_percent"], 20)
        self.assertEqual(terminal["duration_bars"], 4)
        self.assertEqual(terminal["confirmed_at_index"], 8)
        self.assertEqual(terminal["confirmed_at_time_ms"], frame.iloc[8]["time"])
        self.assertEqual(result["window"]["end_index"], 8)

    def test_terminal_low_after_down_swing_and_later_low_does_not_replace_it(self):
        frame = self.candles(down=True)
        result = self.evidence(frame)
        terminal = self.candidate(result, 6, "LOW")
        self.assertEqual(result["status"], "EVIDENCE_AVAILABLE")
        self.assertEqual(terminal["direction"], "DOWN")
        self.assertAlmostEqual(terminal["displacement_percent"], -100 / 6)
        self.assertEqual(terminal["duration_bars"], 4)
        highs, lows = self.scan(frame)
        lows.append({"index": 12, "price": 0.01, "type": "low"})
        self.assertEqual(result, self.evidence(frame, highs, lows))
        self.assertNotIn("subtype", result)
        self.assertNotIn("selected_start_index", result)

    def test_full_history_membership_is_invisible_until_confirmation(self):
        frame = self.candles()
        for right in (1, 2, 3):
            with self.subTest(right=right):
                full_highs, full_lows = self.scan(frame, right=right)
                before_index = 6 + right - 1
                before_frame = frame.iloc[:before_index + 1].copy()
                before_highs, before_lows = self.scan(before_frame, right=right)
                before_full = self.evidence(
                    frame, full_highs, full_lows, right=right, as_of_index=before_index)
                before_truncated = self.evidence(
                    before_frame, before_highs, before_lows,
                    right=right, as_of_index=before_index)
                self.assertEqual(before_full, before_truncated)
                self.assertEqual(before_full["status"], "INSUFFICIENT_HISTORY")
                self.assertFalse(any(p["index"] == 6 for p in before_full["candidates"]))
                self.assertEqual(before_full["pending_candidates"], [])

                confirmed_index = 6 + right
                confirmed_frame = frame.iloc[:confirmed_index + 1].copy()
                confirmed_highs, confirmed_lows = self.scan(confirmed_frame, right=right)
                after_full = self.evidence(
                    frame, full_highs, full_lows,
                    right=right, as_of_index=confirmed_index)
                after_truncated = self.evidence(
                    confirmed_frame, confirmed_highs, confirmed_lows,
                    right=right, as_of_index=confirmed_index)
                self.assertEqual(after_full, after_truncated)
                self.assertEqual(after_full["status"], "EVIDENCE_AVAILABLE")
                self.assertEqual(self.candidate(after_full, 6, "HIGH")["confirmed_at_time_ms"],
                                 frame.iloc[6 + right]["time"])

    def test_future_ohlc_and_future_pivot_prices_are_never_used(self):
        frame = self.candles()
        highs, lows = self.scan(frame)
        for as_of in (7, 8):
            with self.subTest(as_of=as_of):
                closed = frame.iloc[:as_of + 1].copy()
                expected = self.evidence(closed, highs, lows, as_of_index=as_of)
                poisoned = frame.astype(object)
                poisoned.loc[as_of + 1:, :] = "FUTURE MUST NOT BE READ"
                future_highs = highs + [{"index": 999, "price": object(), "type": "bad"}]
                self.assertEqual(expected, self.evidence(
                    poisoned, future_highs, lows, as_of_index=as_of))

    def test_proposed_start_bounds_terminals_even_after_more_bars_close(self):
        frame = self.candles()
        original = self.evidence(frame)
        later = self.evidence(frame, as_of_index=12)
        self.assertEqual(original["candidates"], later["candidates"])
        self.assertEqual(original["endpoint_context"], later["endpoint_context"])
        self.assertLessEqual(later["window"]["end_index"], 6 + 2)

    def test_insufficient_history_never_uses_a_candle_as_swing_origin(self):
        frame = self.candles()
        for kwargs in ({"lookback": 3}, {"highs": [self.point(frame, 6, "high")], "lows": []}):
            with self.subTest(kwargs=kwargs):
                result = self.evidence(frame, **kwargs)
                self.assertEqual(result["status"], "INSUFFICIENT_HISTORY")
                terminal = self.candidate(result, 6, "HIGH")
                self.assertIsNone(terminal["previous_opposing_index"])
                self.assertIsNone(terminal["displacement_percent"])
                self.assertIsNone(terminal["duration_bars"])
                self.assertEqual(terminal["direction"], "UNKNOWN")
        result = self.evidence(frame, [], [])
        self.assertEqual(result["status"], "INSUFFICIENT_HISTORY")

    def test_twenty_bar_window_is_explicit_and_can_be_extended_for_research(self):
        frame = pd.concat([self.candles()] * 3, ignore_index=True)
        frame["time"] = 1_700_000_000_000 + frame.index * 60_000
        highs = [self.point(frame, 30, "high")]
        lows = [self.point(frame, 2, "low")]
        result = self.evidence(frame, highs, lows, start_index=30, as_of_index=32)
        self.assertEqual(result["window"]["start_index"], 10)
        self.assertEqual(result["window"]["start_time_ms"], frame.iloc[10]["time"])
        self.assertEqual(result["status"], "INSUFFICIENT_HISTORY")
        extended = self.evidence(frame, highs, lows, start_index=30, as_of_index=32, lookback=30)
        self.assertEqual(extended["status"], "EVIDENCE_AVAILABLE")
        self.assertEqual(extended["candidates"][-1]["previous_opposing_index"], 2)

    def test_neighboring_high_and_low_alternatives_are_kept_ambiguous(self):
        frame = self.candles()
        highs = [self.point(frame, 6, "high")]
        lows = [self.point(frame, 2, "low"), self.point(frame, 9, "low")]
        result = self.evidence(frame, highs, lows, start_index=9, as_of_index=11)
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertEqual([(p["index"], p["direction"]) for p in result["candidates"]],
                         [(2, "UNKNOWN"), (6, "UP"), (9, "DOWN")])

    def test_flat_swing_has_measurements_but_no_impulse_direction(self):
        frame = self.candles()
        frame[["open", "high", "low", "close"]] = 100
        result = self.evidence(frame, [self.point(frame, 6, "high")],
                               [self.point(frame, 2, "low")])
        terminal = self.candidate(result, 6, "HIGH")
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertEqual(terminal["displacement_percent"], 0)
        self.assertEqual(terminal["direction"], "UNKNOWN")

    def test_same_candle_high_low_has_no_invented_intrabar_order(self):
        frame = self.candles()
        highs = [self.point(frame, 6, "high")]
        lows = [self.point(frame, 2, "low"), self.point(frame, 6, "low")]
        result = self.evidence(frame, highs, lows)
        self.assertEqual(result["status"], "AMBIGUOUS")
        for candidate in result["candidates"]:
            if candidate["index"] == 6:
                self.assertEqual(candidate["direction"], "UNKNOWN")
                self.assertNotEqual(candidate["previous_opposing_index"], 6)

    def test_small_displacement_is_measured_without_a_strength_threshold(self):
        frame = self.candles()
        frame[["open", "high", "low", "close"]] = 100.0
        frame.loc[6, "high"] = 100.0000001
        result = self.evidence(frame, [self.point(frame, 6, "high")],
                               [self.point(frame, 2, "low")])
        terminal = self.candidate(result, 6, "HIGH")
        self.assertEqual(result["status"], "EVIDENCE_AVAILABLE")
        self.assertEqual(terminal["direction"], "UP")
        self.assertGreater(terminal["displacement_percent"], 0)

    def test_shortlist_is_bounded_deterministic_and_deduplicates_input(self):
        frame = self.candles()
        highs = [self.point(frame, i, "high") for i in (3, 6, 10)]
        lows = [self.point(frame, i, "low") for i in (2, 5, 9)]
        result = self.evidence(frame, highs, lows, start_index=10, as_of_index=12,
                               max_candidates=3)
        self.assertEqual([p["index"] for p in result["candidates"]], [6, 9, 10])
        self.assertTrue(result["candidates_truncated"])
        self.assertEqual(result["status"], "AMBIGUOUS")
        shuffled = self.evidence(frame, list(reversed(highs)) + highs, list(reversed(lows)),
                                 start_index=10, as_of_index=12, max_candidates=3)
        self.assertEqual(result, shuffled)

    def test_one_and_five_minute_use_identical_source_indices(self):
        results = [self.evidence(self.candles(tf)) for tf in (1, 5)]
        for key in ("index", "confirmed_at_index", "previous_opposing_index",
                    "displacement_percent", "duration_bars", "direction"):
            self.assertEqual(results[0]["candidates"][-1][key], results[1]["candidates"][-1][key])
        for result, minutes in zip(results, (1, 5)):
            terminal = result["candidates"][-1]
            self.assertEqual(terminal["time_ms"] - terminal["previous_opposing_time_ms"],
                             4 * minutes * 60_000)
            self.assertEqual(terminal["confirmed_at_time_ms"] - terminal["time_ms"],
                             2 * minutes * 60_000)

    def test_invalid_evidence_is_explicit(self):
        invalid_frame = collect_impulse_terminal_evidence(123, [], [], 0, as_of_index=0, right=2)
        self.assertEqual(invalid_frame["status"], "INVALID_INPUT")
        for column, value in (("time", float("nan")), ("time", -1),
                              ("high", float("inf")), ("low", -1), ("open", 9999)):
            with self.subTest(column=column, value=value):
                frame = self.candles().astype(float)
                frame.loc[4, column] = value
                self.assertEqual(self.evidence(frame, [], [])["status"], "INVALID_INPUT")
        frame = self.candles()
        frame.loc[4, "time"] = frame.loc[3, "time"]
        self.assertEqual(self.evidence(frame, [], [])["status"], "INVALID_INPUT")
        frame = self.candles()
        wrong_price = {"index": 6, "price": 999, "type": "high"}
        self.assertEqual(self.evidence(frame, [wrong_price], [])["status"], "INVALID_INPUT")
        for overrides in ({"right": -1}, {"right": 1.5}, {"as_of_index": 100},
                          {"as_of_index": 5}, {"lookback": 0}, {"max_candidates": 0},
                          {"start_index": True}):
            self.assertEqual(self.evidence(frame, **overrides)["status"], "INVALID_INPUT")

    def test_edges_are_bounded_and_missing_data_is_not_fabricated(self):
        frame = self.candles()
        first = self.evidence(frame, [], [], start_index=0, as_of_index=0)
        self.assertEqual(first["status"], "INSUFFICIENT_HISTORY")
        self.assertEqual(first["window"]["start_index"], 0)
        self.assertEqual(first["window"]["end_index"], 0)
        self.assertIsNone(first["endpoint_context"])
        last = self.evidence(frame, [self.point(frame, 12, "high")], [],
                             start_index=12, as_of_index=12)
        self.assertEqual(last["status"], "INSUFFICIENT_HISTORY")
        self.assertEqual(last["window"]["end_index"], 12)
        self.assertEqual(last["candidates"], [])
        self.assertEqual(last["pending_candidates"], [])
        for absent in (None, frame.iloc[:0]):
            result = collect_impulse_terminal_evidence(absent, [], [], 0, as_of_index=0, right=2)
            self.assertEqual(result["status"], "INSUFFICIENT_HISTORY")

    def test_purity_reuses_legacy_endpoint_context_without_rerunning_pivots(self):
        frame = self.candles()
        highs, lows = self.scan(frame)
        before_frame, before_pivots = frame.copy(deep=True), copy.deepcopy((highs, lows))
        with patch("geometry.pre_pattern.detect_pre_pattern_impulse",
                   wraps=detect_pre_pattern_impulse) as legacy, \
             patch("pivots.find_pivots", side_effect=AssertionError("must reuse Scanner pivots")):
            result = self.evidence(frame, highs, lows)
        legacy.assert_called_once()
        self.assertEqual(len(legacy.call_args.args[0]), 9)
        self.assertEqual(result["endpoint_context"], detect_pre_pattern_impulse(frame, 6))
        pd.testing.assert_frame_equal(frame, before_frame)
        self.assertEqual((highs, lows), before_pivots)
        result["candidates"][0]["price"] = -999
        self.assertEqual((highs, lows), before_pivots)

    def test_legacy_endpoint_behavior_and_return_shape_are_unchanged(self):
        frame = pd.DataFrame({"close": [100, 110, 120]})
        self.assertEqual(detect_pre_pattern_impulse(frame, 2), {
            "window_start": 0, "window_end": 2, "lookback": 2,
            "first_close": 100.0, "last_close": 120.0,
            "change_percent": 20.0, "direction": "UP",
        })
        frame["close"] = [100, 95, 90]
        self.assertEqual(detect_pre_pattern_impulse(frame, 2)["direction"], "DOWN")
        frame["close"] = [100, 100, 100]
        self.assertEqual(detect_pre_pattern_impulse(frame, 2)["direction"], "FLAT")
        for start in (None, 0, -1, 99):
            self.assertIsNone(detect_pre_pattern_impulse(frame, start))
        self.assertIsNone(detect_pre_pattern_impulse(None, 2))


if __name__ == "__main__":
    unittest.main()
