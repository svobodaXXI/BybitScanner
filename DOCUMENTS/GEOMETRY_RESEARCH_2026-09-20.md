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

### External-source findings captured versus follow-up research still owed (2026-09-20)

- **Captured for G2a:** TradingView's pivot confirmation delay requires separate pivot-event and
  availability/confirmation indexes; its retroactively plotted pivot label does not make the
  event known on the pivot candle. QuantConnect's sequential-indicator model motivates
  closed-bar-only replay, not an alternative production ZigZag dependency. Freqtrade's
  lookahead-analysis motivates the **paired truncated-history versus full-history pivot-list**
  regression; filtering future OHLC alone does not prevent lookahead through supplied pivot
  *membership*. The regression and the research helper described below implement this narrow
  adaptation; neither result demonstrates profitable entries or establishes a context subtype.
- **Captured for G1/G2/G3:** earlier in this document, original links and ADAPT/DEFER choices
  preserve TradingView Lightweight Charts, mplfinance, TradingView pivot/ZigZag,
  SciPy prominence/distance, QuantConnect Zig Zag, StockCharts wedge context and Freqtrade
  lookahead patterns. They are *reference concepts*, not imported source code or thresholds.
- **G3P/G3R reference research completed below; G3C still pending:**
  Four-point emerging-wedge visuals and Telegram `Освежить` callbacks now have recorded
  reference behaviors and BybitScanner-specific design choices. Robot boundary-to-boundary
  corridor trading remains a **user-requested strategy hypothesis**, not a validated
  external implementation or an authorized order path. Before G3C implementation,
  research relevant source examples, assumptions, edge/risk evidence and failure modes
  separately. Neither reference research nor a display button authorizes Robot orders.

## G3P external reference — four-point *forming* wedges (reviewed 2026-09-20; before Triangle)

**Source and observed behavior (not an imported trading rule):**

| Primary/public reference | Relevant documented behavior | Our decision |
| --- | --- | --- |
| [StockCharts Falling Wedge](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/falling-wedge) | Upper resistance line needs **at least two reaction highs** (ideally three); lower support line needs **at least two reaction lows**; the descending lines must converge. StockCharts distinguishes the pattern's potential from an actual resistance breakout. | **ADAPT** two HIGH + two LOW as a *minimum geometric hypothesis*, not proof of a mature wedge, confirmation of a breakout, or a profitable corridor trade. Preserve separate preceding-impulse/START evidence. StockCharts' examples concern longer stock-market horizons, not validated thresholds for 1m/5m crypto. |
| [TradingView automated Falling Wedge](https://www.tradingview.com/support/solutions/43000697938-chart-pattern-falling-wedge/) and [Rising Wedge](https://www.tradingview.com/support/solutions/43000653219-chart-pattern-rising-wedge/) | Separate **In Progress** mode can display emerging formations; its published pivot model is 5 left / 5 right bars. The last two forming-pattern points need not themselves be confirmed pivots, and the last price line is dotted. It checks for invalid line/close intersections and reports lifecycle states such as Awaiting, Failed and Indefinable. Its “New Pattern” alert uses the position of point 1 or 3 to distinguish a new formation. | **ADAPT** separate emerging vs mature pattern state, projected/dotted *future portions of boundaries*, intersection/containment and explicit invalid/ambiguous states. **Do not copy** its 5/5 settings, target prices, permissive unconfirmed-last-point rule, or point-1/3 identity algorithm. G3P first requires four genuinely confirmed source-timeframe pivots; an optional three-pivot or provisional fourth-point *preview* would need its own future-only, past-closed-bar spec. |
| [TradingView Pine plotting/repainting](https://www.tradingview.com/pine-script-docs/concepts/repainting/) and [trend-line visuals](https://www.tradingview.com/pine-script-docs/faq/visuals/) | A pivot plotted at its historic candle may have become observable only after several additional bars. Its documented trend-line example extends a line joining two same-side pivots into the future. | **ADAPT** distinct pivot event time / availability time, solid observed segment versus clearly dashed extrapolation, and historical truncated-frame replay. In a four-point signal, do not backdate detection to the first anchor candle or treat a future-selected pivot as known at that time. No extra rendering dependency. |
| [QuantConnect LEAN Zig Zag](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/zig-zag) | A stream-updated swing-point indicator uses reversal sensitivity and minimum trend length to reduce noise. | **DEFER** replacing `find_pivots`: compare existing filtered swing history first; any optional alternate candidate-finding or noise threshold requires measured 1m/5m evidence and a separate slice. |

**Repository gap verified at PR #156 HEAD `d2882da`:** `geometry/engine.py` returns `None` if
`len(highs) < 4` **or** `len(lows) < 4`; the mature production geometry therefore cannot
surface a total-four-pivot (2 HIGH + 2 LOW) wedge. Meanwhile
`geometry/candidate.py::build_candidate_lines` already fits each same-side line from two
real anchors but applies `DEFAULT_MIN_LINE_SPAN = 30` and
`DEFAULT_MIN_CONFIRMATIONS = 2` (additional matching points after the primary anchor)
for regular candidates. These are existing *mature-detector* gates, **not** G3P approval
thresholds. Simply lowering either gate globally would change current Scanner/Robot admission
and is outside G3P observation-only scope.

**Bounded first G3P design:** start from the same already-closed OHLC and verified 2 HIGH +
2 LOW; create an independent *observational* provisional line-pair record using the
existing anchor-fitting function (without feeding it into the mature geometry winner).
Check source-time order and confirmation times, descending/ascending slopes, positive
corridor width throughout the observed span, projected convergence/apex, actual historical
close/intersection violations, a minimum usable future corridor and ambiguous alternate
pairings. The projected right-hand segments are estimates and carry a distinct revision;
never fabricate price candles or promise the future intersection price. Freeze the initial
signal-time hypothesis; on later closed bars distinguish a revised version of the same
formation from an invalidated/expired/replaced formation. Stable identity must be tested
against re-anchoring and replay; TradingView's point-1/3 rule is an *example of identity
semantics*, not an adequate drop-in ID for our immutable Robot snapshots.

**G3P acceptance before G3R/G3C:** 3 confirmed + future-known fourth must never produce
a four-point signal; exactly 2 HIGH + 2 LOW becomes eligible only at the latest actual
right-confirmation CLOSE; regression compares truncated-versus-full source pivot lists at
the same as-of index. Check false wedges (parallel/diverging/crossed lines), revision after
fifth/sixth pivot, lost/incomplete source history, 1m/5m index/time alignment and
bounded Scanner hot-path cost. A plotted forecast, even when all four pivots were
confirmed, must not independently enable a Robot order. G3R button research and G3C
corridor execution research remain separate subsequent micro-slices.

## G3R external reference — Telegram `Освежить` and stable formation identity (reviewed 2026-09-20)

**Primary/official sources and reuse choices:**

| Reference | Documented behavior or limitation | BybitScanner adaptation |
| --- | --- | --- |
| [Telegram Bot API: InlineKeyboardButton and CallbackQuery](https://core.telegram.org/bots/api#inlinekeyboardbutton) / [CallbackQuery](https://core.telegram.org/bots/api#callbackquery) | An inline button's `callback_data` is limited to **1–64 bytes**. A callback includes the user, a query ID and, when accessible, the originating bot message; callback data cannot be trusted as a live copy of the message's current keyboard. Telegram displays a progress indicator until the bot calls `answerCallbackQuery`. | **ADAPT** a compact, versioned, opaque formation-reference token instead of embedding symbol + timeframe + pivot arrays + entire snapshot. Check both authorized user/chat and the token's ownership/formation binding. Answer each callback promptly **before** a bounded scan or PNG render; report invalid/expired tokens explicitly. A token is a reference, not authority to trade. |
| [Telegram Bot API: sendPhoto](https://core.telegram.org/bots/api#sendphoto), [sendMessage](https://core.telegram.org/bots/api#sendmessage), [editMessageMedia](https://core.telegram.org/bots/api#editmessagemedia) | A bot can send a new photo with inline keyboard/caption, or modify media where supported. Photo captions are limited to 1024 characters after entity parsing. | **ADAPT** send a **new** text + PNG signal pair and leave the old signal/time-stamped chart untouched. The two posts must share the same one-pass refreshed observation ID/time and geometry revision; don't silently edit the historical post or resend its old filename as if current. Keep caption short; existing Scanner sends its signal text separately and currently attaches the inline keyboard to the photo. |
| [Telegram Bot FAQ: broadcasting limits](https://core.telegram.org/bots/faq#broadcasting-to-users) | Avoid more than about one outgoing message per second to the same chat; sustained bursts can yield HTTP 429. | **ADAPT** per-owner/per-formation cooldown, in-flight single-flight/deduplication for repeated taps and respectful 429 handling. Don't serialize the whole bot behind a network chart fetch. Use measured, bounded queueing rather than speculative infrastructure. |
| [python-telegram-bot example: persisted arbitrary callback data](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/examples/arbitrarycallbackdatabot.py) | Its optional arbitrary-object callback mode resolves a short Telegram identifier through a cache; unpersisted identifiers may become invalid after a restart or eviction. | **ADAPT the reference-token concept only, not the PTB dependency**: this repository already uses `requests` and a single `getUpdates` listener. A short token must resolve via a durable existing data owner (or the smallest approved durable mapping) so a recently posted button can survive listener restart. Expired/unresolvable legacy buttons return a clear status instead of guessing by ticker. |

**Repository integration facts verified against PR #156 HEAD `e7c5376`:**

- `notification.py::send_signal` currently sends **signal text first**, then a Scanner PNG
  with `build_tradingview_keyboard`. That keyboard identifies existing review buttons
  by `symbol:timeframe`, not by an immutable unique formation/message instance. The
  current generic `{symbol}_analysis.png` path can be reused by a later scan; an on-demand
  refresh must render/send a per-request consistent chart snapshot and never mistake
  that file path for a durable image or formation identifier.
- `telegram_monitoring.py::run` is the existing **single** long-polling listener and routes
  positions/monitoring callbacks before delegating to `telegram_review._process_callback`.
  `_process_monitor_callback` and `telegram_review._process_callback` already enforce
  owner checks and acknowledge callbacks. Add one narrow refresh callback dispatch in
  this listener, without a second `getUpdates` consumer, unbounded handler latency,
  or routing into Robot approval/control actions.
- `telegram_monitoring.py::_scanner_request` currently targets Scanner
  `/api/scanner/status|start|pause|resume`; `main.py::run_scan_pass` scans all discovered
  symbols and emits scan-start/scan-finish notifications. Neither should be called
  as a quick-refresh shortcut. Locate/reuse the smallest existing single-symbol
  analyzer / frozen-observation builder; if a bounded read-only on-demand route does
  not yet exist, define one **only within G3R**, without starting the periodic Scanner
  or changing candidate admission or Robot state.

**Proposed minimal refresh contract (not implemented):**

1. The initial G3P signal registers a **durable stable formation ID** (symbol,
   source timeframe and signal-time pivot/geometry provenance; exact identity
   and schema are G3P outputs), initial revision and originating Telegram
   chat/message. Store a compact opaque token referring to this identity;
   do not base the lookup on mutable ticker-only review keys or on an
   in-memory cache that is lost on restart. Preserve old snapshot/lines.
2. On an owner click, promptly acknowledge the Telegram query; validate
   chat + original-message binding, token version, formation identity,
   current lifecycle and duplicate/in-flight requests. A missing original
   message or ambiguous/missing formation returns explicit `unavailable`,
   not a new candidate chosen merely by symbol. Invalidated/expired/
   superseded formations return their current state without resurrecting
   an old approved signal.
3. Fetch **bounded current closed candles** for only this symbol/timeframe,
   reconstruct its current observation with signal-time-safe pivots,
   and verify it still refers to the same formation. Construct **one**
   immutable refreshed snapshot, then render text and image from that
   exact revision/current candle time. Send a new linked Telegram signal
   pair; allow a valid refresh when the periodic scanner is PAUSED only if
   a separately authorized read-only fetch is available. Do not call
   full-pass scanning, unpause/start the Scanner, write a new Robot approval,
   mutate an existing Robot snapshot, or send any order.
4. Deduplicate repeated taps while work is in progress. On stale inputs,
   incomplete history, fetch/chart failure or Telegram 429, report the
   actual failure without posting an old chart as current; avoid duplicate
   text-only or photo-only 'successful refresh' claims. The original
   message and earlier revisions remain inspectable after restart.

**G3R focused acceptance:** callback data <=64 **UTF-8 bytes**; wrong user/chat and
fabricated token rejected; correct post/formation survives restart; no cross-talk
between same symbol on 1m/5m or between two generations of its wedge; double tap
produces no duplicate updated signals; old photo stays old; new text and photo
share one current evaluation ID/time; paused periodic scanner stays paused;
failures/expiry are explicit; bot polling and Robot admission remain unaffected.
G3R is still documentation-only, and has no implementation authorization to
change trading behavior.

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

## G2a implementation specification — terminal-pivot evidence (2026-09-20)

**Task and status (updated 2026-09-20):** the G2a pure research helper and 17 focused tests were published
as commit `44ef535` in draft PR #156, branch `feat/geometry-pattern-chart-window` (not merged into main).
The standalone exact-scope verifier passed; `task finish` did not produce a transaction-bound PASS receipt
because the test file was already untracked at task start. Scanner admission, Robot execution, trade/risk
priority, current geometry winner, Telegram labels, live DB, VPS and running processes remain out of scope.
No numeric impulse threshold is validated or chosen in this research.

### Existing contracts verified against repository main

- `pivots.find_pivots(df, left=3, right=3, min_change=0.003)` returns two lists of dicts
  `{"index": int, "price": float, "type": "high"|"low"}`. A returned pivot at index `i`
  uses subsequent `right` candles, so its confirmation becomes available **at or after
  the close of source candle `i + right`**, not at candle `i`. Its same-side
  `filter_pivots` may drop a terminal candidate: do not presume the filtered lists
  are exhaustive. `find_pivots` also cleans/copies some frame data; reuse the lists
  that Scanner already calculated instead of running it again in the hot path.
- `analyzer/core.py` has the already-loaded OHLC frame and pivot lists before calling
  `analyze_wedge`; `geometry/evaluation.py` currently computes
  `start_index=min(first upper line pivot, first lower line pivot)` and stores
  `pair_metrics["pre_pattern_impulse"]` from `detect_pre_pattern_impulse` using its
  20-candle endpoint-close window. `geometry/ranking.py` chooses geometry before
  final wedge classification. **Do not replace this existing evidence or interpret its
  nonzero close-change direction as confirmed strong impulse.**

### Proposed first code slice: pure diagnostic, no pipeline wiring

Implement only a pure helper in `geometry/pre_pattern.py` (or an equally small reused
existing module) which accepts already-loaded **closed source candles**, existing
`highs`/`lows` pivot lists, a proposed episode `start_index`, an explicit last
available **closed** source-bar index `as_of_index`, and the pivot right-window
parameter actually used in that scan. Return a small result object with:
`status = EVIDENCE_AVAILABLE | INSUFFICIENT_HISTORY | UNCONFIRMED_PIVOT |
AMBIGUOUS | INVALID_INPUT`, bounded source window and time range, and a bounded
chronological list of possible transition pivots:
`index`, `time_ms`, `side` (`HIGH`/`LOW`), `price`, `confirmed_at_index`,
`confirmed_at_time_ms`, previous opposing-pivot index/time, relative swing
displacement, duration in source bars, and the provisional swing direction
`UP`/`DOWN`/`UNKNOWN`. Reuse source OHLC `time` and prices, not Robot's
projected 1m cursor. No final context subtype or replacement START is output.

The context window must be **bounded and explicit**, with enough preceding history
to contain the swing's opposing pivot and terminal pivot. If the fixed 20-bar
historical window or fetched OHLC is insufficient, return `INSUFFICIENT_HISTORY`
instead of treating the nearest available candle as the impulse's true origin.
Do not pick numeric displacement/ATR/duration admission thresholds yet; include
measurements for comparison against labeled 1m/5m examples. Do not assume the
actual strongest extreme in all of history is the first terminal pivot at the
impulse-to-pattern transition. Do not discard alternative HIGH/LOW candidates
just because a current geometry line starts later.

**No lookahead:** exclude any pivot with `index + right > as_of_index` and any
OHLC after `as_of_index`; a pivot becomes eligible only once the required right
candles have **closed**. Never use the final extreme of a subsequently completed
pattern to classify an earlier signal. **Implemented G2a provenance correction:** an unconfirmed pivot MUST NOT be exposed even as a pending
candidate merely because it appears in a pivot list calculated from later candles. Such future-known
pivot membership is itself lookahead; the helper excludes it before reading its price/type or
forming swings/status. Consequently `pending_candidates` is empty in this helper. A later,
separate provisional-pivot feature may identify tentative extrema **only from source candles
closed by `as_of_index`** and must not promote them to confirmed START/context evidence.
Regression compares pivot lists calculated with truncated-at-`as_of_index` history against
full-history lists both immediately before and at confirmation, for `right=1,2,3`.

**Speed and compatibility:** do not add a network request, run all possible
candidate-pair combinations, change `pivots.find_pivots` defaults, refit lines,
or alter `detect_pre_pattern_impulse`'s existing return keys/meaning. Keep G2a
helper uncalled by production Scanner/Robot until an independently reviewed
follow-up integration slice. Reuse existing pivot lists; if later measurements
prove that same-side `filter_pivots` removes required terminal extrema, make
that a separate tested change, not an implicit pivot-engine replacement.

### Focused verification / completion evidence

- Rising corrective episode: preceding DOWN swing ending at a confirmed LOW;
  falling corrective episode: preceding UP swing ending at a confirmed HIGH.
- Falling deceleration episode: DOWN impulse transition pivot remains
  observational; opposing later lows must not move the earlier START.
  Mirrored rising deceleration remains an unconfirmed anchor-rule proposal.
- A provisional terminal pivot at source index `i` is not confirmed at
  `as_of=i+right-1`, becomes eligible at `as_of=i+right`; future appended
  bars must not rewrite an earlier recorded evidence snapshot.
- Noisy/flat movement, two neighboring candidate pivots, insufficient
  preceding candles, corrupt/non-monotonic timestamps, and an anchor near
  either edge return bounded, non-fabricated results.
- Same closed bar history on 1m and 5m produces source-index-consistent
  results without a 1m/5m unit mix-up. A focused test confirms old
  `detect_pre_pattern_impulse`, geometry winner, scanner posts and Robot
  states are not modified by this slice.

**Next gate:** review Codex G1a diff and publish/synchronize it separately,
then request a bounded G2a pure-helper implementation and compare the output
against user-reviewed examples before any scanner integration.
