# BybitScanner — Accumulated Strategy & AUTOPILOT Design Addendum

Version: 1.0
Date: 2026-09-07
Status: ACTIVE / RESEARCH-ONLY / DESIGN-ONLY
Implementation authorization: NONE

Purpose: capture the accumulated strategy-management refinements and AUTOPILOT architecture decisions discussed after `TRADING_STRATEGY_SPEC.md` v1.9, without changing Scanner, Terminal, PAPER, LIVE, execution, risk or runtime behavior.

Classification: primarily `MECHANICS_REFINEMENT`; no new H-ID is allocated by this addendum unless a later review finds a materially distinct generalized setup claim.

---

# 1. FALLING WEDGE PRE-BREAKOUT LONG — UPPER-BOUNDARY MANAGEMENT

## 1.1 First upper-boundary touch before confirmed breakout

For a pre-breakout Falling Wedge LONG entered near the lower edge:

- when price first reaches/touches the contemporaneous upper Falling Wedge boundary before confirmed breakout, study a candidate partial realization of approximately `75%` of the current position;
- retain approximately `25%` as a possible breakout runner;
- touch alone is not breakout confirmation;
- candidate fractions are unoptimized and `NEEDS VALIDATION`.

This branch is conceptually distinct from a partial realization triggered only after confirmed breakout.

## 1.2 Break-even sequencing after the 75% reduction

After the intended `~75%` reduction:

1. first confirm the actual reduction/fill;
2. determine the actual residual position size;
3. only then move protection for the residual to a versioned cost-aware break-even level;
4. protection quantity must equal the actual residual quantity.

A price-only zero-PnL level is insufficient because fees, spread and expected exit costs must be included. Stop execution may still slip; break-even therefore means cost-aware planned protection, not a guaranteed zero realized result.

---

# 2. BREAKOUT, RETEST, REBUILD AND STOP TRANSITIONS

## 2.1 Breakout confirmation stop

After an upside breakout is confirmed, the protective STOP for the remaining position is placed behind the breakout confirmation candle.

For this branch, the user-defined breakout confirmation candle is the first candle whose OPEN is already beyond the broken pattern boundary or level. For LONG, the STOP is placed on the adverse side of that candle; the exact low/open reference and technical buffer remain `NEEDS VALIDATION` unless a setup-specific rule defines them.

## 2.2 Retest allowance

A retest may:

- touch the broken boundary/level;
- slightly penetrate or wick through it;
- still remain eligible if the subsequent reaction demonstrates rejection/hold rather than failed breakout.

A small penetration is therefore not automatic invalidation.

## 2.3 Universal retest reversal sequence

A candidate LONG retest-confirmation sequence is:

1. price returns to the broken boundary/level;
2. price touches or slightly penetrates it;
3. a bullish reversal candle or one of the shared bullish reversal formations forms at/around the level;
4. the following candle opens in the upper part of that bullish reversal structure, near the close of the bullish reversal candle;
5. for a Falling Wedge upside breakout it is preferable that this confirmation-candle OPEN is already above the broken upper pattern boundary.

The next candle is the retest confirmation candle for this branch.

## 2.4 Rebuild timing and size

When the retest confirmation candle OPENS, do not wait for its close:

- permit the candidate rebuild immediately at that open;
- rebuild the retained residual, typically `~0.25 WV`, back to a total ceiling of `1.0 WV` by adding at most `~0.75 WV`;
- the total may not exceed the pre-admitted idea ceiling;
- the original idea-level maximum risk may not increase;
- candidate size/fractions are `NEEDS VALIDATION`.

## 2.5 Stop after successful retest/rebuild

After the retest is confirmed and the position is rebuilt, the STOP for the rebuilt position is no longer anchored behind the original breakout confirmation candle. It is moved behind the extremum of the retest itself.

For LONG:

- STOP reference = adverse extremum / lowest meaningful point of the retest;
- exact tick/ATR/structure buffer = `NEEDS VALIDATION`.

Thus the protection sequence is:

`breakout confirmed -> stop behind breakout confirmation candle -> retest confirmed/rebuild -> stop behind retest extremum`.

---

# 3. UNIVERSAL REVERSAL-CANDLE CONFIRMATION PRINCIPLE

Introduce a reusable research concept: `REVERSAL_CANDLE_CONFIRMATION`.

It is not a standalone trade setup. A host setup must first supply the context: pattern boundary, broken/retested level, mirror zone, support/resistance, channel edge, local structural extremum, or another versioned decision zone.

The shared bullish catalog currently includes at minimum:

- bullish engulfing after downside movement;
- hammer plus bullish confirmation;
- classic Morning Star;
- bullish reversal candle at a touch/penetration of a significant boundary/level followed by a confirmation candle opening in the upper part of the reversal structure near the reversal close.

The same principle should later have a mirrored bearish catalog for SHORT use.

The host setup determines what the confirmation authorizes. Examples:

- lower Falling Wedge edge -> candidate initial LONG;
- breakout retest -> candidate rebuild/add;
- mirror support -> candidate bounce entry;
- channel edge -> candidate reaction entry/hold;
- later setup families -> setup-specific action.

The candle formation itself does not grant universal trade authorization.

## 3.1 Multi-timeframe deduplication

One underlying reversal episode must not be counted multiple times merely because timeframe aggregation changes its visual representation.

Example:

`lower-TF Morning Star -> higher-TF engulfing representation -> still-higher-TF long lower wick`

may be `SAME_EVENT_AGGREGATION`, not three independent confirmations.

Only evidence carrying genuinely independent information outside the shared event window may be treated as `INDEPENDENT_HIGHER_TF_CONTEXT`.

---

# 4. TARGET-PATH MANAGEMENT AFTER RETEST REBUILD

## 4.1 Primary target reference and target progress

The main pattern/signal potential remains the primary path reference. Management may use a normalized progress metric such as:

`target_progress = distance_travelled_from_management_reference / distance_to_versioned_primary_target`

Exact reference choice is `NEEDS VALIDATION` and must be frozen at decision time without hindsight boundary changes.

## 4.2 Do not over-manage the first half of the path

Before approximately `50%` of the primary potential path is traversed:

- strong intermediate levels;
- round-number prices;
- large opposing DOM/order-book densities;

may be recorded as context, but should not by themselves force early partial exits.

The candidate `50%` threshold is unoptimized and `NEEDS VALIDATION`.

## 4.3 Mandatory first profit realization before break-even

After price has traversed at least approximately `50%` of the versioned potential:

1. realize at least `25%` of the original position;
2. confirm the actual partial fill/reduction;
3. only then move the STOP on the residual to cost-aware break-even or better.

The STOP must not be moved to break-even before the minimum partial realization is actually confirmed.

The `50%` progress and `25%` realization figures are research candidates, not proven constants.

---

# 5. COMBINED EXIT-ZONE SELECTION AFTER 50% PROGRESS

After the candidate `>=50%` path threshold, exit placement may use a combination of:

- remaining versioned pattern/signal potential;
- strong structural resistance/support levels;
- large opposing DOM/order-book densities;
- round-number prices;
- local continuation/exhaustion state;
- momentum state.

The primary pattern/signal potential remains the baseline map. Structure and microstructure refine where realized exits are placed.

When several factors coincide, the zone may receive higher exit priority. Example for LONG:

`primary target zone + resistance + large ask density + round number`.

For DOM-based placement, prefer exiting slightly before the opposing density rather than assuming the displayed liquidity will remain executable. The offset method should be normalized by tick size, spread, ATR or another versioned scale and remains `NEEDS VALIDATION`.

DOM density is transient and must not be treated as equally durable as structural geometry.

---

# 6. NORMAL/CALM VS AGGRESSIVE MOMENTUM MANAGEMENT

Introduce a candidate post-50%-progress momentum state such as:

- `CALM`;
- `NORMAL`;
- `AGGRESSIVE`;
- optionally later `WEAKENING` / `REVERSAL`.

Exact thresholds are `NEEDS VALIDATION`.

Candidate decision-time features include:

- velocity relative to ATR/current volatility;
- directional candle range/body size;
- repeated closes near the directional extreme;
- volume relative to local baseline;
- pullback depth and recovery speed;
- time required to traverse a given fraction of target path;
- persistence through nearby resistance/support;
- sequence continuity.

Do not classify a move as aggressive using future outcome information.

## 6.1 Calm/normal branch

After the mandatory first `25%` realization and break-even STOP:

- distribute another approximately `50%` of the original position with closing Limit orders over the remaining path to the primary target;
- baseline distribution is roughly even across the remaining path;
- adjust exact placements around strong structural levels, round numbers and large opposing DOM densities;
- retain the final approximately `25%` as a runner;
- manage the runner by trailing/structure/reversal/exhaustion logic to capture extension beyond the baseline target.

Candidate fractions remain `NEEDS VALIDATION`.

## 6.2 Aggressive branch

When momentum remains `AGGRESSIVE`:

- the mandatory first `25%` realization and break-even protection still apply;
- do not automatically deploy the normal `50%` exit grid up to the baseline target;
- allow the remaining `75%` to participate in momentum continuation according to the rules below.

From that remaining `75%` of the original position:

- approximately `25%` of the original position may be offered above the original target at an extended target;
- candidate extension is approximately `+25% to +30%` of the original potential beyond the baseline target, i.e. roughly `125-130%` of the original measured potential path;
- this is not the final runner allocation; it is one quarter of the original position carved out of the still-open `75%`;
- the remaining `50%` of the original position is managed dynamically rather than pre-distributed immediately.

The `125-130%` extension is a research candidate and must be compared with neighboring extensions and pure trailing controls.

## 6.3 Weakening of aggressive momentum

Candidate weakening evidence includes:

- shrinking directional candles;
- deeper pullbacks;
- closes moving away from the directional extreme;
- falling volume after an impulse;
- repeated adverse wicks;
- repeated failure at a nearby level/density;
- material slowing in path velocity;
- a shared reversal-candle formation against the position;
- structural loss of the support/resistance sequence sustaining the impulse.

A working candidate is to require multiple materially independent weakening signals rather than one isolated feature. Exact count/weights remain `NEEDS VALIDATION`.

When `AGGRESSIVE -> WEAKENING/NORMAL`, begin distributing the dynamically held `50%` of the original position around the nearest meaningful obstacle/target zones rather than closing all of it in one order.

A candidate split is `25% + 25%` of the original position, with the first quarter realized near the first strong obstacle and the second quarter either assigned to the next zone or structure-trailed.

## 6.4 Extended-target cancellation

Do not cancel the above-target Limit merely because momentum slows briefly.

Cancel/reintegrate that `25%` extended-target allocation only after stronger evidence that the momentum-extension branch has failed, such as:

- confirmed reversal against the position;
- loss of key local continuation structure;
- deep pullback without momentum recovery;
- repeated rejection/failure at a strong zone;
- persistent opposing liquidity that demonstrably holds price;
- state transition from `AGGRESSIVE` through `WEAKENING` to `REVERSAL/FAILURE`.

After cancellation, return that quantity to ordinary structural/target-based exit management.

---

# 7. POST-IMPULSE STRUCTURE AS MANAGEMENT CONTEXT

Introduce a reusable management context: `POST_IMPULSE_STRUCTURE_STATE`.

Candidate states:

- `CONTINUATION`;
- `NEUTRAL`;
- `EXHAUSTION`.

For an existing LONG after a bullish impulse:

## 7.1 Exhaustion evidence

A newly forming `Rising Wedge` may be treated as additional evidence of post-impulse exhaustion and may increase the priority of:

- partial realization;
- tighter structure-aware protection;
- cancellation of aggressive extension assumptions;
- final exit if combined with other reversal/weakening evidence.

A Rising Wedge alone is not an unconditional immediate full-close command.

## 7.2 Continuation evidence

Candidate continuation structures include:

- bullish flag;
- L-shaped post-impulse consolidation;
- compression/pressing toward upper resistance with shallow pullbacks;
- other versioned compact consolidation structures that preserve directional pressure.

These can support continued holding, delayed unloading or preservation of an extended target, but they do not override hard invalidation or account risk rules.

This management layer should be reusable across setup families and mirrored for SHORT positions.

---

# 8. AUTOPILOT DISCOVERY AND FOCUSED-WATCH ARCHITECTURE

This section is architecture/design, not a trading-edge claim.

## 8.1 Scanner remains the shared discovery source

Do not create a second independent market-search engine solely for AUTOPILOT unless future evidence shows the shared Scanner cannot satisfy required semantics.

Target architecture:

`MARKET UNIVERSE`
`-> DISCOVERY SCANNER`
`-> CANDIDATE QUEUE`
`-> AUTOPILOT STRATEGY ENGINE`
`-> ACCOUNT/RISK ADMISSION`
`-> ORDER INTENT`
`-> EXECUTION ADAPTER`.

Scanner discovers/describes opportunities. AUTOPILOT does not trade merely because Scanner emits a bullish/bearish signal. Strategy still owns setup admission, trigger, sizing, risk and management decisions.

## 8.2 Observation tiers

Use resource-tiered monitoring rather than stopping the entire Scanner when one symbol becomes interesting.

Candidate tiers:

1. `DISCOVERY` — broad, relatively cheap market-wide scan;
2. `CANDIDATE` — increased analysis for structurally interesting symbols;
3. `ARMED` — high-frequency focused monitoring near a trade trigger;
4. `ACTIVE/MANAGING` — maximum required monitoring for open positions.

The broad discovery process should continue while individual symbols receive focused attention.

DOM/L2/prints subscriptions should generally be activated only for a limited set of symbols near execution or already in an active position, not for the whole universe continuously.

## 8.3 Symbol suppression/exclusion

AUTOPILOT must be able to suppress a symbol from ordinary discovery scans while retaining the symbol in focused/active monitoring.

Candidate reasons:

- open AUTOPILOT position;
- `ARMED` / focused-watch state;
- cooldown after a trade;
- invalid/expired setup;
- idea-risk already occupied;
- temporary liquidity/market-state exclusion;
- instrument eligibility/delisting restriction.

Conceptual state: `SUPPRESSED_FROM_DISCOVERY`, not deletion from the system.

## 8.4 Opportunity prioritization

When watch/resource/capital capacity is constrained, prioritize candidates using expected economic value rather than detector score alone.

Future priority inputs should include:

- expected potential after costs;
- expected reward-to-risk;
- later, statistically estimated setup win rate / conditional success probability;
- expected holding/realization time;
- liquidity and expected execution quality;
- proximity to trigger;
- portfolio correlation and current exposure;
- account-specific risk availability.

A future research metric may include:

`Expected Value = P(win) * AvgWin - P(loss) * AvgLoss - Costs`

and a time-efficiency measure such as:

`Capital Efficiency = Expected Value / Expected Holding Time`.

This is conceptual only until statistical estimates are validated. Time-to-realization is explicitly important: a smaller but faster opportunity may outrank a larger but much slower one.

---

# 9. MULTI-ACCOUNT AUTOPILOT AS A FIRST-CLASS INVARIANT

This section is architecture/design and must guide future implementation from the first AUTOPILOT slice.

## 9.1 No strategy-level PAPER/LIVE split

AUTOPILOT strategy logic must be account-neutral. Do not introduce strategy branches of the form:

`if PAPER ... else LIVE ...`.

Target flow:

`AUTOPILOT STRATEGY`
`-> ACCOUNT-NEUTRAL TRADING INTENT`
`-> EXPLICIT ACCOUNT/RISK CONTEXT`
`-> ACCOUNT-SCOPED ORDER INTENT`
`-> EXECUTION ADAPTER`
`-> concrete account/provider`.

PAPER and LIVE are execution/account environments, not separate strategy implementations.

## 9.2 Arbitrary account count

Design for any number of connected accounts, including:

- PAPER accounts;
- multiple Bybit LIVE accounts;
- Bybit subaccounts;
- future provider adapters if added.

Do not hard-code an architecture for exactly `1 PAPER + 1 LIVE`.

Each account context should have explicit identity and capabilities, including at minimum:

- `account_id`;
- `provider`;
- `environment`;
- execution adapter/capability set;
- wallet/WV state;
- risk profile;
- current positions/exposure;
- session generation / authority fence;
- connection/reconciliation state;
- instrument permissions/constraints.

## 9.3 Setup state versus account trade state

Separate shared market/setup state from per-account execution/trade state.

Example:

`SETUP ABCUSDT: RETEST_CONFIRMED`

may coexist with:

- `paper-1: ACTIVE 1.0 WV`;
- `bybit-main: ACTIVE 0.75 WV`;
- `bybit-sub2: SKIPPED`;
- `bybit-sub3: ARMED`.

The setup should not be duplicated as unrelated strategy copies for each account.

## 9.4 Per-account admission

A single market setup may produce different decisions per account.

Each account independently evaluates:

- current WV/account wallet;
- risk budget;
- aggregate exposure;
- existing symbol position;
- cooldown;
- liquidity/execution constraints;
- provider/account capabilities;
- session/reconciliation health;
- account-specific restrictions.

Therefore the same setup can be `ACCEPT` on one account and `REJECT/SKIP` on another without altering the shared setup state.

## 9.5 PAPER-to-LIVE parity

PAPER should use the same domain command lifecycle, intent identity, fencing, ambiguity handling and reconciliation semantics as LIVE wherever technically possible.

The goal is that moving an AUTOPILOT strategy from PAPER to LIVE means attaching another account/execution adapter to the same strategy and risk architecture, not rewriting the robot.

No blind retries, account/session fencing, authoritative fills, UNKNOWN/reconciliation semantics and explicit account identity should remain common invariants.

---

# 10. REQUIRED FUTURE DATA FIELDS

Candidate fields to support the mechanics above:

- `management_branch`;
- `upper_boundary_touch_time`;
- `planned_partial_fraction`, `actual_partial_fraction`;
- `partial_fill_confirmed_time`;
- `residual_quantity`;
- `break_even_requested_price`, `break_even_effective_price`, `cost_model_version`;
- `breakout_confirmation_candle_time`, OHLC and boundary/level price at its open;
- `retest_start_time`, `retest_extremum`, `retest_penetration_depth`;
- `reversal_formation_id/version`, component candle OHLC;
- `retest_confirmation_candle_open_time`, open price and relative location within prior reversal structure;
- `rebuild_intended_wv`, `rebuild_actual_wv`, `post_rebuild_total_wv`;
- `post_rebuild_stop_reference`, requested/effective stop;
- `primary_target_reference`, `target_progress`;
- `momentum_state`, feature values and state-transition time;
- `mandatory_partial_25_fill_status`;
- `normal_exit_grid_plan`;
- `extended_target_fraction`, `extended_target_ratio`, requested/effective price;
- `extended_target_cancel_reason`;
- `post_impulse_structure_state`, structure identity/version;
- structural level / round-number / DOM-density features used for an exit decision;
- `discovery_state`, `focused_watch_state`, suppression reason;
- opportunity-priority features, expected holding-time estimate and model version;
- shared `setup_instance_id` plus per-account trade/admission IDs;
- account-level `account_id`, provider, environment, risk profile/version, capability state and reconciliation state.

All decision-time fields must remain immutable for research evaluation; later outcomes append rather than rewrite prior state.

---

# 11. VALIDATION / COMPARISON BACKLOG

All numeric values in this addendum are candidate research parameters unless already governed by a stronger existing contract.

Required future comparisons include:

- upper-boundary full exit vs `75/25` touch-partial + BE residual;
- breakout-confirmation-candle STOP vs retest-extremum STOP after rebuild;
- retest entry at confirmation-candle OPEN vs waiting for confirmation-candle CLOSE;
- retest with/without shared reversal-candle formation evidence;
- `50%` target-progress activation vs neighboring thresholds;
- mandatory `25%` realization before BE vs alternative partial fractions;
- calm/normal `50%` exit-grid + `25%` runner vs other distributions;
- aggressive extension target around `125-130%` vs neighboring extension ratios and pure trailing;
- momentum classification ablations and sensitivity;
- Rising Wedge exhaustion context vs matched post-impulse controls;
- Flag/L-shape/upper-compression continuation context vs matched controls;
- opportunity ranking by potential only vs EV/time-efficiency aware ranking once sufficient statistics exist;
- multi-account PAPER/LIVE parity and account-specific admission behavior in PAPER/shadow environments.

No item in this addendum authorizes autonomous LIVE trading.

---

# 12. OPEN QUESTIONS

1. Exact deterministic definition of breakout confirmation candle adverse-side STOP reference: candle low, open, or another versioned reference.
2. Exact allowed retest penetration tolerance and failure rule.
3. Exact geometry for "confirmation candle opens in the upper part of reversal structure" and how to normalize it.
4. Exact momentum-state thresholds and transition hysteresis.
5. Exact grid spacing policy for calm/normal distribution.
6. Exact extended-target ratio neighborhood and cancellation hysteresis.
7. Exact structure definitions for L-shaped continuation and upper compression.
8. Exact opportunity-ranking formula before statistically reliable win-rate and holding-time models exist.
9. Focused-watch resource budgets and scheduling cadence.
10. Per-account allocation policy when the same setup is simultaneously admissible on multiple accounts.

# END_OF_DOCUMENT
