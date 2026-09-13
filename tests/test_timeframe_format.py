import unittest

from timeframe_format import format_timeframe_ru


class TimeframeFormatRuTests(unittest.TestCase):
    def test_minute_intervals_render_compactly(self):
        self.assertEqual(format_timeframe_ru("1"), "1м")
        self.assertEqual(format_timeframe_ru("5"), "5м")
        self.assertEqual(format_timeframe_ru("15"), "15м")
        self.assertEqual(format_timeframe_ru("240"), "240м")

    def test_day_week_month_units(self):
        self.assertEqual(format_timeframe_ru("D"), "1д")
        self.assertEqual(format_timeframe_ru("W"), "1н")
        self.assertEqual(format_timeframe_ru("M"), "1мес")

    def test_is_case_insensitive_and_strips_whitespace(self):
        self.assertEqual(format_timeframe_ru(" d "), "1д")

    def test_unrecognized_values_are_returned_unchanged(self):
        self.assertEqual(format_timeframe_ru("weird"), "WEIRD")


if __name__ == "__main__":
    unittest.main()
