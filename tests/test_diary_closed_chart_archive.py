import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from terminal.diary.closed_chart_archive import (
    ClosedChartArchiveError,
    archive_closed_chart,
)


def _view(*, closed=True, fills=True):
    trade = SimpleNamespace(
        trade_id="trade-1", candidate_id="candidate-1",
        entry_time_ms=1000, exit_time_ms=3000 if closed else None,
        exit_price=Decimal("101"), exit_reason="STOP",
        realized_pnl_usdt=Decimal("-2"),
    )
    markers = (
        SimpleNamespace(time_ms=1000, price=Decimal("100"), side="Buy", filled=True),
        SimpleNamespace(time_ms=2000, price=Decimal("99"), side="Sell", filled=True),
        SimpleNamespace(time_ms=2000, price=Decimal("98"), side="Buy", filled=False),
    ) if fills else ()
    return SimpleNamespace(
        trade=trade, is_open=not closed, markers=markers, symbol="TESTUSDT",
        direction="LONG", pattern="MIRROR", signal_snapshot={"robot_geometry": {}},
        average_entry=Decimal("100"), stop_price=Decimal("99"),
        take_price=Decimal("105"), fees_usdt=Decimal("0.1"),
    )


class ClosedChartArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.png = self.root / "rendered.png"
        self.png.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + b"chart-bytes")

    def test_closed_only_one_final_png_and_factual_report(self):
        chart, report = archive_closed_chart(_view(), self.png, archive_dir=self.root / "archive")
        self.assertEqual(chart.read_bytes(), self.png.read_bytes())
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["trade_id"], "trade-1")
        self.assertEqual(data["pattern"], "MIRROR")
        self.assertEqual(data["net_pnl_usdt"], "-2.1")
        self.assertEqual(len(data["executions"]), 2)
        self.assertEqual([m["side"] for m in data["executions"]], ["Buy", "Sell"])
        self.assertFalse(data["historical_level_changes_available"])
        self.assertEqual(len(list((self.root / "archive").glob("*.png"))), 1)
        self.assertEqual((chart, report), archive_closed_chart(_view(), self.png, archive_dir=self.root / "archive"))

    def test_no_png_for_open_or_unfilled_trade(self):
        for view in (_view(closed=False), _view(fills=False)):
            with self.subTest(view=view):
                with self.assertRaises(ClosedChartArchiveError):
                    archive_closed_chart(view, self.png, archive_dir=self.root / "archive")
        self.assertFalse((self.root / "archive").exists())

    def test_existing_final_image_cannot_be_overwritten(self):
        archive_closed_chart(_view(), self.png, archive_dir=self.root / "archive")
        self.png.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + b"different")
        with self.assertRaises(ClosedChartArchiveError):
            archive_closed_chart(_view(), self.png, archive_dir=self.root / "archive")
