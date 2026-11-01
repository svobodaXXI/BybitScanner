"""Frozen exact-identity Editor source geometry regressions. No runtime."""
import json
import tempfile
import unittest
from pathlib import Path

from signal_archive import record_original_signal, load_frozen_signal_geometry
from signal_geometry_snapshot import validate_snapshot
from signal_mirror_geometry_producer import build_mirror_geometry_snapshot


def frozen_event():
    return {
        "symbol": "ALCHUSDT",
        "timeframe": "5",
        "level_id": "lvl-source-1",
        "candles": [
            {"open_time_ms": 1000, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0},
            {"open_time_ms": 301000, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0},
        ],
        "levels": [{
            "level_id": "lvl-source-1",
            "selected": True,
            "anchors": [[1000, 10.0]],
            "boundary": {
                "anchor_time_ms": 1000, "anchor_price": 10.0,
                "slope_per_ms": 0.0, "as_of_time_ms": 301000,
            },
        }],
    }


class MirrorFrozenGeometryTests(unittest.TestCase):
    def test_exact_mirror_level_produces_one_locked_source_boundary(self):
        snap = build_mirror_geometry_snapshot("mirror-origin:abc", frozen_event())
        self.assertIsNotNone(snap)
        self.assertEqual(snap["signal_id"], "mirror-origin:abc")
        self.assertEqual(snap["boundaries"][0]["kind"], "horizontal-ray")
        self.assertEqual(snap["boundaries"][0]["anchors"], [
            {"bar_open_time_ms": 1000, "price": 10.0},
        ])
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(record_original_signal(
                "mirror-origin:abc", symbol="ALCHUSDT", timeframe="5",
                pattern="MIRROR", text="source", image_bytes=b"image",
                directory=root, geometry_snapshot=snap,
            ))
            self.assertEqual(
                load_frozen_signal_geometry("mirror-origin:abc", directory=root),
                snap,
            )
            self.assertIsNone(load_frozen_signal_geometry("mirror-origin:other", directory=root))
            data = next(Path(root).glob("*.geometry.json"))
            data.write_text(json.dumps({"tampered": True}))
            self.assertIsNone(load_frozen_signal_geometry("mirror-origin:abc", directory=root))

    def test_invalid_or_outside_window_source_never_reconstructed(self):
        event = frozen_event()
        event["levels"][0]["anchors"] = [[-1000, 10.0]]
        self.assertIsNone(build_mirror_geometry_snapshot("mirror-origin:abc", event))
        event["levels"][0]["anchors"] = [[1000, 10.0]]
        event["levels"][0]["boundary"]["slope_per_ms"] = 0.001
        self.assertIsNone(build_mirror_geometry_snapshot("mirror-origin:abc", event))

    def test_snapshot_rejects_foreign_identity_and_bad_ohlc(self):
        snap = build_mirror_geometry_snapshot("mirror-origin:abc", frozen_event())
        with self.assertRaises(ValueError):
            validate_snapshot(snap, candidate_id="mirror-origin:other",
                              symbol="ALCHUSDT", timeframe="5")
        snap["bars"][0]["high"] = 1
        with self.assertRaises(ValueError):
            validate_snapshot(snap, candidate_id="mirror-origin:abc",
                              symbol="ALCHUSDT", timeframe="5")


if __name__ == "__main__":
    unittest.main()
