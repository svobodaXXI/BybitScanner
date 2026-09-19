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

## Additional existing code: impulse context is already computed (2026-09-20)

A targeted code review found `geometry/pre_pattern.py::detect_pre_pattern_impulse(candles, start_index, lookback=20)`.
`geometry/evaluation.py::evaluate_candidate_pair` already derives `start_index` from the earliest of the
upper/lower line candidate's first pivots, calls that helper and writes its result into
`pair_metrics["pre_pattern_impulse"]`. It records lookback-window indexes, first/last close,
percentage change and `UP` / `DOWN` / `FLAT`. This is **existing groundwork to reuse, not a new detector
to build from scratch**. Before proposing new fields or running another candle request, trace how
`pair_metrics` reaches Scanner signal and frozen Robot snapshot; do not presume it already does.

Limitations that matter for G2/G3:
- The helper classifies **any nonzero endpoint-close change** as UP or DOWN; it has no
  volatility/ATR significance threshold, no trend persistence, no pivot confirmation and no
  measurement of deceleration *within* the wedge. Its result must **not** be displayed as a
  definitive correction/deceleration label or treated as a Robot priority rule.
- Its input START is currently derived from existing line anchors. Since the user's corrected
  START can be the impulse-ending high/low rather than either fitted boundary's first pivot,
  a future context classifier must evaluate bounded alternative transition pivots and retain
  their time/index evidence, rather than accepting the current `start_index` as ground truth.
- `lookback=20` is a present implementation constant, **not** an approved definition of an
  impulse for 1m and 5m. A source-timeframe-aware measurement window is a future G3 decision.

For G2 reuse existing anchor-based candidate generation and actual pivot support. A proposed
small extension to research **without changing execution** is to attach provenance to each
candidate transition pivot: event candle index/time, pivot side (HIGH/LOW), confirmation
index/time, provisional impulse direction, and which fitted boundary candidates use it.
Retain only candidates already confirmed by the signal's decision time. G3 can then match
UP-ending HIGH to falling correction, DOWN-ending LOW to rising correction, and test the
falling/rising deceleration transition hypotheses separately. Continue to record UNKNOWN if
evidence does not discriminate.

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

## G2/G3: external algorithm patterns and incremental reuse plan (2026-09-20)

**Sources checked:** [TradingView Zigzag](https://www.tradingview.com/support/solutions/43000591664-zigzag-indicator/),
[TradingView Pivot Points High Low](https://www.tradingview.com/support/solutions/43000589195-pivot-points-high-low/),
[SciPy find_peaks](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html),
[QuantConnect Zig Zag](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/zig-zag),
[StockCharts Falling Wedge](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/falling-wedge),
[Freqtrade lookahead-analysis](https://docs.freqtrade.io/en/latest/lookahead-analysis/).
These are reusable concepts, not proof that any particular threshold generates positive trading expectancy.

| External design pattern | Decision for BybitScanner |
| --- | --- |
| TradingView pivots are confirmed using bars on both sides; its Zigzag distinguishes confirmed swing points from temporary projected pivots, and applies a price-reversal threshold. | ADAPT: candidate `pivot_time`, `confirmed_at`, `HIGH/LOW`, `PENDING/CONFIRMED`, and structural swing significance. PENDING points may be observational on a chart, but must not retroactively appear in an earlier signal-time context. Existing Scanner pivots should be reused first. |
| SciPy `find_peaks` exposes candidate peak distance and prominence, plus width; a negative price series produces trough candidates. | ADAPT **criteria**, not a new mandatory SciPy dependency: measure local prominence in the bounded pre-pattern segment and avoid choosing micro-extrema. Compare with current pivot generator; normalized prominence/thresholds remain to be calibrated for 1m and 5m. |
| QuantConnect Zig Zag uses reversal sensitivity and minimum trend length to filter noise. | ADAPT: impulse candidate is a *swing* with observable displacement and duration, not the sign of one close-to-close endpoint difference. Test ATR-relative and percentage displacements, preserving source-timeframe candle units and avoiding a magic copied threshold. |
| StockCharts categorizes the same Falling Wedge as possible continuation after UP and reversal after DOWN, while breakout confirms the bullish interpretation. | ADAPT: prior impulse and geometric wedge are separate signal-time features/cohorts. Correction/deceleration context alone does not authorize an entry or imply an observed profit edge. |
| Freqtrade lookahead analysis checks whether using future candles changes historical entries/indicator values. | ADAPT: replay stored signals one closed candle at a time and assert that the frozen pivot/START/context at historical signal time does not depend on later candles. Do not substitute a successful hindsight scan for signal-time correctness. |

### Proposed reuse-first pipeline, not yet a production rule

1. **Reuse existing data/evidence.** `geometry/evaluation.py` computes `start_index=min(first upper pivot,first lower pivot)`, then calls `detect_pre_pattern_impulse(candles,start_index)` **for every candidate pair**. `geometry/ranking.py` chooses geometry before final pattern classification. The current impulse's `lookback=20` and endpoint-close sign cannot classify impulse strength or deceleration; its start is also not necessarily the historical terminal high/low demanded by the user's corrective START rule.
2. **Observe without affecting the existing winner.** For bounded *distinct* candidate STARTs, compute (and memoize per scan) read-only prior-swing evidence from already-loaded, closed OHLC and existing Scanner pivots: direction, terminal HIGH/LOW event time, confirmation time, duration, price displacement and volatility-relative magnitude. Label missing history/noisy/nonconfirmed evidence UNKNOWN. Do not add a second network request per candidate, rewrite existing geometry ranking or add a second detector.
3. **Small shortlist, then joint evaluation.** Initially retain a small, bounded set of existing *validated geometry pairs* at the current ranker's selection boundary for side-by-side research only, and compare their independent candidate START/context evidence against the chosen production pair. Do not explode the existing pair-generation loop into multiple full passes. If alternative geometry cannot be retrieved from the current selection boundary without a substantial refactor, first log alternatives observationally rather than expanding core contracts.
4. **Candidate terminal pivots versus line anchors.** For a falling corrective wedge use the terminal HIGH of its preceding UP impulse; for a rising corrective wedge use the terminal LOW of its preceding DOWN impulse; evaluate falling deceleration at its DOWN-impulse transition pivot. A candidate episode START is **not** automatically one of both fitted boundaries' `anchor_index` values. Keep independent authentic upper/lower support pivots; never backfill/shift the frozen geometry to a desired episode START.
5. **Require real deceleration evidence.** An impulse DOWN followed by descending/converging lines is necessary context for a falling deceleration *hypothesis*, not sufficient to call it slowing. Compare progression of successive directional pivot excursions and displacement per elapsed time inside the wedge with the pre-pattern impulse; require converging genuine bounds/containment as already validated. Record any inability to measure the trend change as UNKNOWN. No ad hoc hard thresholds are authorized before labeled examples.
6. **Version and replay.** Store observational provenance (`source_timeframe`, `signal_time`, `pivot_time`, `confirmed_at`, bounded lookback, candidate START, separate line anchors, classification evidence/version) with each *new* signal-time research record when an approved slice specifies its persistence shape. Do not mutate legacy snapshots or current trading DB during research. Compare the same historical event under truncated-at-signal-time replay and full-history inspection; classify only from evidence observable by the signal time.
7. **Strategy separation.** After four variants plus UNKNOWN can be differentiated on user-reviewed 1m/5m examples and prospective PAPER observations, display one frozen `Контекст: …` line consistently in Telegram text, Scanner PNG, Robot position/lifecycle caption and chart. Evaluate subtype results net of fees under matched entry rules; a proposed deceleration candidate-selection preference needs its own risk/admission decision, never follows automatically from a label.

**Implementation sequence:** complete/review G1a (Codex's unpublished display-only slice), then G1b Robot chart if needed;
G2a add a focused *pure read-only* impulse-evidence helper and regression using existing candles/pivots;
G2b compare a bounded shortlist of START/geometry alternatives observationally on saved user-reviewed signals;
G3a establish subtype+UNKNOWN evidence and label display after examples; G3b separately evaluate any Robot selection
priority. Preserve scanner throughput and the current PAPER runtime until each smaller gate is verified.
