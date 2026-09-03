# BybitScanner — Trading Strategy Living Specification

Version:

1.2

Date:

2026-09-03

Document Type:

TRADING_STRATEGY_SPECIFICATION

Status:

ACTIVE / RESEARCH-ONLY

# DOCUMENT_METADATA

document_id:

BS-DOC-TRADING-STRATEGY-001

purpose:

Repository-authoritative living specification for the trading system intended for BybitScanner research and a
future AUTOPILOT robot.

machine_readable:

true

parser_version:

1.0

status:

ACTIVE_RESEARCH_ONLY

implementation_authorization:

NONE

owners:

* Trading Strategy / Research;
* future AUTOPILOT policy layer.

authoritative_references:

* `DOCUMENTS/PROJECT_CONTRACTS.md`;
* `DOCUMENTS/ARCHITECTURE.md`;
* `DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md`;
* `DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md`;
* `DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md`;
* current Scanner, Geometry, Wedge, Confirmation, Signal and Terminal code for verified implemented baselines.

---

# 1. PURPOSE AND AUTHORITY

The terminal objective is a trading system that demonstrates profitability with acceptable risk after realistic
costs. That objective is not yet an achieved property. This document specifies what must be defined, observed and
validated before any setup can be treated as a production strategy.

This is a living specification. It owns trading-research vocabulary, setup hypotheses, entry and management model
separation, validation rules, promotion criteria and the research data required by a future AUTOPILOT. It does not
authorize implementation, live trading, autonomous execution, numeric optimization or a change to Scanner,
Geometry, Signal, PAPER or LIVE behavior.

Terminal mechanics are not evidence of edge. A working chart, DOM, STOP, TAKE, order lifecycle, account switch or
execution adapter may be necessary infrastructure, but none proves that an entry or exit rule has positive
expectancy.

## 1.1 Status vocabulary

Every normative or research statement uses one of these meanings:

| Status | Meaning |
| --- | --- |
| `ACCEPTED DESIGN` | Repository-approved architecture, boundary or safety invariant. It may still lack implementation. |
| `BASELINE` | Current repository behavior, default or initial comparison point. It is not presumed optimal or profitable. |
| `HYPOTHESIS` | Testable trading claim without sufficient promotion evidence. It must not drive production trading. |
| `NEEDS VALIDATION` | Definition, threshold, parameter or effect that lacks adequate evidence. |

Authority order inside this document is `ACCEPTED DESIGN` over `BASELINE` over research proposals. Evidence may
promote or kill a `HYPOTHESIS`; visual appeal, one chart, an anecdote or a successful trade may not. When this
document conflicts with current execution or risk contracts, the stricter risk boundary wins until an approved
amendment resolves the conflict.

## 1.2 Layer boundary

`ACCEPTED DESIGN`: Geometry and pattern detectors describe structure. Confirmation describes evidence. Strategy
chooses a setup and creates intent. Risk admits or rejects exposure. Execution determines actual order and fill
behavior. No detector owns sizing, STOP, TAKE or execution, and no strategy relabels geometric identity.

---

# 2. CAPITAL AND POSITION MODEL

## 2.1 Working Volume

`ACCEPTED DESIGN` from `CR-TRADING-WORKSPACE-001`:

```text
raw_1_WV = active-account account-wide Wallet (`totalWalletBalance`) × 5%
1_WV     = floor(raw_1_WV) USDT
```

One Working Volume (`WV`) is therefore 5% of the active-account account-wide Wallet before leverage, rounded down
to whole USDT. Leverage never multiplies or otherwise redefines WV. `totalEquity`, `totalAvailableBalance`,
leverage-adjusted buying power and frontend-derived estimates are not the WV base.

Entry quantity is derived from intended WV notional and entry/reference price, then normalized by authoritative
instrument constraints such as `qtyStep`, minimum quantity and minimum notional. Normalization must not silently
increase risk beyond the admitted intent.

## 2.2 Exposure and idea risk

`ACCEPTED DESIGN`: maximum aggregate ROBOT-controlled exposure is `19 WV` per trading account. That cap is not a
trade-level loss budget. Before the first order, each trade idea must define one maximum total risk budget using
entry distribution, structural invalidation, expected costs and worst admissible fill assumptions.

For every position-building method:

* total intended position and maximum loss are fixed before entry;
* all legs belong to the same idea-level budget;
* a later leg must not increase the pre-admitted maximum risk;
* automatic averaging or pyramiding must never become martingale;
* leverage, unrealized loss or prior losing legs must not justify increasing the budget;
* invalidation cancels every remaining entry leg.

`NEEDS VALIDATION`: risk per idea, portfolio heat below the 19-WV exposure ceiling, correlation limits, daily loss
limits, drawdown stops and liquidation-distance constraints.

## 2.3 Pre-trade market eligibility and delisting gate

`ACCEPTED DESIGN`: before every future AUTOPILOT exposure-increasing entry, the robot must perform a fresh
market-eligibility check for the exact Bybit instrument and market/category.

The check must detect authoritative Bybit announcements or exchange state concerning:

* announced delisting or contract removal;
* announced trading suspension or termination;
* scheduled forced settlement;
* contract migration or replacement affecting the current instrument;
* current instrument status that makes normal new trading unavailable.

Announcements must be matched to the exact symbol and relevant market/category. A Spot delisting of the same asset
does not by itself mean that its USDT Linear Perpetual is being delisted.

If a relevant future delisting, termination, forced settlement or equivalent shutdown is known, AUTOPILOT must
reject all new exposure in that instrument. Pattern quality, confirmation score, expected reward and available
capital may not override this gate.

The decision record should preserve the matched symbol, market/category, announcement identity or source,
announcement timestamp, effective event timestamp when available, and the resulting eligibility decision.

`ACCEPTED DESIGN`: inability to establish sufficiently fresh authoritative delisting/eligibility evidence is
fail-closed for autonomous exposure-increasing entry. The fact that a symbol is still quoted or temporarily
tradeable does not override an already-published future delisting or forced-settlement announcement.

If a relevant delisting/shutdown announcement is discovered while a ROBOT-controlled position is already open,
AUTOPILOT must stop adding exposure and raise a separate risk-management event for orderly exit before the exchange
deadline. Exact exit timing and safety buffer are `NEEDS VALIDATION`.

`NEEDS VALIDATION`: authoritative Bybit announcement source/API or feed, polling cadence, cache lifetime,
acceptable evidence freshness, event taxonomy, symbol matching, amended/cancelled announcement handling and the
required exit buffer before effective delisting/settlement time.

---

# 3. CURRENT PATTERN UNIVERSE

## 3.1 Repository baseline

The active Wedge layer recognizes the following exact labels:

| Pattern | Status | Repository geometry | Direction bias | Current confirmation baseline |
| --- | --- | --- | --- | --- |
| `Falling Wedge` | `BASELINE` detector family | Descending converging upper and lower boundaries; GeometryModel supplies trendlines, apex, slopes, compression, touches, quality and validation. | Bullish interpretation. | Upside close beyond the upper boundary; current Confirmation baseline also measures ATR extension, volume, volatility and retest. |
| `Rising Wedge` | `BASELINE` detector family | Ascending converging upper and lower boundaries with the same GeometryModel contract. | Bearish interpretation. | Downside close beyond the lower boundary; current Confirmation baseline measures the same evidence families. |
| `Triangle Compression` | `BASELINE` detector family | Opposing boundary slopes and compression. | Neutral until directional break evidence. | Close beyond either boundary determines LONG or SHORT breakout direction. |
| `Unknown` | `BASELINE` classification outcome | Available geometry is not recognized as one of the supported operational labels. | Neutral. | No trade authorization follows from the label. |

The current Wedge structural score is not a probability or trading expectancy. The current potential estimate for
Falling/Rising Wedge is derived from structure start width and is a `BASELINE` feature, not a proven target.

## 3.2 Required strategy description by pattern

### Falling Wedge

* **Geometry — `BASELINE`:** two descending converging boundaries built and validated by Geometry, then interpreted
  by Wedge; final direction is owned after Geometry construction.
* **Context — `HYPOTHESIS`:** reversal near a broader base/support, continuation after a controlled pullback and
  post-impulse exhaustion may have materially different expectancy and must be separate cohorts.
* **Bias — `BASELINE`:** bullish, without banning a failure-break or separate bearish setup study.
* **Required confirmation — `NEEDS VALIDATION`:** breakout close, distance in ATR, volume context, retest/hold,
  candle evidence, regime and liquidity/cost sufficiency.
* **Invalidation — `HYPOTHESIS`:** confirmed structural break below the admitted lower structure or failed reclaim,
  with a time/volatility expiry defined before entry.
* **Entry modes:** breakout; breakout plus retest; pre-breakout corridor; structural pullback; exhaustion/reversal
  accumulation. Each is a separate setup dataset.
* **Scanner output:** pattern identity and instance/observation identity; geometry and version; upper/lower lines;
  apex; compression; touches; validation; quality; score breakdown; potential; detection/source-candle time;
  timeframe; current boundary prices; confirmation and invalidation evidence.

### Rising Wedge

* **Geometry — `BASELINE`:** two ascending converging boundaries; pattern-aware directional integrity belongs to
  Wedge after direction-neutral Geometry.
* **Context — `HYPOTHESIS`:** topping/reversal, bearish continuation and post-impulse recovery contexts must be
  stratified rather than pooled.
* **Bias — `BASELINE`:** bearish.
* **Required confirmation — `NEEDS VALIDATION`:** downside breakout close, ATR-normalized distance, volume,
  retest/rejection, candle evidence, regime and economic tradability.
* **Invalidation — `HYPOTHESIS`:** accepted recovery above the structural boundary or failed downside breakout,
  plus explicit time/volatility expiry.
* **Entry modes:** breakout; breakout plus retest; pre-breakout corridor; structural pullback; exhaustion/reversal
  accumulation. Results remain mode-specific.
* **Scanner output:** the common fields above plus bearish boundary, breakout and retest evidence.

### Triangle Compression

* **Geometry — `BASELINE`:** opposing trendline compression; neither side is directionally privileged by identity.
* **Context — `HYPOTHESIS`:** continuation, reversal and neutral compression contexts may differ.
* **Bias — `BASELINE`:** neutral until directional evidence.
* **Required confirmation — `NEEDS VALIDATION`:** direction-specific close outside a boundary, ATR distance,
  volume/volatility, acceptance or retest and adequate post-cost reward.
* **Invalidation — `HYPOTHESIS`:** re-entry and acceptance inside the structure, opposite boundary failure or
  expiry near/beyond a no-longer-useful apex.
* **Entry modes:** direction-specific breakout and retest; corridor trading only as a distinct mean-reversion setup.
* **Scanner output:** the common geometry fields and explicit breakout direction/evidence.

### Unknown

* **Geometry — `BASELINE`:** unrecognized/ambiguous structure, not a fourth trade pattern.
* **Context/bias:** neutral.
* **Required confirmation:** none can promote `Unknown` directly into an entry.
* **Invalidation:** not applicable; the observation expires or is reclassified by a later versioned observation.
* **Entry modes:** none under pattern identity alone.
* **Scanner output:** observation identity, geometry/evidence available, reason, ambiguity/rejection diagnostics and
  algorithm version so false negatives and future detector candidates can be researched.

## 3.3 Research candidate families

All items below are `HYPOTHESIS / NEEDS VALIDATION`; none is an active production detector unless current code and
contracts are separately amended.

| Candidate | Geometry and context | Direction bias | Confirmations and invalidation | Required future scanner fields |
| --- | --- | --- | --- | --- |
| Flag | Antecedent directional expansion followed by bounded approximately parallel consolidation; not a Wedge subtype. Countertrend or horizontal drift may occur. | Direction of the antecedent expansion. | Boundary break/acceptance or retest are later events. Excessive retracement, adverse break or channel collapse may invalidate. | Expansion origin/end/direction, displacement, duration, efficiency; channel boundaries/parallelism, retracement, containment, lifecycle, association identity and ambiguity. |
| Head & Shoulders / Inverse H&S | Five ordered pivots `LS, N1, HEAD, N2, RS`; neckline through N1/N2; natural asymmetry is quality rather than automatic failure. | H&S bearish; inverse H&S bullish. | Right-shoulder, neckline breakout and retest are separate entry events. Structural head/shoulder failure, neckline recovery/failure and expiry require calibrated definitions. | Pivot identities/times/prices, neckline geometry, symmetry/quality, prior-trend context, lifecycle and confirmation evidence. |
| Double Top / Double Bottom | Two comparable extrema with an intervening reaction and neckline; requires its own topology/reversal-family research rather than automatic Wedge reuse. | Top bearish; bottom bullish. | Second-extreme rejection, neckline break/acceptance or retest; invalidation beyond the extreme/zone or by expiry. | Extrema and neckline identities, separation, tolerance normalized by volatility, intervening depth, context, confirmation and lifecycle. |
| Candlestick formations | Local OHLC formation evidence including engulfing, hammer, hanging man, morning star and any later versioned catalog. These are evidence/context, not an independent primary trading engine. | Formation- and context-dependent. | Must be closed-candle, location-aware and combined without double-counting correlated evidence. Failure definitions depend on the host setup. | Formation name/version, candle interval and timestamps, component candles, location relative to structure/zone, direction, strength and provenance. |

No exact threshold, weight or probability is accepted for these candidate families. Detector-specific scores must not
be compared as universal probabilities.

---

# 4. ENTRY MODELS

The `setup_id` and `entry_mode` are mandatory cohort keys. Statistics from one mode must never be silently pooled
with another, even when pattern, symbol and direction match.

## 4.1 Breakout entry

Enter only after a defined boundary-break event. `BASELINE`: existing code recognizes a close beyond the relevant
line and evaluates distance in ATR, volume and volatility. `NEEDS VALIDATION`: candle-close requirements,
acceptance duration, maximum chase distance, order type, latency and slippage limits.

## 4.2 Breakout plus retest

Arm after a valid breakout, then require price to revisit the broken boundary/zone and hold/reject in the breakout
direction. Current retest logic is a `BASELINE` implementation reference, not proof of edge. Touch tolerance,
retest window, close/acceptance rule and failure rule require validation.

## 4.3 Pre-breakout / corridor trading

Trade inside a still-valid bounded structure before breakout. This is a distinct mean-reversion/setup type with
different failure and cost characteristics. It must not inherit breakout statistics. Entries require sufficient
distance to the opposing boundary after costs, explicit boundary zones and immediate invalidation rules.

## 4.4 Structural pullback

Enter on a controlled pullback within an established directional setup, using a structural level or zone rather
than an arbitrary percentage. The antecedent impulse, retained structure, pullback depth, resumption evidence and
invalidation must all be recorded.

## 4.5 Exhaustion/reversal accumulation

Build a bounded position near a suspected exhaustion/reversal zone before complete confirmation. This is the
highest uncertainty entry family here. It requires a smaller or otherwise explicitly capped risk budget, structural
invalidation, ladder rules and separate performance reporting. It must not be described as a confirmed reversal
until reclaim/acceptance evidence exists.

---

# 5. POSITION BUILDING / LADDER ACCUMULATION

## H-012 STRUCTURAL LADDER ACCUMULATION

**Status:** `HYPOTHESIS`.

**Claim:** within a defined exhaustion/reversal zone, distributing a pre-limited intended position across a
structure-aware ladder may improve entry quality or risk-adjusted expectancy versus one full entry, without
increasing the original maximum idea risk.

Binding research invariants:

* total intended position and maximum risk are determined before the first leg;
* subsequent legs consume the same budget and never increase maximum allowed risk;
* the ladder is not martingale: adverse movement does not unlock extra capital or geometric size escalation;
* structural invalidation cancels unfilled legs and initiates the defined exit response for filled exposure;
* spacing derives from volatility or market structure, not arbitrary equal price percentages;
* costs, partial fills, gaps and the worst filled-leg combination are included in admission.

`BASELINE` research example only:

```text
1 WV total = 0.2 WV + 0.3 WV + 0.5 WV
```

These weights are not optimized and carry no preference over alternatives. Compare equal spacing, structural-level
spacing and ATR-based spacing against single-entry control. Measure average entry, MAE, MFE, full/partial fill
probability, expectancy after costs, drawdown and tail loss. Stratify by pattern, entry mode and regime.

---

# 6. POST-IMPULSE MIRROR RANGE

## H-011 POST-IMPULSE MIRROR RANGE / MIRROR-LEVEL BOUNCE HARVESTING

**Status:** `HYPOTHESIS`.

**Claim:** after a strong directional displacement and exhaustion/recovery sequence, a reclaimed significant area
may become a mirror support/resistance zone; once a sufficiently wide and repeatedly respected high-volatility
range forms, repeated zone reactions may offer multiple positive-expectancy trades after costs.

This claim includes two different opportunities—initial reversal and later repeated-bounce regime—and their
statistics must remain separate.

### A. DISPLACEMENT

Strong directional movement with elevated realized volatility and preferably volume expansion. Required research
features include direction, magnitude, duration, efficiency, ATR-normalized displacement and volume context.

### B. EXHAUSTION_CANDIDATE

Impulse deceleration, rejection or failure to continue. Structural or Fibonacci extension may be confluence.
`ACCEPTED DESIGN`: Fibonacci `1.618` is never an independent trigger.

### C. RECLAIM

Price returns through a significant area. A bullish candidate preferably closes/accepts back above it; a bearish
candidate mirrors this below it. Reclaim tolerance, duration and false-reclaim policy are `NEEDS VALIDATION`.

### D. MIRROR_FORMING

The prior area changes observed function and receives repeated reactions. The boundary is a zone with explicit
volatility/tick tolerance, not an infinitely precise line.

### E. RANGE_VALIDATION

The range must have economically tradable width after fees, funding, slippage and latency; multiple independent
reactions; adequate continuing volatility; identifiable high/low zones; and no active structural invalidation.
Minimum reactions and independence/window definitions are `NEEDS VALIDATION`.

### F. BOUNCE_HARVESTING

For bullish mirror support, seek LONG entries near the lower mirror zone only after the selected confirmation rule.
For bearish mirror resistance, mirror the rule for SHORT. Targets need not be the opposite extreme: fixed-R,
structural and partial exits are separate variants. No entry is admitted below a predefined minimum expected reward
or edge after costs.

### G. INVALIDATION

Invalidate on confirmed structural break, failed reclaim, volatility collapse, economically insufficient range
width or adverse regime change. After invalidation there is no automatic averaging. The setup turns off and a new
formation cycle and identity are required before another entry.

---

# 7. TOUCH-NUMBER DECAY

## H-013 MIRROR LEVEL TOUCH DECAY / TOUCH CONDITIONAL EXPECTANCY

**Status:** `HYPOTHESIS`.

No prior assumption is permitted that the first, second or third touch is best. Each independent bounce event must
record:

* `touch_number`;
* penetration depth relative to the zone and normalized by ATR/zone width;
* rejection magnitude;
* time since previous touch;
* volume at touch and its local baseline;
* local volatility;
* range age;
* MFE and MAE under a versioned observation horizon;
* outcome after fees, funding, realistic slippage and latency.

Expectancy must be reported separately for touch 1, touch 2, touch 3 and touch 4+, with confidence intervals and
sample sizes. The study must test both degradation and maturation explanations and control for range age, regime,
survivorship, changing volatility and event dependence.

---

# 7A. POST-IMPULSE CHANNEL MIDLINE HARVESTING

## H-014 POST-IMPULSE CHANNEL MIDLINE HARVESTING

**Status:** `HYPOTHESIS`.

**Relationship:** distinct setup geometry from H-011, with shared post-impulse context; H-012 may supply a
separately controlled position-building variant. Results must not be pooled across H-011, H-012 and H-014.

**Claim:** when a post-impulse rising or falling channel has economically meaningful width after costs, entry in a
defined lower channel fraction for LONG or upper fraction for SHORT, followed by primary realization near the
midline and an optional runner toward the opposite boundary, may produce better risk-adjusted outcomes than
requiring an absolute channel-extreme entry or always targeting the opposite boundary.

Required setup definition and invariants:

* channel identity requires versioned boundaries, direction, width, midline, lifecycle and structural validity;
* `normalized_channel_position` maps price location within the contemporaneously known channel without future
  boundary information;
* entry zones are expressed as fractions of channel width, normalized for direction, rather than fixed prices;
* the minimum harvestable distance from entry zone to intended realization point must remain positive and meet a
  predefined economic threshold after fees, spread, slippage and latency;
* channel failure, adverse boundary acceptance, loss of fit/structure, expiry and volatility collapse are candidate
  invalidations whose exact rules need validation;
* any ladder follows H-012's pre-limited total position and risk invariants and is analyzed as an explicit variant;
* primary and runner exit quantities are fixed by the tested policy, not optimized after observing the outcome.

Exit-policy candidates are `MID_100`, `MID_70_TOP_30`, `MID_50_TOP_50`, `OPPOSITE_BOUNDARY` and
`TRAIL_AFTER_MID`. Candidate entry bins such as `0–0.20` or `0.20–0.35` of normalized channel width are examples
for research design only, not accepted parameters.

Required comparisons include single entry versus H-012 ladder variants; absolute-extreme versus channel-fraction
eligibility; each exit policy; rising versus falling channels; post-impulse regime strata; full/partial fill rates;
and expectancy, MAE, MFE, drawdown and tail loss after costs.

---

# 7B. ROUNDED DECELERATION BREAKOUT

## H-015 ROUNDED DECELERATION BREAKOUT / PARABOLIC COMPRESSION REVERSAL

**Status:** `HYPOTHESIS`.

**Classification:** `NEW_SETUP`. It shares post-bearish-impulse context with H-011 and H-014 but does not require a
mirror level, range or approximately linear channel. It must remain a separate cohort from linear wedge/channel and
ordinary momentum-deceleration setups.

**Formalized claim:** after a strong bearish displacement, a decision-time sequence of diminishing downside
velocity, flattening fitted slopes and contracting structure may identify a reversal/compression regime in which a
bullish structural breakout has distinguishable post-cost expectancy versus matched non-curved controls. The study
must determine whether nonlinear curvature adds information beyond ordinary bearish-momentum deceleration and
compression; neither effect is assumed.

Competing explanations:

* `TRUE_CURVATURE`: nonlinear fitted geometry or curvature contributes incremental predictive information after
  controlling for displacement, slope decay, volatility, compression and regime;
* `DECELERATION_ONLY`: apparent curvature adds no usable information; any effect is explained by ordinary downside
  velocity decay and compression.

The visual arc is not a detector or ground-truth label. Candidate fit methods, windows, derivatives and thresholds
are `NEEDS VALIDATION` and must use only information available at decision time. Required features include rolling
high/low slopes; slope decay; first and second derivatives/curvature of versioned fits; downside velocity decay;
successive swing-amplitude contraction; ATR and range state; swing timing; volume evolution; rejection magnitude;
post-impulse age; breakout displacement, volume ratio and distance beyond the fitted structural boundary; retest;
BTC/broad-market regime; liquidity and spread.

Entry variants are `BREAKOUT_CLOSE`, `BREAKOUT_INTRABAR`, `BREAKOUT_RETEST` and
`EARLY_COMPRESSION_ENTRY`. None is a production/default mode, and their statistics must remain separate.
Invalidation candidates are a new structural low after flattening, renewed downside acceleration, failed breakout,
failed reclaim, insufficient follow-through and adverse regime change.

Exit comparisons include fixed R, nearest structural resistance, measured compression height, partial take plus
runner, volatility-adjusted trailing and time-based exit. No universal TAKE is accepted.

Required controls are matched strong bearish displacement followed by: ordinary sideways consolidation; a linear
descending channel; a wedge; deceleration without meaningful curvature; and random volatility/liquidity-matched
windows. Promotion requires the common historical, untouched holdout, walk-forward, after-cost robustness,
parameter-sensitivity and PAPER/shadow gates. Kill the hypothesis if curvature is not incrementally distinguishable,
the definition is unstable or look-ahead-dependent, or post-cost/tail-risk results fail the common gates.

### BTWUSDT 1m observation

**Status:** `OBSERVATION / CASE STUDY SOURCE`, not detector ground truth or evidence of edge.

User-reported observation: after a strong downside impulse, BTWUSDT on 1m formed a visually rounded descending
compression whose negative slope appeared to flatten over time, followed by a hypothesized bullish breakout
opportunity. No separate screenshot file was available for repository capture in this update. No example price,
subjective arc thickness or hand-drawn boundary is promoted into the generalized setup.

---

# 8. AKEUSDT CASE STUDY

**Status:** `OBSERVATION / HYPOTHESIS SOURCE`, not proof.

User observation: after a strong fall from a local high, AKEUSDT formed a local one-minute box/base near a
Fibonacci extension around `1.618`, recovered, then developed an approximate mirror-support area. Price reportedly
returned and bounced several times, with visually observed moves around 5% during high volatility.

No exact level, percentage, Fibonacci coefficient or reaction count from this example is a universal strategy
parameter. The observation may suffer hindsight, selection and execution-cost bias. It does not establish
profitability.

Research use:

* preserve the original chart and observation-time annotation under
  `training/reference_patterns/AKEUSDT/<CASE_ID>/` if separately supplied and authorized;
* preserve later outcome separately without rewriting the initial interpretation;
* label initial reversal and later repeated-bounce events separately;
* preserve rising-channel interpretation as an H-014 candidate without replacing the H-011 mirror-range
  interpretation; competing labels remain available for later arbitration;
* use the case to seed detector and event definitions, then validate on a broad multi-symbol dataset containing
  positive, negative and ambiguous examples.

Primary question: can the system detect both the initial reversal candidate and the subsequent repeated-bounce
regime without using future information?

---

# 9. TRADE MANAGEMENT

Trade management variants are independently testable policy components. They must be versioned and compared on
the same eligible-entry cohorts, including costs and censored/unresolved outcomes.

| Mechanism | Research definition |
| --- | --- |
| Initial structural stop | Stop derived from the setup's structural invalidation zone plus explicit tolerance and execution assumptions. |
| Hard invalidation | Evidence that the setup premise no longer holds; exits/locks apply even if a softer stop model disagrees. |
| Fixed-R take | Exit at a predetermined multiple of initial admitted risk. R definition must remain stable after entry. |
| Structural target | Target from an opposing zone, pattern structure or liquidity barrier; repository pattern potential is only a baseline candidate. |
| Partial take | Reduce predefined fractions at predefined conditions; remaining-risk accounting must be explicit. |
| Break-even | Move protection to a versioned cost-aware level after a specified event; never assume zero-price PnL equals zero after fees. |
| Trailing stop | Trail by a defined price/volatility distance. |
| Trailing by structure | Trail behind confirmed pivots, zones or other versioned structural evidence. |
| Time stop | Exit when the expected realization window expires without sufficient progress. |
| Volatility contraction exit | Exit or reduce when tradable movement collapses according to a calibrated measure. |

If `STOP -2%` or `TAKE +3%` appears in UX/PAPER configuration, it is a `BASELINE / DEFAULT`, not evidence of an
optimal or profitable strategy. Current Terminal protection mechanics and approved proposal behavior do not select
strategy parameters.

---

# 10. MARKET REGIME FILTERS

Each eligible event stores the regime classification available at decision time. Exact classifiers and thresholds
are `NEEDS VALIDATION`.

* **Trend:** direction and strength across the setup and one or more higher horizons.
* **Volatility:** realized/ATR state, expansion/contraction and percentile relative to the instrument.
* **Liquidity:** executable depth over the intended path, gaps and concentration zones; public L2 is aggregated
  liquidity, not exact queue truth.
* **Spread:** absolute, basis-point and tick-normalized spread at decision and execution.
* **Volume:** local/historical context, expansion/contraction and reliability.
* **Post-impulse state:** displacement, exhaustion, reclaim, mirror formation or ordinary market.
* **BTC/market correlation context:** benchmark direction, beta/correlation stability and market-wide impulse.
* **Abnormal/news-like volatility:** discontinuous, liquidation-like or event-like behavior maintained as a
  separate category; it may be an exclusion, risk-reduction or dedicated cohort, never silently ordinary data.

Filters must be tested for incremental out-of-sample value. A plausible narrative alone cannot justify excluding
losing observations or selecting regimes after the outcome.

---

# 11. TRADE AND SETUP STATE MACHINES

## 11.1 Research trade lifecycle

```text
CANDIDATE
  -> ARMED
  -> ENTRY_PENDING
  -> ACTIVE
  -> MANAGING
  -> PARTIAL_EXIT
  -> EXIT_PENDING
  -> CLOSED
```

`CANDIDATE` has a detected setup but no admitted entry. `ARMED` has satisfied a versioned setup policy and awaits
its trigger. `ENTRY_PENDING` represents order uncertainty and cannot be treated as a fill. `ACTIVE` requires
authoritative fill/position evidence. `MANAGING` applies only approved risk/exit policy. `PARTIAL_EXIT` retains an
authoritative remainder. `EXIT_PENDING` preserves ambiguity and prohibits blind retry. `CLOSED` requires
authoritative flat/outcome evidence.

Alternative transitions include `CANDIDATE/ARMED -> INVALIDATED|EXPIRED`, rejected entry back to an explicitly
defined state, and uncertain execution to `UNKNOWN/RECONCILING` under execution contracts. State names here are a
research model and must be reconciled with domain execution states before implementation.

## 11.2 Mirror-range lifecycle

```text
DISPLACEMENT
  -> EXHAUSTION_CANDIDATE
  -> RECLAIM
  -> MIRROR_FORMING
  -> RANGE_ACTIVE
  -> RANGE_DEGRADED
  -> INVALIDATED
```

`RANGE_DEGRADED` allows observation or risk reduction but no assumption that new entries remain valid. A materially
new formation after `INVALIDATED` receives a new setup instance; history is never rewritten into one continuous
successful range.

---

# 12. HYPOTHESIS REGISTRY

No authoritative numbered registry for `H-001` through `H-010` was found at version 1.0. Those identifiers remain
`RESERVED / UNKNOWN`; they are not backfilled from loosely related historical notes. New entries require an
explicit unique ID and evidence plan.

| ID | Name | Status | Setup | Claim | Required data | Validation method | Promotion criterion | Kill criterion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H-001–H-010 | Reserved / unknown | `RESERVED` | Unknown | No claim recorded. | None until defined. | Not applicable. | Approved, non-duplicative hypothesis record. | Identifier remains unused if no authoritative source is recovered. |
| H-011 | Post-Impulse Mirror Range / Mirror-Level Bounce Harvesting | `HYPOTHESIS` | Post-impulse reversal and repeated range bounce | A reclaimed mirror zone in a validated volatile range can support repeatable post-cost bounce trades. | State transitions, zone/range geometry, reactions, entries/exits, regimes, costs, MAE/MFE. | Event study, mode-specific historical test, holdout, walk-forward, PAPER/shadow. | Positive robust post-cost expectancy and controlled tail risk across held-out symbols/regimes, followed by PAPER and shadow gates. | Non-positive robust expectancy, economically untradeable width, unstable definition or unacceptable tail loss. |
| H-012 | Structural Ladder Accumulation | `HYPOTHESIS` | Exhaustion/reversal accumulation | A fixed-risk structural/volatility ladder improves risk-adjusted outcomes versus a single-entry control. | Leg plan/fills, structural levels, ATR, average entry, risk, MAE/MFE, costs and outcomes. | Matched-event comparison of equal, structural, ATR and single-entry variants with bootstrap uncertainty. | Repeatable out-of-sample improvement without higher admitted/tail risk and with operationally feasible fills. | No improvement after costs, increased tail risk, excessive missed/full-fill dependency or rule instability. |
| H-013 | Mirror Level Touch Decay / Touch Conditional Expectancy | `HYPOTHESIS` | H-011 bounce events | Bounce expectancy changes as a function of touch number; direction of change is unknown. | Touch fields in section 7 plus range/regime controls. | Conditional event study for touch 1/2/3/4+, clustered uncertainty, holdout and sensitivity tests. | Stable, actionable conditional effect with adequate sample size and out-of-sample replication. | No distinguishable effect, effect disappears under controls/costs, or sample dependence makes it unusable. |
| H-014 | Post-Impulse Channel Midline Harvesting | `HYPOTHESIS` | Post-impulse rising/falling channel | Channel-fraction entry with midline-first realization may outperform absolute-extreme entry or full opposite-boundary targeting after costs. | Channel version/boundaries/midline, normalized position, entry bin, ladder variant, exit policy, invalidation, fills, costs, MAE/MFE and outcomes. | Mode-specific event study and matched policy comparison across holdout symbols/regimes, then walk-forward and PAPER/shadow gates. | Robust positive post-cost expectancy with acceptable tail risk and an out-of-sample advantage over frozen control policies. | No robust advantage, insufficient harvestable width, unstable/no-look-ahead channel definition or unacceptable fill/tail-risk behavior. |
| H-015 | Rounded Deceleration Breakout / Parabolic Compression Reversal | `HYPOTHESIS` | Post-bearish-impulse nonlinear deceleration/compression | Measured curvature/deceleration followed by bullish structural breakout may have distinguishable post-cost expectancy, and curvature may or may not add information beyond deceleration alone. | Versioned fit/derivatives, slopes and decay, velocity, swing/ATR/range/volume contraction, breakout/retest, regime/liquidity, entry/exit variant, MAE/MFE, costs and outcome. | Curvature-versus-deceleration ablation and matched-control event study, then holdout, walk-forward, sensitivity and PAPER/shadow. | Robust post-cost result plus stable out-of-sample incremental value for the retained feature model with acceptable tail risk. | No incremental/stable effect, look-ahead-dependent geometry, non-robust parameters, or failed post-cost/tail-risk gates. |

---

# 13. VALIDATION METHODOLOGY

## 13.1 Dataset and leakage controls

Build an immutable, versioned event dataset from information available at detection/decision time. Preserve all
eligible events, not only notified, traded or successful cases. Store algorithm/config/data versions and separate
features-at-decision from later outcome labels.

`LOOK_AHEAD_LEAKAGE_FORBIDDEN`: future candles, final extrema, later range boundaries, realized outcome or hindsight
labels must never alter the historical decision features. Closed-candle rules apply wherever the setup requires
closed candles. Intrabar/microstructure strategies need event-time ordering and explicit latency.

Use chronological train, validation and untouched holdout periods; walk-forward evaluation; purging/embargo where
overlapping horizons leak information; per-symbol and cross-symbol reporting; and regime stratification. Symbol
selection and delist/survivorship treatment must be documented.

## 13.2 Execution realism

Include maker/taker fees, funding, spread, realistic slippage, partial fills, minimum/step constraints and explicit
latency assumptions. Market simulation must use executable-side liquidity where available. A Limit touch is not a
guaranteed fill. Report results before and after all costs, with the after-cost result controlling promotion.

## 13.3 Robustness

Freeze primary definitions and metrics before holdout evaluation. Test parameter neighborhoods and report
sensitivity surfaces rather than selecting a single lucky point. Correct for repeated trials/model selection where
material. Use bootstrap or Monte Carlo when appropriate, preserving serial/event clustering and tail dependence.
Compare every complex rule against simple baselines and ablations.

## 13.4 Required metrics

At minimum report:

* expectancy per trade and per unit risk, with uncertainty;
* profit factor;
* win rate;
* average win and average loss;
* maximum drawdown and drawdown duration;
* MAE and MFE distributions;
* tail loss and adverse percentiles;
* exposure time;
* turnover and number of independent events;
* results after fees, funding, slippage and latency;
* Sharpe/Sortino only where return sampling and distribution make them meaningful.

Also report concentration by symbol, period, regime, side, setup, entry mode and touch number. Aggregate performance
must not conceal a failing subgroup that controls live risk.

---

# 14. PROMOTION PIPELINE

```text
HYPOTHESIS
  -> HISTORICAL_RESEARCH
  -> HOLDOUT_PASS
  -> WALK_FORWARD_PASS
  -> PAPER
  -> SHADOW
  -> TIGHTLY_GATED_MICRO_LIVE
  -> PRODUCTION_CANDIDATE
```

Each transition requires a versioned definition, required dataset, predefined metrics, objective gate result,
residual risks and explicit authorization. Failure returns the hypothesis to revision or kills it; it does not
permit tuning on the holdout and reusing the same data as untouched evidence.

`MICRO_LIVE` requires a separately authorized real-money gate, hard exposure/loss limits, kill switch,
reconciliation and monitoring. `PRODUCTION_CANDIDATE` is still subject to risk and deployment acceptance. No idea
becomes production strategy because it looks compelling on one chart or worked once.

---

# 15. RESEARCH DATA MODEL

The preferred research event is immutable or append-only, with stable IDs and explicit schema/algorithm versions.
Fields below are desired before implementation design; names and storage are not yet contracts.

## 15.1 Identity and provenance

* `event_id`, `candidate_id`, `setup_instance_id`, `trade_id`;
* `symbol`, `timeframe`, `setup_id`, `hypothesis_id`, `pattern`, `pattern_version`;
* `entry_mode`, `regime`, `direction`;
* `detection_time`, `source_candle_time`, `signal_time`, `order_time`, `fill_time`;
* data source, detector/config/schema versions and feature provenance.

## 15.2 Structure, context and intent

* geometry/boundary references, validation, quality and confirmations;
* `entry`, intended and actual fill price;
* `stop`, hard invalidation and `target`;
* intended `WV`, admitted idea risk and aggregate exposure;
* `ladder_plan`, `ladder_leg`, intended/filled leg quantity;
* mirror level/zone lower and upper bounds;
* range high/low, range age and width after expected costs;
* channel boundaries, midline, width, direction, lifecycle and `normalized_channel_position`;
* channel entry-zone/bin, exit-policy variant, primary/runner allocation and harvestable distance after costs;
* rounded-deceleration fit method/type, fit window/version, high/low slope start/end, slope decay, first/second
  derivative or curvature, downside-velocity decay, swing-amplitude contraction and post-impulse age;
* breakout type/displacement/distance, breakout volume ratio, retest flag and H-015 matched-control class;
* `touch_number`, penetration, rejection and time since previous touch;
* ATR/realized volatility and volume context;
* spread, liquidity/depth context, BTC/market context and abnormal-volatility flag.

## 15.3 Execution and outcome

* order types, acknowledgements, partial fills, latency and ambiguity/reconciliation states;
* MAE/MFE values and their versioned horizons;
* exit time, exit price, exit mechanism and remaining quantity;
* fees, funding, slippage and realized result before/after costs;
* normalized R outcome, exposure time and turnover contribution;
* invalidation/expiry/exit reason;
* outcome censoring and data-quality flags.

Detection-time fields must remain immutable after the outcome. Corrections append a versioned amendment with
reason rather than overwriting what the system knew.

---

# 16. OPEN RESEARCH BACKLOG

No item below authorizes code.

## P0 — definitions and evidence capture

* formalize H-011 mirror-zone detector inputs, zone tolerance and formation identity;
* formalize economically valid range width, independent reactions and invalidation;
* define event dataset, timestamps, eligible-event denominator and cost/latency model;
* define H-013 touch numbering, independence, penetration and outcome horizons;
* define H-012 structural ladder budget, spacing variants and single-entry control;
* formalize H-014 channel identity, no-look-ahead normalized position, economic-width gate and invalidation;
* formalize H-015 decision-time fit, curvature/deceleration features, competing models and matched-control labels;
* complete an end-to-end Falling Wedge strategy definition with separate context and entry-mode cohorts;
* preserve the AKEUSDT source/reference case only if original evidence and case identity are supplied.

## P1 — comparative validation

* compare breakout, breakout-plus-retest and pre-breakout/corridor entries without cohort mixing;
* evaluate structural pullback and exhaustion/reversal accumulation separately;
* optimize/compare trade-management mechanisms only after a stable eligible-entry dataset exists;
* compare H-014 entry fractions and `MID_100`, `MID_70_TOP_30`, `MID_50_TOP_50`,
  `OPPOSITE_BOUNDARY`, `TRAIL_AFTER_MID` policies, including H-012 ladder interaction;
* compare H-015 entry/exit variants and test `TRUE_CURVATURE` against `DECELERATION_ONLY` plus the five frozen
  matched-control families;
* stratify by trend, volatility, liquidity, volume, spread, BTC context and abnormal volatility;
* define Flag, HS/IHS and Double Top/Bottom labeled datasets and detector-family acceptance gates;
* test candlestick evidence for incremental value and correlated-feature double counting.

## P2 — later extensions

* candidate association/arbitration across overlapping and nested patterns;
* liquidity and public-trade evidence for entry/management timing;
* portfolio correlation, allocation and dynamic exposure research below the 19-WV cap;
* calibrated probability/expectancy models only after deterministic baselines and leakage controls exist;
* shadow and micro-live experiment design with operational kill criteria.

---

# 17. RULE AGAINST STRATEGY DRIFT

Every new trading idea follows this mandatory sequence:

```text
USER OBSERVATION / CASE STUDY
  -> RELATED OR NEW HYPOTHESIS ID
  -> REQUIRED DATASET
  -> PREDEFINED TEST PROTOCOL
  -> STATISTICAL RESULT
  -> PROMOTION, REVISION OR KILL
```

An observation records what was seen and when. It does not rewrite prior data, claim causality or become a rule.
The hypothesis states a falsifiable claim, population, setup and expected effect. The protocol defines eligible
events, splits, metrics, costs and promotion/kill criteria before final evaluation. Only a statistical PASS through
the promotion pipeline may change strategy status.

Any material change to setup identity, entry, sizing, risk, exit or promotion criteria creates a new version and
requires fresh validation. Production behavior must remain reproducible from the promoted version; experimental
features stay default-off and may not silently drift into admission.

---

# 18. OPEN QUESTIONS

1. What exact authoritative capital field should future AUTOPILOT use across PAPER and each Bybit account type, and
   at what refresh/fencing points?
2. What is the per-idea maximum loss and portfolio heat policy beneath the 19-WV exposure ceiling?
3. What deterministic event defines displacement end, exhaustion, reclaim acceptance and a new mirror-range cycle?
4. How many reactions count as independent, and how are zone width and reaction tolerance normalized?
5. Which entry confirmation and minimum post-cost reward rule is primary for each H-011 side and touch cohort?
6. How are overlapping range touches clustered so confidence intervals do not treat dependent events as independent?
7. What outcome horizon and censoring policy define MAE/MFE and a successful bounce?
8. Which single-entry and ladder variants are frozen as H-012 controls before holdout evaluation?
9. Which deterministic, no-look-ahead channel construction and normalization method is admissible for H-014?
10. Which fit family, window and curvature/deceleration ablation can identify H-015 without visual-label or
    look-ahead leakage?
11. Which archived notes, if any, legitimately own H-001 through H-010? Until recovered, the IDs remain reserved.
12. What minimum sample, effect size, uncertainty and tail-risk gates are required for each promotion stage?

---

# 19. REPOSITORY BASELINE TRACEABILITY

Version 1.0 was reconciled against these current facts:

* `DOCUMENTS/ARCHITECTURE.md`: Geometry/Wedge ownership and current pattern labels;
* `DOCUMENTS/PROJECT_CONTRACTS.md`: Geometry, Validation, Pattern and Signal boundaries;
* `DOCUMENTS/CHANGE_REQUESTS/CR-SCANNER-GEOMETRY-001.md`: direction-neutral Geometry and pattern-aware Wedge
  integrity decisions;
* `DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md`: candidate detector families, candlestick evidence,
  setup separation, Paper/realtime research and no implementation authorization;
* `DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md`: WV, 19-WV, account/risk/execution and Terminal mechanics;
* `wedge/classifier.py`, `wedge/detector.py`, `wedge/result.py`, `wedge/potential.py`: current labels, biases,
  result fields and structural-potential baseline;
* `confirmation.py` and `breakout.py`: current breakout, ATR, volume, volatility and retest baselines;
* `training/reference_patterns/`: canonical case-study storage and before/after integrity rules.

Version 1.1 adds the H-014 post-impulse channel research hypothesis and strategy-idea capture support.
Version 1.2 adds H-015 and the BTWUSDT 1m observation with curvature-versus-deceleration controls. These revisions
change documentation only and create no detector, signal, order, risk or runtime behavior.

# END_OF_DOCUMENT
