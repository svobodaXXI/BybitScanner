import sys
import types
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

# analyze_symbol imports local config/Bybit/chart modules; stub them only for
# the import and restore the module registry immediately afterward.
_STUBS = {
    "config": types.SimpleNamespace(
        TELEGRAM_TOKEN="test-token", TELEGRAM_CHAT_ID="42", TELEGRAM_CHAT_IDS=("42",),
        TELEGRAM_ENABLED=True, TELEGRAM_TEST_MODE=False, TIMEFRAME="5", CANDLE_LIMIT=200,
        MODE="hunter", MIN_SCORE=30, MAX_SYMBOLS=None, BYBIT_CATEGORY="linear",
    ),
    "bybit_api": types.SimpleNamespace(
        get_candles=lambda *args, **kwargs: None, get_symbols=lambda *args, **kwargs: [],
    ),
    "analyzer.charts": types.SimpleNamespace(create_chart=lambda *args, **kwargs: None),
}
_previous = {name: sys.modules.get(name) for name in _STUBS}
for _name, _stub in _STUBS.items():
    module = types.ModuleType(_name)
    module.__dict__.update(vars(_stub))
    sys.modules[_name] = module
try:
    import analyzer.core as analyzer_core
finally:
    for _name, _module in _previous.items():
        if _module is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _module

from scanner_geometry_cursor import (  # noqa: E402
    ScannerGeometryCursorError,
    build_scanner_geometry_cursor_anchor,
    project_frozen_geometry_to_robot_1m,
)

SOURCE_TIME_MS = 1_800_000
GEOMETRY = {
    "upper_line": {"slope": -5.0, "intercept": 1100.0},
    "lower_line": {"slope": -2.5, "intercept": 600.0},
    "apex": {"index": 220.5, "price": 0.0, "valid_intersection": True},
    "current_index": 199,
    "pair_metrics": {"reference_price": 100.0, "start_width": 20.0},
}


class AnalyzerCoreRobotHandoffTests(unittest.TestCase):
    def _analyze(self, *, timeframe=None, extra_patches=()):
        candles = MagicMock()
        candles.__len__.return_value = 200
        candles.iloc.__getitem__.return_value = {"time": SOURCE_TIME_MS}
        with ExitStack() as stack:
            load = stack.enter_context(
                patch.object(analyzer_core, "load_candles", return_value=candles))
            for target, value in (
                ("find_pivots", ([1, 2, 3], [1, 2, 3])),
                ("analyze_wedge", {"pattern": "Falling Wedge", "geometry": dict(GEOMETRY)}),
                ("confirm_signal", {"confirmed": False, "breakout": False}),
                ("calculate_final_score", 80),
                ("evaluate_quality", {"quality": "Elite Setup"}),
                ("evaluate_signal", {"approved": True, "reason": "test"}),
                ("create_signal_payload", {}),
                ("create_chart", None),
                ("create_report", None),
            ):
                stack.enter_context(patch.object(analyzer_core, target, return_value=value))
            stack.enter_context(patch.object(analyzer_core, "TIMEFRAME", "5"))
            for extra in extra_patches:
                stack.enter_context(extra)
            kwargs = {} if timeframe is None else {"timeframe": timeframe}
            result = analyzer_core.analyze_symbol("BTCUSDT", **kwargs)["result"]
        return result, load

    def _assert_robot_ready(self, result, source_timeframe):
        self.assertIs(result["scanner_observational_only"], False)
        self.assertEqual(result["scanner_source_timeframe"], source_timeframe)
        self.assertEqual(result["scanner_source_candle_time_ms"], SOURCE_TIME_MS)
        self.assertEqual(
            result["robot_geometry"],
            project_frozen_geometry_to_robot_1m(GEOMETRY, source_timeframe=source_timeframe),
        )
        self.assertEqual(
            result["scanner_geometry_cursor"],
            build_scanner_geometry_cursor_anchor(
                geometry_index=199, source_candle_time_ms=SOURCE_TIME_MS, timeframe="1",
            ),
        )
        self.assertIs(result["robot_handoff_ready"], True)
        self.assertNotIn("robot_handoff_error", result)

    def test_explicit_1m_wedge_is_robot_ready_with_geometry_and_cursor(self):
        result, load = self._analyze(timeframe="1")
        self.assertEqual(load.call_args.args[1], "1")
        self._assert_robot_ready(result, "1")
        self.assertEqual(result["geometry"], GEOMETRY)  # native geometry is untouched

    def test_robot_evidence_failure_stays_fail_closed(self):
        for target, error in (
            ("project_frozen_geometry_to_robot_1m", ScannerGeometryCursorError("projection")),
            ("build_scanner_geometry_cursor_anchor", ScannerGeometryCursorError("cursor")),
            ("project_frozen_geometry_to_robot_1m", KeyError("upper_line")),
        ):
            with self.subTest(target=target, error=error):
                result, _load = self._analyze(
                    timeframe="1",
                    extra_patches=(patch.object(analyzer_core, target, side_effect=error),),
                )
                self.assertIs(result["robot_handoff_ready"], False)
                self.assertEqual(result["robot_handoff_error"], str(error))
                self.assertIs(result["scanner_observational_only"], False)

    def test_5m_handoff_is_unchanged(self):
        for timeframe in (None, "5"):
            with self.subTest(timeframe=timeframe):
                result, load = self._analyze(timeframe=timeframe)
                self.assertEqual(load.call_args.args[1], "5")
                self._assert_robot_ready(result, "5")


if __name__ == "__main__":
    unittest.main()
