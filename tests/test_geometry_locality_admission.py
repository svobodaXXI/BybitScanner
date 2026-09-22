"""
tests.test_geometry_locality_admission

Focused regression for the Geometry locality admission gate:

- a candidate may span at most GEOMETRY_MAX_STRUCTURE_SPAN_RATIO (0.60) of
  the analysed window (current_index + 1 bars);
- the gate runs BEFORE ranking, so a non-local candidate never competes,
  whatever its mode, score or body-breach count;
- an empty pool means no geometry (no fallback to a non-local figure);
- ordering among admitted candidates is unchanged (PR #173).

TOSHI/XEC use exact 200-bar windows committed under
tests/fixtures/geometry_locality/ (pivots verified identical to the Scanner
reports of the 2026-09-21 17:46 pass). AEVO reference revision is covered by the committed formation-fit fixture.
"""

import json
import os
import unittest

import pandas as pd

import geometry.engine as engine
from pivots import find_pivots
from wedge.analyzer import _freshness_predicate

from tests.test_geometry_candidate_selection_freshness import (
    _StubGeometry,
    _select,
)


FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "geometry_locality",
)


def _window(symbol):
    with open(
        os.path.join(FIXTURE_DIR, f"{symbol}_5m_window.json"),
        encoding="utf-8",
    ) as handle:
        return pd.DataFrame(json.load(handle)["candles"])


def _analyze(frame):
    highs, lows = find_pivots(frame.copy())

    return engine.analyze_geometry(
        highs,
        lows,
        current_index=len(frame) - 1,
        candles=frame,
        freshness_predicate=_freshness_predicate,
    )


def _span(geometry):
    return geometry.end_index - geometry.start_index


class RealWindowTest(unittest.TestCase):

    def test_toshi_overlong_formation_is_not_selected(self):
        """Before: START=30 END=173 (span 143 of 200) won."""

        frame = _window("1000TOSHIUSDT")
        geometry = _analyze(frame)

        self.assertIsNotNone(geometry)
        self.assertLessEqual(_span(geometry), 120)
        self.assertNotEqual((geometry.start_index, geometry.end_index), (30, 173))
        # The remaining local figure is stale, so it is not a fresh signal.
        self.assertFalse(
            _freshness_predicate(
                geometry.start_index,
                geometry.end_index,
                (geometry.apex or {}).get("index"),
                geometry.current_index,
            )
        )

    def test_xec_has_no_local_formation_so_no_geometry(self):
        """Before: START=23 END=195 (span 172 of 200) won; every valid
        candidate spans 166..175, so nothing local exists."""

        self.assertIsNone(_analyze(_window("1000XECUSDT")))


# The old AEVO reference's lower-prefix defect and locality are exercised
# together in tests.test_geometry_formation_fit using a committed fixture.


class GateMechanicsTest(unittest.TestCase):
    # _select analyses a 200-bar window: cap = round(200 * 0.60) = 120.

    def test_non_local_candidate_loses_despite_better_key(self):
        local = _StubGeometry("local", score=1.0, body_breaches=50, start_index=0, end_index=100)
        wide = _StubGeometry(
            "wide", score=999.0, body_breaches=0, mode="CANONICAL",
            start_index=0, end_index=121, current_index=125,
        )

        self.assertIs(_select([local, wide]), local)
        self.assertIs(_select([wide, local]), local)

    def test_boundary_span_is_admitted_and_one_more_is_not(self):
        at_cap = _StubGeometry("at_cap", score=1.0, start_index=0, end_index=120, current_index=125)
        over = _StubGeometry("over", score=1.0, start_index=0, end_index=121, current_index=125)

        self.assertIs(_select([at_cap]), at_cap)
        self.assertIsNone(_select([over]))

    def test_empty_pool_returns_no_geometry_without_fallback(self):
        wide_a = _StubGeometry("a", score=10.0, start_index=0, end_index=150, current_index=155)
        wide_b = _StubGeometry("b", score=20.0, start_index=0, end_index=180, current_index=185)

        self.assertIsNone(_select([wide_a, wide_b]))

    def test_ordering_among_admitted_candidates_is_unchanged(self):
        clean = _StubGeometry("clean", score=100.0, body_breaches=0)
        noisy = _StubGeometry("noisy", score=999.0, body_breaches=9)

        self.assertIs(_select([clean, noisy]), clean)
        self.assertIs(_select([noisy, clean]), clean)


if __name__ == "__main__":
    unittest.main()
