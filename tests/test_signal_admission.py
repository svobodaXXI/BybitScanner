import unittest
from unittest.mock import MagicMock, patch

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
        self.assertFalse(self.evaluate("B Setup", score=70)["approved"])
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

        prepare_mock.assert_called_once()
        update_mock.assert_called_once()
        send_mock.assert_called_once()
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
        send_mock.assert_called_once()
        self.assertTrue(send_mock.call_args.kwargs["test_mode"])
        payload = send_mock.call_args.args[0]
        self.assertFalse(payload["signal"]["approved"])


if __name__ == "__main__":
    unittest.main()
