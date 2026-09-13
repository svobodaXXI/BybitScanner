import unittest

from chart_clean import build_chart_title


class ChartTitleTests(unittest.TestCase):
    def _result(self, **overrides):
        base = {
            "pattern": "Falling Wedge",
            "timeframe": "1",
            "geometry": {},
            "detection": {"detected": True},
            "final_score": 82,
        }
        base.update(overrides)
        return base

    def test_title_header_contains_the_signal_timeframe(self):
        title = build_chart_title("1000NEIROCTOUSDT", self._result())

        header = title.splitlines()[0]
        self.assertIn("1000NEIROCTOUSDT", header)
        self.assertIn("1м", header)

    def test_title_header_uses_russian_compact_rendering_for_other_timeframes(self):
        title = build_chart_title("BTCUSDT", self._result(timeframe="5"))

        self.assertEqual(title.splitlines()[0], "BTCUSDT · 5м")

    def test_title_falls_back_to_bare_symbol_without_a_timeframe(self):
        result = self._result()
        del result["timeframe"]

        title = build_chart_title("BTCUSDT", result)

        self.assertEqual(title.splitlines()[0], "BTCUSDT")

    def test_title_falls_back_to_bare_symbol_without_a_result(self):
        self.assertEqual(build_chart_title("BTCUSDT", None), "BTCUSDT")

    def test_title_still_contains_the_existing_structure_lines(self):
        title = build_chart_title("BTCUSDT", self._result())

        self.assertIn("СТРУКТУРА: Нисходящий клин", title)
        self.assertIn("КАЧЕСТВО СТРУКТУРЫ: 82/100", title)


if __name__ == "__main__":
    unittest.main()
