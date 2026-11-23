"""No-network fail-closed tests for REST/WS L1000 research provenance."""
import copy
import unittest

from terminal.market_data.research_l2_rest_anchor import (
    align_rest_to_observed_l1000,
)


def rest():
    return {
        "retCode": 0,
        "result": {
            "s": "BTCUSDT", "u": 50, "seq": 500,
            "cts": 1199, "ts": 1200,
            "b": [["100", "2"], ["99", "3"]],
            "a": [["101", "4"], ["102", "5"]],
        },
    }


def frame(u, seq, cts, ts, received):
    return (
        received,
        {"topic": "orderbook.1000.BTCUSDT", "type": "delta",
         "ts": ts, "cts": cts,
         "data": {"s": "BTCUSDT", "u": u, "seq": seq,
                  "b": [["100", "2"]], "a": [["101", "4"]]}},
    )


def frames():
    return (
        frame(49, 499, 1140, 1145, 1150),
        frame(50, 500, 1199, 1200, 1220),
        frame(51, 501, 1255, 1260, 1280),
        frame(52, 502, 1310, 1320, 1350),
    )


def align(response=None, tape=None, **overrides):
    params = dict(symbol="BTCUSDT", host_known_at_ms=1000,
                  rest_requested_at_ms=1100, rest_received_at_ms=1400,
                  decision_ms=1600, max_quote_age_ms=500)
    params.update(overrides)
    return align_rest_to_observed_l1000(
        rest() if response is None else response,
        frames() if tape is None else tape,
        **params,
    )


class RestWsL2AnchorTests(unittest.TestCase):
    def test_exact_identity_with_monotone_following_delta_is_observation_only(self):
        result = align()
        self.assertIsNotNone(result)
        self.assertEqual(result.update_id, 50)
        self.assertEqual(result.cross_sequence, 500)
        self.assertEqual(result.engine_cts_ms, 1199)
        self.assertEqual(result.ws_match_received_at_ms, 1220)
        self.assertEqual(result.rest_available_at_ms, 1400)
        self.assertEqual([row[1]["data"]["u"] for row in result.following_deltas],
                         [51, 52])
        self.assertEqual(str(result.baseline_bids[0][0]), "100")
        self.assertTrue(result.identity_match_only)
        self.assertFalse(result.source_complete)
        self.assertFalse(result.trading_authorized)

    def test_missing_or_mismatched_cross_protocol_identity_is_unknown(self):
        self.assertIsNone(align(tape=frames()[2:]))
        for field, value in (("u", 51), ("seq", 501), ("cts", 1201)):
            reply = rest()
            reply["result"][field] = value
            self.assertIsNone(align(response=reply), field)
        no_matching_frame = list(frames())
        no_matching_frame[1] = frame(50, 500, 1198, 1200, 1220)
        self.assertIsNone(align(tape=tuple(no_matching_frame)))
        self.assertIsNone(align(tape=frames()[:2]))  # no two post-baseline deltas

    def test_dropped_reordered_duplicate_and_late_deltas_are_unknown(self):
        cases = [
            frames()[:2] + (frame(53, 501, 1255, 1260, 1280),) + frames()[3:],
            frames()[:2] + (frame(50, 501, 1255, 1260, 1280),) + frames()[3:],
            frames()[:2] + (frame(51, 499, 1255, 1260, 1280),) + frames()[3:],
            frames()[:2] + (frame(51, 501, 1198, 1260, 1280),) + frames()[3:],
            frames()[:2] + (frame(51, 501, 1255, 1290, 1280),) + frames()[3:],
            frames()[:2] + (frame(51, 501, 1255, 1260, 1210),) + frames()[3:],
            frames()[:2] + (frame(51, 501, 1255, 1260, 1800),) + frames()[3:],
        ]
        for case in cases:
            self.assertIsNone(align(tape=case))
        self.assertIsNone(align(tape=frames(), max_quote_age_ms=20))
        self.assertIsNone(align(tape=frames(), decision_ms=1340))

    def test_wrong_source_depth_symbol_snapshot_or_host_time_unknown(self):
        cases = []
        change = list(copy.deepcopy(frames()))
        change[2][1]["topic"] = "orderbook.200.BTCUSDT"
        cases.append(tuple(change))
        change = list(copy.deepcopy(frames()))
        change[2][1]["data"]["s"] = "ETHUSDT"
        cases.append(tuple(change))
        change = list(copy.deepcopy(frames()))
        change[1][1]["type"] = "snapshot"
        cases.append(tuple(change))
        for case in cases:
            self.assertIsNone(align(tape=case))
        self.assertIsNone(align(host_known_at_ms=1200))
        self.assertIsNone(align(rest_requested_at_ms=1400))
        self.assertIsNone(align(rest_received_at_ms=1700))

    def test_untrusted_rest_payloads_fail_closed(self):
        for field, value in (("retCode", True), ("retCode", 1)):
            reply = rest()
            reply[field] = value
            self.assertIsNone(align(response=reply))
        for field, value in (
            ("s", "ETHUSDT"), ("u", True), ("u", 0),
            ("seq", "500"), ("cts", None), ("ts", 3000),
            ("b", []), ("b", [["100", "2"], ["100", "3"]]),
            ("b", [["99", "2"], ["100", "3"]]),
            ("a", [["100", "4"]]),
            ("a", [["101", "-1"]]),
            ("a", [["101", "NaN"]]),
        ):
            reply = rest()
            reply["result"][field] = value
            self.assertIsNone(align(response=reply), field)

    def test_bounds_and_cross_protocol_staleness_unknown(self):
        self.assertIsNone(align(tape=()))
        self.assertIsNone(align(tape=frames()*300))
        reply = rest()
        reply["result"]["ts"] = 1010  # stale beyond max quote age
        self.assertIsNone(align(response=reply))
        duplicate = frames() + (frames()[1],)
        self.assertIsNone(align(tape=duplicate))


if __name__ == "__main__":
    unittest.main()
