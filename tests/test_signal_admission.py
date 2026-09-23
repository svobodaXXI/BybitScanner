import sys
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

config_stub = types.ModuleType("config")
config_stub.TELEGRAM_TOKEN = "test-token"
config_stub.TELEGRAM_CHAT_ID = "42"
config_stub.TELEGRAM_CHAT_IDS = ("42",)
config_stub.TELEGRAM_ENABLED = True
config_stub.TELEGRAM_TEST_MODE = False
config_stub.TIMEFRAME = "5"
config_stub.CANDLE_LIMIT = 200
config_stub.MODE = "hunter"
config_stub.MIN_SCORE = 30
config_stub.MAX_SYMBOLS = None
config_stub.BYBIT_CATEGORY = "linear"
sys.modules["config"] = config_stub

bybit_api_stub = types.ModuleType("bybit_api")
bybit_api_stub.get_candles = lambda *args, **kwargs: None
bybit_api_stub.get_symbols = lambda *args, **kwargs: []
sys.modules["bybit_api"] = bybit_api_stub

charts_stub = types.ModuleType("analyzer.charts")
charts_stub.create_chart = lambda *args, **kwargs: None
sys.modules["analyzer.charts"] = charts_stub

import analyzer.core as analyzer_core
import main
from signal.filter import evaluate_signal


def quality(name):
    return {"quality": name}


def confirmation(*, confirmed=False, breakout=False):
    return {
        "confirmed": confirmed,
        "breakout": breakout,
    }


class SignalFilterAdmissionTests(unittest.TestCase):
    def evaluate(
        self,
        quality_name,
        score=80,
        *,
        mode="hunter",
        min_score=60,
        confirmed=False,
        breakout=False,
    ):
        return evaluate_signal(
            quality(quality_name),
            score,
            confirmation(
                confirmed=confirmed,
                breakout=breakout,
            ),
            mode=mode,
            min_score=min_score,
        )

    def test_hunter_accepts_elite_canonical_and_legacy_alias(self):
        self.assertTrue(self.evaluate("Elite Setup")["approved"])
        self.assertTrue(self.evaluate("A+ Setup")["approved"])

    def test_hunter_quality_boundaries(self):
        self.assertTrue(self.evaluate("A Setup", score=75)["approved"])
        self.assertTrue(self.evaluate("B Setup", score=70)["approved"])
        self.assertFalse(self.evaluate("Watch", score=70)["approved"])
        self.assertFalse(self.evaluate("Invalid", score=90)["approved"])

    def test_min_score_is_inclusive_absolute_threshold(self):
        self.assertTrue(
            self.evaluate(
                "Elite Setup",
                score=60,
                min_score=60,
            )["approved"]
        )
        self.assertFalse(
            self.evaluate(
                "Elite Setup",
                score=59,
                min_score=60,
            )["approved"]
        )

    def test_hunter_does_not_require_confirmation_universally(self):
        result = self.evaluate(
            "Elite Setup",
            confirmed=False,
            breakout=False,
        )
        self.assertTrue(result["approved"])

    def test_sniper_preserves_confirmation_boundary(self):
        self.assertTrue(
            self.evaluate(
                "A Setup",
                score=80,
                mode="sniper",
                confirmed=True,
                breakout=True,
            )["approved"]
        )
        self.assertFalse(
            self.evaluate(
                "A Setup",
                score=79,
                mode="sniper",
                confirmed=True,
                breakout=True,
            )["approved"]
        )
        self.assertFalse(
            self.evaluate(
                "A Setup",
                score=80,
                mode="sniper",
                confirmed=False,
                breakout=True,
            )["approved"]
        )
        self.assertFalse(
            self.evaluate(
                "A Setup",
                score=80,
                mode="sniper",
                confirmed=True,
                breakout=False,
            )["approved"]
        )


class AnalyzerAdmissionConfigurationTests(unittest.TestCase):
    @patch.object(analyzer_core, "create_report")
    @patch.object(analyzer_core, "create_chart")
    @patch.object(analyzer_core, "create_signal_payload", return_value={})
    @patch.object(
        analyzer_core,
        "evaluate_signal",
        return_value={"approved": True, "reason": "test"},
    )
    @patch.object(
        analyzer_core,
        "evaluate_quality",
        return_value={"quality": "Elite Setup"},
    )
    @patch.object(analyzer_core, "calculate_final_score", return_value=80)
    @patch.object(
        analyzer_core,
        "confirm_signal",
        return_value={"confirmed": False, "breakout": False},
    )
    @patch.object(
        analyzer_core,
        "analyze_wedge",
        return_value={"pattern": "Falling Wedge", "geometry": object()},
    )
    @patch.object(analyzer_core, "find_pivots", return_value=([1, 2, 3], [1, 2, 3]))
    @patch.object(analyzer_core, "load_candles")
    def test_analyzer_passes_config_mode_and_min_score(
        self,
        load_candles_mock,
        _find_pivots_mock,
        _analyze_wedge_mock,
        _confirm_signal_mock,
        _calculate_score_mock,
        _evaluate_quality_mock,
        evaluate_signal_mock,
        _create_payload_mock,
        _create_chart_mock,
        _create_report_mock,
    ):
        candles = MagicMock()
        candles.__len__.return_value = 10
        load_candles_mock.return_value = candles

        with patch.object(analyzer_core, "MODE", "sniper"), \
                patch.object(analyzer_core, "MIN_SCORE", 67):
            analyzer_core.analyze_symbol("BTCUSDT")

        evaluate_signal_mock.assert_called_once_with(
            {"quality": "Elite Setup"},
            80,
            {"confirmed": False, "breakout": False},
            mode="sniper",
            min_score=67,
        )


class AnalyzerRobotHandoffTests(unittest.TestCase):
    @patch.object(analyzer_core, "create_report")
    @patch.object(analyzer_core, "create_chart")
    @patch.object(analyzer_core, "create_signal_payload", return_value={})
    @patch.object(
        analyzer_core,
        "evaluate_signal",
        return_value={"approved": True, "reason": "test"},
    )
    @patch.object(
        analyzer_core,
        "evaluate_quality",
        return_value={"quality": "Elite Setup"},
    )
    @patch.object(analyzer_core, "calculate_final_score", return_value=80)
    @patch.object(
        analyzer_core,
        "confirm_signal",
        return_value={"confirmed": False, "breakout": False},
    )
    @patch.object(analyzer_core, "find_pivots", return_value=([1, 2, 3], [1, 2, 3]))
    @patch.object(analyzer_core, "load_candles")
    def test_5m_scanner_emits_proven_robot_1m_geometry(
        self,
        load_candles_mock,
        _find_pivots_mock,
        _confirm_signal_mock,
        _calculate_score_mock,
        _evaluate_quality_mock,
        _evaluate_signal_mock,
        _create_payload_mock,
        _create_chart_mock,
        _create_report_mock,
    ):
        candles = MagicMock()
        candles.__len__.return_value = 200
        candles.iloc.__getitem__.return_value = {"time": 1_800_000}
        load_candles_mock.return_value = candles

        geometry = {
            "upper_line": {"slope": -5.0, "intercept": 1100.0},
            "lower_line": {"slope": -2.5, "intercept": 600.0},
            "apex": {
                "index": 220.5,
                "price": 0.0,
                "valid_intersection": True,
            },
            "current_index": 199,
            "pair_metrics": {
                "reference_price": 100.0,
                "start_width": 20.0,
            },
        }

        with patch.object(
            analyzer_core,
            "analyze_wedge",
            return_value={"pattern": "Falling Wedge", "geometry": geometry},
        ), patch.object(analyzer_core, "TIMEFRAME", "5"):
            result = analyzer_core.analyze_symbol("BTCUSDT")["result"]

        self.assertTrue(result["robot_handoff_ready"])
        self.assertEqual(result["scanner_source_timeframe"], "5")
        self.assertEqual(result["scanner_geometry_cursor"]["timeframe"], "1")
        self.assertEqual(result["scanner_geometry_cursor"]["geometry_index"], 199)
        self.assertEqual(result["robot_geometry"]["upper_line"]["slope"], -1.0)
        self.assertEqual(result["robot_geometry"]["apex"]["index"], 306.5)
        self.assertEqual(result["geometry"]["upper_line"]["slope"], -5.0)


class TimeframeSignalMemoryTests(unittest.TestCase):
    def test_interval_and_formation_identity_are_independent(self):
        import signal_memory

        history = {}
        base = {
            "symbol": "BTCUSDT", "pattern": "Falling Wedge",
            "direction": "LONG", "score": 80,
        }
        with patch.object(signal_memory, "load_memory", side_effect=lambda: dict(history)), \
                patch.object(signal_memory, "save_memory", side_effect=lambda value: history.update(value)):
            five = {**base, "timeframe": "5", "formation_id": "100:200"}
            one = {**base, "timeframe": "1", "formation_id": "100:200"}
            next_five = {**five, "formation_id": "300:400"}
            self.assertEqual(signal_memory.update_signal(five), "NEW")
            self.assertEqual(signal_memory.update_signal(one), "NEW")
            self.assertEqual(signal_memory.update_signal(five), "STABLE")
            self.assertEqual(signal_memory.update_signal(next_five), "NEW")
        self.assertEqual(len(history), 3)


class MainAdmissionGateTests(unittest.TestCase):
    def run_main(self, approved, *, test_mode=False):
        analysis = {
            "pattern": "Falling Wedge",
            "final_score": 80,
            "signal": {
                "approved": approved,
                "reason": "test",
            },
        }

        patches = (
            patch.object(main, "get_symbols", return_value=["BTCUSDT"]),
            patch.object(
                main,
                "analyze_symbol",
                return_value={"result": analysis},
            ),
            patch.object(
                main,
                "prepare_signal",
                return_value={
                    "symbol": "BTCUSDT",
                    "pattern": "Falling Wedge",
                    "direction": "LONG",
                    "score": 80,
                },
            ),
            patch.object(main, "update_signal", return_value="NEW"),
            patch.object(main, "send_signal", return_value=True),
            patch.object(main, "send_message", return_value={"ok": True}),
            patch.object(main.config, "TELEGRAM_TEST_MODE", test_mode),
        )

        mocks = []
        with patches[0] as get_symbols_mock, \
                patches[1] as analyze_mock, \
                patches[2] as prepare_mock, \
                patches[3] as update_mock, \
                patches[4] as send_mock, \
                patches[5] as finish_mock, \
                patches[6]:
            mocks.extend(
                [
                    get_symbols_mock,
                    analyze_mock,
                    prepare_mock,
                    update_mock,
                    send_mock,
                    finish_mock,
                ]
            )
            main.main()

        return mocks

    def test_approved_signal_reaches_normal_persistence_and_notification(self):
        _, _, prepare_mock, update_mock, send_mock, _ = self.run_main(True)

        self.assertEqual(prepare_mock.call_count, 2)
        self.assertEqual(update_mock.call_count, 2)
        self.assertEqual(send_mock.call_count, 2)
        self.assertNotIn("test_mode", send_mock.call_args.kwargs)

    def test_rejected_signal_skips_normal_persistence_and_telegram(self):
        _, _, prepare_mock, update_mock, send_mock, _ = self.run_main(False)

        prepare_mock.assert_not_called()
        update_mock.assert_not_called()
        send_mock.assert_not_called()

    def test_diagnostic_rejected_signal_is_not_persisted_or_approved(self):
        _, _, prepare_mock, update_mock, send_mock, _ = self.run_main(
            False,
            test_mode=True,
        )

        prepare_mock.assert_not_called()
        update_mock.assert_not_called()
        self.assertEqual(send_mock.call_count, 2)
        self.assertTrue(all(call.kwargs["test_mode"] for call in send_mock.call_args_list))
        payload = send_mock.call_args.args[0]
        self.assertFalse(payload["signal"]["approved"])

    def test_scanner_orders_both_intervals_per_symbol_and_continues_after_error(self):
        observed = []

        def analyze(symbol, *, timeframe):
            observed.append((symbol, timeframe))
            if (symbol, timeframe) == ("FIRST", "5"):
                raise RuntimeError("5m data unavailable")
            return {"result": None, "data": None}

        with patch.object(main, "get_symbols", return_value=["FIRST", "SECOND"]), \
                patch.object(main, "analyze_symbol", side_effect=analyze), \
                patch.object(main, "send_message", return_value=True):
            main.run_scan_pass()

        self.assertEqual(observed, [
            ("FIRST", "5"), ("FIRST", "1"),
            ("SECOND", "5"), ("SECOND", "1"),
        ])

    def test_scan_summary_counts_only_admission_approved_results(self):
        def analysis_result(symbol, *, timeframe):
            return {
                "result": {
                    "pattern": "Falling Wedge",
                    "final_score": 80,
                    "signal": {
                        "approved": symbol != "REJECTED",
                        "reason": "test",
                    },
                }
            }

        output = StringIO()

        with patch.object(
            main,
            "get_symbols",
            return_value=["APPROVED", "REJECTED"],
        ), patch.object(
            main,
            "analyze_symbol",
            side_effect=analysis_result,
        ), patch.object(
            main,
            "prepare_signal",
            return_value={"score": 80},
        ), patch.object(
            main,
            "update_signal",
            return_value="NEW",
        ), patch.object(
            main,
            "send_signal",
            return_value=False,
        ), patch.object(
            main,
            "send_message",
            side_effect=RuntimeError("telegram unavailable"),
        ), patch.object(
            main.config,
            "TELEGRAM_TEST_MODE",
            False,
        ), redirect_stdout(output):
            main.main()

        summary = "Найдено паттернов: 2"
        self.assertEqual(output.getvalue().count(summary), 1)


if __name__ == "__main__":
    unittest.main()
