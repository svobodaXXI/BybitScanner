"""A descriptive flow snapshot can be kept without granting trading authority."""
import json
import tempfile
import unittest
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from terminal.market_data.pattern_flow_shadow_evidence import (
    build_shadow_sample, save_shadow_sample, window_digest,
)


@dataclass(frozen=True)
class Print:
    trade_id: str
    timestamp_ms: int
    sequence: int
    side: str
    price: Decimal
    quantity: Decimal
    received_at_ms: int


class ShadowEvidenceTests(unittest.TestCase):
    NOW = 1_800_030

    def setUp(self):
        self.prints = (
            Print("p1", self.NOW - 25_000, 1, "Sell", Decimal("100"), Decimal("1"), self.NOW - 24_980),
            Print("p2", self.NOW - 22_000, 2, "Sell", Decimal("99"), Decimal("1"), self.NOW - 21_980),
            Print("p3", self.NOW - 14_000, 3, "Buy", Decimal("99"), Decimal("1"), self.NOW - 13_980),
            Print("p4", self.NOW - 1_000, 4, "Buy", Decimal("102"), Decimal("3"), self.NOW - 980),
        )
        self.record = SimpleNamespace(
            candidate_id="candidate-a", state_revision=4, status="APPROVED",
            symbol=SimpleNamespace(value="BTCUSDT"),
            snapshot_sha256="a" * 64,
            signal_snapshot={"pattern": "Falling Wedge"},
            robot_state={"phase": "WAITING_RETEST", "direction": "LONG"},
        )
        self.preview = SimpleNamespace(
            candidate_id="candidate-a", state_revision=4, symbol="BTCUSDT",
            direction="LONG", known_at_ms=self.NOW, transport_generation=2,
            gap_or_truncation=True, source_complete=False, trading_authorized=False,
            window_sha256=window_digest(self.prints, self.NOW),
            transition=SimpleNamespace(buy_wave_accelerating=True, sell_wave_accelerating=False),
        )
        self.snapshot = {
            "symbol": "BTCUSDT", "generation": 2, "invalid_frames": 0,
            "continuity": "UNPROVEN", "order_authority": False,
            "gap_or_truncation": True, "prints": self.prints,
        }

    def test_exact_window_can_be_saved_in_separate_bounded_archive(self):
        result = build_shadow_sample(self.record, self.preview, self.snapshot)
        self.assertEqual(result["candidate_id"], "candidate-a")
        self.assertEqual(result["state_revision"], 4)
        self.assertEqual(result["public_trade_rows"][0][-1], self.NOW - 24_980)
        self.assertFalse(result["source_complete"])
        self.assertFalse(result["trading_authorized"])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "owner-work.json").write_text("preserve", encoding="utf-8")
            with patch("terminal.market_data.pattern_flow_shadow_evidence._KEEP", 2):
                for _ in range(3):
                    self.assertTrue(save_shadow_sample(folder, result))
            written = sorted(folder.glob("pattern-flow-shadow-*.json"))
            self.assertEqual(len(written), 2)
            self.assertEqual(json.loads(written[0].read_text())["window_sha256"], result["window_sha256"])
            self.assertEqual((folder / "owner-work.json").read_text(), "preserve")

    def test_changed_or_late_snapshot_fails_closed(self):
        altered = dict(self.snapshot)
        altered["prints"] = self.prints[:-1] + (
            Print("new", self.NOW - 500, 5, "Buy", Decimal("103"), Decimal("1"), self.NOW - 400),
        )
        with self.assertRaises(ValueError):
            build_shadow_sample(self.record, self.preview, altered)
        late = dict(self.snapshot)
        late["prints"] = self.prints[:-1] + (
            Print("p4", self.NOW - 1_000, 4, "Buy", Decimal("102"), Decimal("3"), self.NOW + 10),
        )
        with self.assertRaises(ValueError):
            build_shadow_sample(self.record, self.preview, late)
        disconnected = dict(self.snapshot, generation=3)
        with self.assertRaises(ValueError):
            build_shadow_sample(self.record, self.preview, disconnected)

    def test_mismatch_and_untrusted_preview_cannot_be_recorded(self):
        with self.assertRaises(ValueError):
            build_shadow_sample(self.record, SimpleNamespace(**{**vars(self.preview), "source_complete": True}), self.snapshot)
        with self.assertRaises(ValueError):
            build_shadow_sample(SimpleNamespace(**{**vars(self.record), "state_revision": 5}), self.preview, self.snapshot)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(save_shadow_sample(Path(tmp), {"source_complete": True}))
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
