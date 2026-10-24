import copy
import tempfile
import unittest
from pathlib import Path

from signal_archive import record_original_signal, load_frozen_signal_geometry


def snapshot(signal_id="cand-1"):
    return {
        "schema_version": 1, "signal_id": signal_id,
        "symbol": "BTCUSDT", "timeframe": "5",
        "bars": [
            {"open_time_ms": 1000, "open": 10, "high": 12, "low": 8, "close": 11},
            {"open_time_ms": 2000, "open": 11, "high": 14, "low": 9, "close": 13},
        ],
        "boundaries": [
            {"boundary_id": "upper", "kind": "upper", "anchors": [
                {"bar_open_time_ms": 1000, "price": 12},
                {"bar_open_time_ms": 2000, "price": 14}]},
            {"boundary_id": "lower", "kind": "lower", "anchors": [
                {"bar_open_time_ms": 1000, "price": 8},
                {"bar_open_time_ms": 2000, "price": 9}]},
        ],
    }


class FrozenSignalGeometryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def record(self, signal_id, payload):
        return record_original_signal(
            signal_id, symbol="BTCUSDT", timeframe="5", pattern="Wedge",
            text="Original", image_bytes=b"PNG",
            photo_response={"ok": True, "result": {"message_id": 1}},
            directory=self.dir, geometry_snapshot=payload,
        )

    def test_round_trip_exact_id_first_wins(self):
        self.assertTrue(self.record("cand-1", snapshot()))
        self.assertEqual(load_frozen_signal_geometry("cand-1", directory=self.dir), snapshot())
        self.assertIsNone(load_frozen_signal_geometry("cand-2", directory=self.dir))
        changed = snapshot()
        changed["boundaries"][0]["anchors"][0]["price"] = 11
        self.assertTrue(self.record("cand-1", changed))
        self.assertEqual(load_frozen_signal_geometry("cand-1", directory=self.dir), snapshot())

    def test_rejects_unknown_times_missing_line_or_identity(self):
        for mutate in (
            lambda s: s["boundaries"][0]["anchors"][0].update(bar_open_time_ms=1500),
            lambda s: s["boundaries"].pop(),
            lambda s: s.update(signal_id="wrong"),
            lambda s: s["bars"][1].update(open_time_ms=1000),
            lambda s: s["boundaries"][0]["anchors"][0].update(price=float("nan")),
        ):
            data = copy.deepcopy(snapshot())
            mutate(data)
            with self.subTest(data=data):
                signal_id = f"cand-{len(list(self.dir.glob('*.json')))}"
                data["signal_id"] = signal_id if data["signal_id"] == "cand-1" else data["signal_id"]
                self.record(signal_id, data)
                self.assertIsNone(load_frozen_signal_geometry(signal_id, directory=self.dir))

    def test_tampering_fails_closed(self):
        self.record("cand-1", snapshot())
        path = next(self.dir.glob("*.geometry.json"))
        path.write_text("{}", encoding="utf-8")
        self.assertIsNone(load_frozen_signal_geometry("cand-1", directory=self.dir))

    def test_original_png_archive_still_succeeds_without_geometry(self):
        self.record("cand-1", None)
        self.assertIsNone(load_frozen_signal_geometry("cand-1", directory=self.dir))


if __name__ == "__main__":
    unittest.main()
