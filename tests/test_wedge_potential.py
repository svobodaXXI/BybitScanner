import unittest

from wedge.potential import calculate_potential_move


class PotentialMoveTests(unittest.TestCase):
    def _geometry(self, start_width, reference_price):
        return {
            "pair_metrics": {
                "start_width": start_width,
                "reference_price": reference_price,
            }
        }

    def test_falling_wedge_is_signed_up(self):
        result = calculate_potential_move(
            "Falling Wedge", self._geometry(2.0, 100.0)
        )
        self.assertEqual(result["percent"], 2.0)
        self.assertEqual(result["signed_percent"], 2.0)
        self.assertEqual(result["direction"], "UP")

    def test_rising_wedge_is_signed_down(self):
        result = calculate_potential_move(
            "Rising Wedge", self._geometry(2.0, 100.0)
        )
        self.assertEqual(result["percent"], 2.0)
        self.assertEqual(result["signed_percent"], -2.0)
        self.assertEqual(result["direction"], "DOWN")

    def test_triangle_compression_is_symmetric_with_no_signed_value(self):
        result = calculate_potential_move(
            "Triangle Compression", self._geometry(4.28, 100.0)
        )
        self.assertEqual(result["percent"], 4.28)
        self.assertIsNone(result["signed_percent"])
        self.assertEqual(result["direction"], "SYMMETRIC")
        self.assertEqual(result["method"], "STRUCTURE_START_WIDTH")

    def test_triangle_compression_uses_the_same_start_width_formula_as_wedges(self):
        geometry = self._geometry(3.0, 150.0)
        wedge_result = calculate_potential_move("Falling Wedge", geometry)
        triangle_result = calculate_potential_move("Triangle Compression", geometry)
        self.assertEqual(wedge_result["percent"], triangle_result["percent"])

    def test_unknown_pattern_returns_none(self):
        self.assertIsNone(
            calculate_potential_move("No wedge", self._geometry(2.0, 100.0))
        )

    def test_missing_pair_metrics_returns_none(self):
        self.assertIsNone(calculate_potential_move("Triangle Compression", {}))
        self.assertIsNone(calculate_potential_move("Triangle Compression", None))


if __name__ == "__main__":
    unittest.main()
