"""RVL-G5 invariant: remote history cannot alter a local structure.

Trimming candles that lie entirely left of every anchor and of the selection
span must leave the production winner identical, only translated in index
space.  Runs the real find_pivots -> analyze_geometry path on the frozen PONS
gold window (the compact-gold positive control).
"""

import unittest

from tests.geometry_gold import _analyze, _load_frame, geometry_identity, load_manifest


REMOTE_TRIM = 50


class RemoteHistoryDoesNotAlterLocalStructureTest(unittest.TestCase):
    def test_trimming_remote_left_history_only_translates_the_winner(self):
        case = next(
            c for c in load_manifest()["cases"]
            if c["case_id"] == "PONS-formation-fit-positive-anchor"
        )
        frame = _load_frame(case)
        expected = case["expectation"]["geometry_identity"]
        self.assertEqual(geometry_identity(_analyze(frame)[2]), expected)
        # Every anchor and the whole span sit right of the trimmed prefix.
        self.assertGreater(min(expected), REMOTE_TRIM)

        trimmed = frame.iloc[REMOTE_TRIM:].reset_index(drop=True)
        winner = geometry_identity(_analyze(trimmed)[2])

        self.assertEqual(winner, [index - REMOTE_TRIM for index in expected])


if __name__ == "__main__":
    unittest.main()
