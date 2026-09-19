# Geometry G0 — existing groundwork and external reference review

Status: RESEARCH / NO GEOMETRY OR TRADING IMPLEMENTATION AUTHORIZATION
Date: 2026-09-20
Scope: G0 research for G1 chart window and later G2 pivot/anchor work
Owner: DOCUMENTS/BACKLOG.md section 3 (G0–G2)

## Existing BybitScanner groundwork (verified against main)

- `geometry/trendline.py::fit_anchor_trendline` constructs a structural line through two actual pivot anchors and uses later pivots to quantify residual errors. Do not add another parallel trendline engine.
- `geometry/engine.py` already retains upper/lower anchor evidence; `robot_position_chart.py::_line_start_index` translates source-timeframe `anchor_index` to the Robot's 1-minute geometry coordinate, then masks line samples before the anchor and after the frozen apex.
- `scanner_geometry_cursor.py` freezes source candle time and geometry index; line prices on historical chart candles are derived from that frozen geometry. Do not refit geometry to improve presentation.
- `robot_position_view.py::chart_candle_limit` sizes the request **only from trade entry time**; `telegram_monitoring.py::_with_candles` makes the single bounded candle request. Thus the plotted pattern can begin before the downloaded chart window even when the entry is visible. This is a display-window error, not proof that detection chose a wrong anchor.
- `DOCUMENTS/ROADMAP.md::FUTURE_MISSION_ANCHOR_QUALITY_LEARNING` already describes multiple plausible historical anchor candidates, immutable signal-time evidence, and future retrospective calibration. That separate research mission does not authorize present-day model training or live strategy changes.

## External examples and BybitScanner-specific reuse

| Reference | Verified useful behavior | Decision |
| --- | --- | --- |
| TradingView Lightweight Charts time-scale docs: https://tradingview.github.io/lightweight-charts/docs/5.1/time-scale | Select visible data/time range or logical bar range; logical range permits chart margins. A data-time range cannot show historical bars not loaded into the chart. | ADAPT the *visible-window calculation*, not a JS chart dependency: fetch enough historical OHLC first, then render the frozen pattern's full visible span. |
| mplfinance repository: https://github.com/matplotlib/mplfinance | Chart draws the timestamp-indexed candles supplied by its caller; `show_nontrading` handles omitted periods, not missing older market data. | ADOPT existing `mplfinance` renderer. Widen the data request in `_with_candles`; do not introduce a second renderer or artificially extend unobserved candles. |
| SciPy `find_peaks`: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html | Independent pivot candidates can be filtered by distance and prominence, with optional bounded local window. | DEFER to G2: compare on frozen examples against the existing pivot/anchor engine; avoid changing candidate selection before the chart-window fix. A centered pivot may require future candles to confirm: never use unobserved candles at signal time. |
| Existing BybitScanner anchor model: `geometry/trendline.py`, `geometry/engine.py` | Actual anchor pivots plus fit/error evidence already exist. | REUSE FIRST: select/rank multiple anchors only via a G2 spec and observational side-by-side verification, without silently replacing frozen robot geometry. |

No external code is copied. External approaches are presentation/research patterns, not trading rules.

## G1: smallest chart-only implementation contract

1. Derive the earliest historical start of **both** frozen pattern lines from their `anchor_index` in source-candle coordinates, transformed to 1-minute Robot geometry coordinates by the existing `_line_start_index` function. Use the immutable Scanner cursor (`geometry_index`, `source_candle_time_ms`) to compute a start timestamp. The chart must cover the earlier of that start and entry time.
2. Pad the left side by `max(10 bars, ceil(0.08 * number_of_bars_in_span))`, subject to the existing 1,000-candle API cap and current-candle/right-edge behavior. Keep the 300-bar (1m) / 120-bar (other) minimums. For 5m source geometry do **not** mistake a source-bar anchor for a 1-minute Robot index.
3. If a start index/cursor is missing or invalid, degrade safely to the current entry-based chart window; do not fabricate an anchor. If the 1,000-bar cap or the exchange's returned range excludes the pattern start, mark it explicitly: `Начало паттерна раньше окна графика`. Display the old entry-window warning independently when applicable.
4. Handle candle boundaries and source-timeframe alignment using actual returned OHLC timestamps; test 1m and 5m, different upper/lower start indices, missing/invalid anchor, capped history, and a window whose start is returned/visible. No DB writes, no change to scanner detection, signal snapshot, trading state, entry or protection.
5. Verify through the Telegram chart code and focused tests before merging. Actual Telegram visual acceptance remains a separate check when an operating PAPER listener is available; no backend/VPS restart for this task.

## G2: later, not part of the chart task

Collect 3–5 mis-anchored chart examples; record signal timestamp and whether a pivot was confirmed by that time. Compare existing `fit_anchor_trendline` candidates against bounded pivot prominence/distance variants offline, preserving all original frozen snapshots. Define ranking evidence and tolerances before proposing production geometry changes. Never use future candles to rank live-time anchor candidates.
