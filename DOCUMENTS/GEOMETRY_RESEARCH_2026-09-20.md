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

## G1: expose the preceding impulse on the signal/position chart

The user explicitly needs to see **price action before** the wedge to distinguish a countertrend correction
from same-direction deceleration. Rendering the first wedge anchor at the left edge is insufficient.
The current frozen START is a recorded hypothesis, not necessarily the appropriate START for every wedge
subtype. G1 exposes enough preceding bars to inspect the last impulse's terminal HIGH (falling correction),
terminal LOW (rising correction), and transition pivot for an impulse-deceleration wedge; G1 must not
retrospectively modify existing geometry or choose a trading subtype.

1. Derive the earlier of the two frozen line anchors using the current `robot_position_chart._line_start_index`
   conversion from Scanner source-bar coordinates to the immutable 1m Robot cursor; locate its candle time
   relative to `scanner_geometry_cursor.source_candle_time_ms`. Cover the earlier of pattern start and entry.
2. Target an extra **pre-pattern** context window equal to one pattern-formation span (earliest anchor through
   frozen detection time). This is only a presentation window, not a qualifying impulse definition or a
   strategy predicate. Keep a left margin of max(10 chart bars, 8% of pattern-to-current span), the current
   candle on the right, and existing minimum 1m/5m request lengths.
3. Cap the request at 1,000 candles. Preserve figure-start visibility first, then allocate remaining history
   to the preceding impulse. Derive visibility from the **actual timestamps returned** (not just requested
   candle count). If the full figure does not fit, show `Начало паттерна раньше окна графика`; if the
   figure fits but older context is truncated, show `Предшествующий импульс показан не полностью`.
   Preserve the entry-window warning independently. Never claim the entire impulse is shown merely because
   a fixed number of candles was requested.
4. Cover the Scanner-generated signal PNG as well as Robot position/lifecycle chart surfaces: inspect
   `chart_clean.py::draw_chart`, `analyzer/charts.py`, `notification.py::send_signal`, and
   `telegram_monitoring.py::_with_candles`. Do not assume the Robot position chart and Scanner signal
   image share a candle-loading path. If a legacy snapshot is missing/invalid, retain the previous
   entry/available-data window with an explicit unknown-context outcome; do not make up earlier data.
5. Test 1m and 5m source timeframes, unequal boundary anchor ages, old entry, bounded/missing pre-pattern
   history, and visual readability of the line START points and preceding candles. No new geometry,
   trade admission, risk/execution, persistence writes, backend/VPS restart, or automatic context label in G1.

## G2: later, not part of the chart task

Collect 3–5 mis-anchored chart examples; record signal timestamp and whether a pivot was confirmed by that time.
Compare existing `fit_anchor_trendline` candidates against bounded pivot prominence/distance variants offline,
preserving all original frozen snapshots. Define ranking evidence and tolerances before proposing production geometry
changes. Never use future candles to rank live-time anchor candidates.

## G3: two contexts per wedge orientation, including signal/chart labels (before Triangle)

Existing groundwork is explicit but incomplete. `DOCUMENTS/TRADING_STRATEGY_SPEC.md` §3.2 calls for independent
Falling Wedge reversal/exhaustion vs controlled-pullback/continuation cohorts and Rising Wedge topping/exhaustion
vs bearish-continuation/recovery cohorts. `DOCUMENTS/AUTOPILOT_STRATEGY_ACCUMULATED_DESIGN.md` §7.1 notes that a
Rising Wedge following an upward impulse may provide exhaustion evidence for managing an existing LONG.
Neither document specifies a completed, measurable four-subtype detector or authorizes a Robot priority change.

The intended classification is contextual: retain the existing geometrical `Falling Wedge` or `Rising Wedge`
identity and independently record one of these five context values, based on **history available at signal time**:

| Geometric pattern | Pre-pattern impulse | Context ID | Signal / chart caption |
| --- | --- | --- | --- |
| Falling Wedge | UP | `FALLING_CORRECTION_AFTER_UP` | `Контекст: Коррекция после роста` |
| Falling Wedge | DOWN | `FALLING_DECELERATION_AFTER_DOWN` | `Контекст: Замедление после падения` |
| Rising Wedge | DOWN | `RISING_CORRECTION_AFTER_DOWN` | `Контекст: Коррекция после падения` |
| Rising Wedge | UP | `RISING_DECELERATION_AFTER_UP` | `Контекст: Замедление после роста` |
| Either / insufficient evidence | UNKNOWN | `PREPATTERN_CONTEXT_UNKNOWN` | `Контекст: Не определён` |

### G2/G3 historical START — corrected definition (user, 2026-09-20)

**The earlier claim that a falling corrective wedge STARTs at the lowest local-structure extremum was a misunderstanding and is SUPERSEDED.** The user's clarified rule is the impulse-ending peak/trough at which the countertrend correction begins:

| Wedge context | Preceding impulse | Historical START candidate | Clarification status |
| --- | --- | --- | --- |
| Falling correction | Sharp UP | **Terminal HIGH (upper extreme / swing high) completing that bullish impulse**; downward correction/wedge begins there. | User-confirmed correction. |
| Rising correction | Sharp DOWN | **Terminal LOW (lower extreme / swing low) completing that bearish impulse**; upward rebound/wedge begins there. | User-confirmed mirror of corrective rule. |
| Falling deceleration | DOWN | First impulse-terminal pivot at falling-impulse → decelerating-wedge transition (working interpretation: transition LOW, not necessarily later final minimum). | User's original first-terminal-pivot principle; exact pivot criterion remains open. |
| Rising deceleration | UP | Terminal pivot at rising-impulse → decelerating-wedge transition (working interpretation: transition HIGH). | Mirrored **proposal**, not independently user-confirmed. |

A chart's historical **pattern START**, the pivot ending an impulse and each upper/lower trendline's
individual pivot anchors must be stored/identified separately when they are not the same point.
Do not force both wedge boundaries through the correction's terminal high or low.
Do not search for the extreme of a future-completed pattern: each pivot needs its event time,
confirmation time and evidence available at signal time.

**Avoid circular inference:** G2 supplies multiple plausible impulse-ending extrema and
boundary-pivot candidates without assigning a final subtype. G3 evaluates preceding impulse
direction and independent within-wedge deceleration evidence, then jointly validates context,
START and both boundaries. If evidence is unavailable or contradictory, keep UNKNOWN and
retain safe existing geometry rather than manufacturing a definitive context. Historical
snapshots and drawn lines are immutable; G1 simply exposes old candles for review.

Open thresholds: what counts as a sharp preceding impulse, how many closed candles confirm the
terminal pivot, how to identify a transition amid consecutive highs/lows, and how to treat
unconfirmed START candidates. Collect representative user-reviewed examples of all four variants.

The UP/DOWN impulse label alone does not prove actual deceleration. A G3 specification must distinguish a bounded
prior directional impulse from range noise and measure weakening movement **inside** the wedge without hindsight.
Choose the lookback horizon, trend/volatility normalization, and UNKNOWN thresholds from stored, user-reviewed
examples; avoid confusing a trendline's slope with the impulse that preceded the line's start.

**Display requirement once the G3 classifier exists:** show precisely one `Контекст: …` line in the Scanner
signal's Telegram text (`notification.py::format_signal`) and in its PNG title/header
(`chart_clean.py::build_chart_title`). Propagate the exact frozen, versioned subtype into the Robot
candidate/signal snapshot; show the same line in the Robot position/lifecycle chart title and text/photo caption
(`robot_position_chart.py`, `robot_position_view.py`, `telegram_monitoring.py`). A legacy/missing subtype
remains UNKNOWN; no late chart renderer or notification may independently infer or revise it. Keep the ordinary
`Паттерн: …` identity separate from the context label. Non-wedge patterns are unaffected.

Validate all four context values plus UNKNOWN in both the signal text and PNG and, when Robot evidence exists,
the position/lifecycle chart and caption, including 1m/5m and Telegram caption-length constraints.
Do not show a definitive correction/deceleration label in production until measured signal-time classification
is available and accepted.

**Robot priority is a separate strategy hypothesis:** the user wants to favor deceleration/exhaustion variants
over corrective ones. Study their risk-adjusted outcomes in distinct comparable cohorts before defining
candidate-selection priority. No automatic preferential entry, position size, STOP/TAKE, or ownership-gate
change is authorized by this research/UX requirement.
