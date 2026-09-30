"""RVL-G5 invariant: appended future candles cannot move a historical decision.

The historical decision is the frozen PONS gold window at as_of_index 199.
The same decision is replayed with 60 adversarial candles appended after the
cutoff: the production pivot finder runs on the extended frame and only pivots
already confirmed at the cutoff are admitted (a pivot needs `right` later bars),
then analyze_geometry runs with the original current_index and the extended
candles.  Freshness, locality and current-index rules are therefore unchanged;
only data after the decision bar differs, and it must not move the anchors.
"""

import inspect
import unittest

import pandas as pd

import geometry.engine as engine
from pivots import find_pivots
from wedge.analyzer import _freshness_predicate

from tests.geometry_gold import _analyze, _load_frame, geometry_identity, load_manifest


FUTURE_BARS = 60
PIVOT_RIGHT = inspect.signature(find_pivots).parameters["right"].default


def _with_adversarial_future(frame):
    # Rows 100..159 rescaled x3: a large gap, new extremes and ATR spikes.
    future = frame.iloc[100:100 + FUTURE_BARS].copy().reset_index(drop=True)
    future[["open", "high", "low", "close"]] *= 3
    if "time" in future.columns:
        step = frame["time"].iloc[-1] - frame["time"].iloc[-2]
        future["time"] = [frame["time"].iloc[-1] + step * (k + 1) for k in range(FUTURE_BARS)]
    return pd.concat([frame, future], ignore_index=True)


class AppendedFutureCandlesDoNotMoveHistoricalAnchorsTest(unittest.TestCase):
    def test_same_decision_index_with_future_candles_keeps_the_winner(self):
        case = next(
            c for c in load_manifest()["cases"]
            if c["case_id"] == "PONS-formation-fit-positive-anchor"
        )
        frame = _load_frame(case)
        cutoff = len(frame) - 1
        decision_highs, decision_lows, decided = _analyze(frame)
        self.assertEqual(
            geometry_identity(decided),
            case["expectation"]["geometry_identity"],
        )

        extended = _with_adversarial_future(frame)
        highs, lows = find_pivots(extended.copy())
        highs = [p for p in highs if p["index"] + PIVOT_RIGHT <= cutoff]
        lows = [p for p in lows if p["index"] + PIVOT_RIGHT <= cutoff]
        # Decision-time pivot knowledge is identical with or without the future.
        self.assertEqual((highs, lows), (decision_highs, decision_lows))

        replayed = engine.analyze_geometry(
            highs,
            lows,
            current_index=cutoff,
            candles=extended,
            freshness_predicate=_freshness_predicate,
        )

        self.assertIsNotNone(replayed)
        self.assertEqual(geometry_identity(replayed), geometry_identity(decided))
        self.assertEqual(replayed.upper_line, decided.upper_line)
        self.assertEqual(replayed.lower_line, decided.lower_line)
        self.assertEqual(
            replayed.pair_metrics["geometry_mode"],
            decided.pair_metrics["geometry_mode"],
        )


if __name__ == "__main__":
    unittest.main()
