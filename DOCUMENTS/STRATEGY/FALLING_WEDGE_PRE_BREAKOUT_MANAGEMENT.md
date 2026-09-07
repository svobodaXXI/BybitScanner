# Falling Wedge — Pre-Breakout Lower-Edge Entry and Breakout Management

Document Type: TRADING_STRATEGY_RESEARCH_HYPOTHESIS

Hypothesis ID: H-016

Status: HYPOTHESIS / NEEDS VALIDATION

Authority: research documentation only; this document does not authorize AUTOPILOT, PAPER, LIVE, sizing, STOP, TAKE, or execution changes.

Related authoritative specification: `DOCUMENTS/TRADING_STRATEGY_SPEC.md`

---

# 1. PURPOSE

Capture the proposed Falling Wedge scenario in which a LONG position is opened before breakout from the lower edge of an already mature wedge, then managed differently depending on whether the upper-edge breakout is ordinary/strong or explosive.

This scenario is a distinct entry-and-management cohort. Its results must not be silently pooled with breakout-only, breakout-plus-retest, or generic corridor-trading results.

All numeric fractions and thresholds below are working research parameters, not proven or production-approved values.

---

# 2. SETUP CONTEXT

Pattern: `Falling Wedge`.

Direction bias for this hypothesis: LONG.

Entry family: `PRE_BREAKOUT_LOWER_EDGE`.

The wedge must already be substantially formed. Price is near the lower boundary while the structure is approaching its later formation stage / apex region.

The intended advantage of the early entry is twofold:

1. obtain a favorable entry close to structural invalidation while the price is still inside the wedge;
2. retain participation if the move develops directly into an upside breakout.

The early entry does not imply that breakout is guaranteed. Until the upper boundary is broken, the trade remains a pre-breakout trade inside a still-valid wedge.

`NEEDS VALIDATION`:

* deterministic wedge-maturity definition;
* allowed distance from price to the lower edge;
* exact apex-distance or lifecycle gate;
* confirmation trigger for the lower-edge entry;
* initial position size;
* initial stop / structural invalidation logic;
* minimum economically viable distance to the upper boundary after costs.

---

# 3. INITIAL ENTRY

When a mature Falling Wedge remains structurally valid and price reaches an admissible zone near the lower boundary, the strategy may open a LONG position before breakout.

The first entry is treated as one idea-level risk budget. Any later addition after breakout/retest belongs to the same idea and must respect the pre-admitted risk constraints from the main strategy specification.

For the management examples below, `1 WV` (`1 РО`) is used as the normalized full working position. This is a research normalization, not a statement that every qualifying setup must enter with exactly 1 WV.

---

# 4. MOVE TOWARD THE UPPER EDGE

If price moves from the lower edge toward the upper edge while remaining inside the wedge, the position continues to be managed as a pre-breakout position.

No breakout-management rule activates until an actual upper-edge breakout event has been detected according to the versioned breakout definition.

---

# 5. DIRECT BREAKOUT WITHOUT PRE-BREAKOUT ACCUMULATION

A key scenario is a direct upside break of the upper wedge boundary without prolonged accumulation immediately below the edge.

Management depends on breakout strength.

The strategy must distinguish at minimum:

* `NORMAL` breakout;
* `STRONG` breakout;
* `EXPLOSIVE` breakout.

The exact classifier is `NEEDS VALIDATION`.

Candidate inputs for a future `Breakout Strength Score` include:

* breakout-candle range relative to ATR;
* breakout volume relative to the local volume baseline;
* speed of price displacement after crossing the upper edge;
* depth and speed of any immediate pullback;
* persistence of closes above the broken edge;
* consecutive directional candles;
* close location within the candle range, especially close-to-high behavior;
* candle-range expansion;
* absence of rapid acceptance back inside the wedge.

These features are candidates only. No threshold or weight is accepted yet.

---

# 6. NORMAL / STRONG BREAKOUT BRANCH

Working hypothesis: after a clear but non-explosive upside breakout, realize a large part of the early-entry profit while retaining a smaller position for continuation and possible retest.

Research baseline example:

```text
initial position:          1.00 WV
first realization:        0.75 WV
remaining position:       0.25 WV
```

After this realization, protection for the remaining position is moved at least to a cost-aware breakeven zone.

`Breakeven` must account for actual fees, funding where relevant, slippage and fill price. It must not be defined as merely the nominal entry price.

The exact `75% / 25%` split is a hypothesis and must be compared against alternatives.

---

# 7. RETEST AND RELOAD

After the breakout, price may return toward the broken upper wedge boundary.

A return to the edge is not sufficient by itself to add exposure. The strategy must distinguish a valid retest from a failed breakout.

Candidate valid-retest sequence:

```text
REVISIT_BROKEN_EDGE
  -> HOLD / REJECTION / RECLAIM
  -> CONTINUATION_TRIGGER
```

Candidate failure evidence includes:

* meaningful acceptance back inside the wedge;
* deep adverse penetration beyond the retest tolerance;
* failed reclaim;
* structural deterioration inconsistent with the original bullish premise.

If the retest is confirmed and the idea remains valid, the position may be rebuilt up to the normalized full working size.

Research baseline example:

```text
remainder after first take:  0.25 WV
retest addition:             up to 0.75 WV
maximum resulting position:  1.00 WV
```

The addition must not cause the idea to exceed its pre-admitted maximum risk. A retest addition is not martingale and is not justified merely because price moved against the open remainder.

`NEEDS VALIDATION`:

* retest-zone tolerance;
* maximum time from breakout to retest;
* hold/rejection/reclaim definition;
* continuation trigger;
* failed-breakout definition;
* exact reload quantity and its relationship to current stop distance and remaining risk budget.

---

# 8. MAIN EXIT DISTRIBUTION AFTER SUCCESSFUL RETEST

Working hypothesis: after a successful breakout/retest and continuation, avoid distributing the rebuilt position too early.

Use the versioned Falling Wedge potential estimate only as a research reference, not as a proven target.

When approximately 70% of the expected move has been completed — equivalently, when roughly 30% of the estimated potential remains — begin the main distribution phase.

Research baseline for a 1.00 WV position:

```text
first distribution leg:   0.25 WV
second distribution leg:  0.25 WV
third distribution leg:   0.25 WV
runner:                   0.25 WV
```

The first three legs are placed as an approximately even realization grid over the remaining final part of the expected move.

The exact definition of `70% completed`, the potential model, and the spacing of the three exits are `NEEDS VALIDATION`.

Required comparisons should include alternative start points, alternative fractions and structural rather than purely proportional exit grids.

---

# 9. RUNNER

The final quarter is intended to capture moves that materially exceed the normal measured Falling Wedge potential.

Working principle: once the primary 75% distribution has completed, the runner does not require a fixed price target.

Candidate runner exits:

* volatility-adjusted trailing stop;
* trailing behind confirmed structural pivots;
* confirmed reversal;
* loss of trend structure;
* separately defined exhaustion event.

The trailing method and distance are `NEEDS VALIDATION`.

The runner exists specifically so that rare large trend extensions can contribute disproportionately to expectancy instead of being fully capped by the standard measured target.

---

# 10. EXPLOSIVE BREAKOUT BRANCH

A direct breakout may become sufficiently strong that immediate realization of approximately 75% would exit too much of the position too early.

For this case the strategy enters a distinct management state:

`EXPLOSIVE_BREAKOUT`.

Working principles:

* do not automatically realize the normal 75% fraction immediately;
* allow the impulse more room to develop;
* move the stop into positive territory as the move becomes sufficiently established;
* do not place that stop so close to current price that ordinary impulse volatility removes the position;
* delay large-scale profit distribution while momentum remains exceptional;
* begin larger realization only after measurable weakening, structural deterioration, or another versioned exit condition.

The objective is to protect a profitable trade without truncating unusually strong continuation.

A positive stop for this branch is not intended to be a tight price-following stop. The distance must be volatility/structure aware so that price is allowed to "breathe".

`NEEDS VALIDATION`:

* threshold between `STRONG` and `EXPLOSIVE`;
* minimum profit/progress before moving the stop above breakeven;
* stop-distance model during explosive momentum;
* momentum-decay definition;
* whether partial realization still occurs during explosive momentum and, if so, at what fractions;
* transition from explosive management back to ordinary distribution or runner management.

---

# 11. CANDIDATE STATE MACHINE

```text
FALLING_WEDGE_MATURE
  -> LOWER_EDGE_ENTRY_ARMED
  -> PRE_BREAKOUT_LONG
  -> UPPER_EDGE_APPROACH
  -> BREAKOUT_CLASSIFICATION
       -> NORMAL_OR_STRONG
            -> PRIMARY_TAKE
            -> REMAINDER_PROTECTED
            -> RETEST_PENDING
                 -> RETEST_FAILED -> EXIT / INVALIDATION
                 -> RETEST_CONFIRMED
                      -> RELOAD_UP_TO_1_WV
                      -> CONTINUATION
                      -> DISTRIBUTION_ZONE
                      -> TAKE_1
                      -> TAKE_2
                      -> TAKE_3
                      -> RUNNER
       -> EXPLOSIVE
            -> PROFIT_PROTECTION
            -> MOMENTUM_HOLD
            -> MOMENTUM_DECAY / STRUCTURAL_EXIT / TRAILING
```

Execution ambiguity, partial fills and reconciliation remain governed by the repository execution contracts and must not be hidden by this research state model.

---

# 12. REQUIRED RESEARCH FIELDS

A future event dataset for H-016 should preserve at minimum:

* `setup_instance_id`;
* `pattern = Falling Wedge`;
* wedge lifecycle / maturity features;
* apex distance;
* upper/lower boundary prices at every decision event;
* normalized price distance to each boundary;
* entry mode = `PRE_BREAKOUT_LOWER_EDGE`;
* entry time, intended and actual entry price;
* initial WV and admitted idea risk;
* initial stop and structural invalidation reference;
* breakout timestamp and breakout-edge price;
* breakout-strength features and classification;
* ATR, realized volatility and volume context;
* first-take trigger, intended fraction and actual fills;
* remaining quantity and cost-aware breakeven/profit-stop level;
* retest timestamp, penetration depth, hold/reclaim evidence and result;
* reload trigger, quantity and resulting total position;
* potential model/version and potential completion fraction;
* each distribution-leg trigger and fill;
* runner quantity and trailing-policy version;
* MAE/MFE before breakout, after breakout, during retest and after continuation;
* final exit reason;
* fees, funding, spread, slippage, latency and realized result after costs;
* regime, liquidity and BTC/broad-market context.

---

# 13. VALIDATION REQUIREMENTS

H-016 must be compared against frozen controls rather than evaluated only on successful examples.

Required comparisons include:

* lower-edge pre-breakout entry versus breakout-only entry;
* lower-edge pre-breakout entry versus breakout-plus-retest entry;
* `75/25` first realization versus alternative splits;
* immediate normal distribution versus explosive-breakout hold logic;
* retest reload versus no reload;
* reload to 1 WV versus smaller rebuilt exposure;
* distribution beginning near 70% potential versus alternative start points;
* three-part grid versus structural exits;
* 25% runner versus alternative runner fractions or no runner;
* volatility trailing versus structural trailing.

Report expectancy after all costs, profit factor, win rate, average win/loss, drawdown, MAE/MFE, tail loss, exposure time, fill quality and performance by regime/symbol/timeframe.

Promotion requires the same untouched holdout, walk-forward, PAPER/shadow and risk gates defined in `DOCUMENTS/TRADING_STRATEGY_SPEC.md`.

Kill or revise the hypothesis if the early-entry advantage disappears after costs, the management complexity does not improve out-of-sample expectancy/risk, the explosive classifier is unstable, or retest reload materially worsens tail risk.

---

# 14. OPEN QUESTIONS

1. What exact event makes a Falling Wedge mature enough for a lower-edge pre-breakout entry?
2. What lower-edge zone and entry confirmation should be required?
3. Where is the initial structural stop and what invalidates the idea before breakout?
4. What initial WV is admissible as a function of stop distance and risk budget?
5. What objective features separate `NORMAL`, `STRONG` and `EXPLOSIVE` breakout states?
6. Is `75%` the correct first realization fraction for ordinary strong breakout?
7. What constitutes a successful retest versus a failed breakout?
8. How much may be re-added while keeping total idea risk within its original budget?
9. How should Falling Wedge potential be measured without look-ahead leakage?
10. At what completion fraction should distribution begin?
11. How should the three main exit legs be spaced?
12. What trailing model best preserves an extended runner?
13. How far should a profit stop sit during explosive momentum so normal volatility can breathe?
14. Which measurable event ends `EXPLOSIVE_BREAKOUT` management?

# END_OF_DOCUMENT
