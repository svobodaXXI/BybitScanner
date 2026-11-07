"""MIRROR Scanner cards are observational, not a PAPER admission verdict."""

from mirror_scanner import mirror_caption


def test_caption_does_not_claim_paper_authorization_or_denial():
    row = {
        "symbol": "0GUSDT",
        "timeframe": "5",
        "breakout": {},
        "breakout_evidence": {},
        "level_label": "L-shape lower",
        "level": {
            "anchors": [(0, 1.0)],
            "boundary": {"slope_per_ms": 0, "anchor_price": 1.0},
        },
        "first_retest_text": "—",
        "imbalance_text": "—",
        "sources_text": "L-shape",
    }
    for kind in ("breakout", "first_retest"):
        caption = mirror_caption(row, kind)
        assert "PAPER-допуск и исполнение проверяются отдельно" in caption
        assert "PAPER-допуск MIRROR не авторизован" not in caption
        assert "MIRROR · 0GUSDT 5m" in caption
