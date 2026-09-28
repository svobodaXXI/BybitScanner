# BybitScanner — Market Microstructure / Forced-Flow Research Architecture

Version: 0.1
Date: 2026-09-28
Status: DOCUMENTED DESIGN / DEFERRED RESEARCH
Implementation authorization: NONE
Trading authorization: NONE
LIVE trading: OUT OF SCOPE
Owner priority impact: NONE — the active Robot/Geometry queue remains authoritative until explicitly reprioritized.

Purpose: preserve the complete design for researching whether short-horizon crypto-perpetual microstructure contains an exploitable edge around forced liquidations, absorption, liquidity recovery and cross-venue divergence, without contaminating the current Scanner/Robot execution architecture before the hypothesis is proven.

---

# 1. PRODUCT THESIS

The research target is not another chart pattern and not a generic liquidation sniper.

Primary hypothesis:

> During a forced liquidation cascade, an exploitable transition may exist when forced/aggressive flow remains extreme but its marginal price impact collapses, consumed liquidity repeatedly refills, leverage is flushed, and independent venues stop confirming further movement.

For a potential LONG reversal:

~~~text
large forced/aggressive sells
+ falling open interest / leverage flush
+ continued liquidation pressure
BUT
+ less downside movement per unit of sell flow
+ repeatable bid refill / faster book recovery
+ external venue stabilization
+ local mark/index dislocation normalizing
= candidate forced-flow exhaustion / absorption
~~~

SHORT is the exact mirror.

This is a research hypothesis, not a production trading rule. It must be accepted or rejected from captured event data after fees, spread, slippage and execution latency.

---

# 2. WHY THIS IS A SEPARATE RESEARCH LAYER

Current BybitScanner is primarily candle/geometry/decision oriented. The new work is event/microstructure oriented.

The new layer remains separate from Scanner geometry, Telegram signal delivery, canonical Robot admission, Robot execution/protection/reconciliation and PAPER/LIVE mutation authority.

It may eventually provide decision-time factors or a frozen candidate reference, but it must never become a second execution engine.

~~~text
Market Microstructure Lab
        |
        +--> research evidence / outcomes
        +--> decision-time factors for Trading Diary
        +--> optional pattern confirmation (future, separately authorized)
        +--> optional frozen research candidate (future, separately authorized)
                 |
                 X no direct orders
                 |
          canonical Robot admission
                 |
          existing Robot execution
~~~

---

# 3. EXTERNAL ARCHITECTURE LESSONS ADOPTED

The design borrows mechanisms, not strategy parameters or code wholesale.

## 3.1 Hummingbot

Adopt the separation:
exchange data source -> normalized messages -> maintained local OrderBookTracker state -> strategy/controller -> separate execution machinery.

Useful rules:
- venue-specific public-data adapters;
- local order-book reconstruction outside strategy logic;
- explicit snapshot/delta semantics;
- recover rather than guess when book integrity is uncertain;
- decision/controller separation from order execution.

Do not import Hummingbot as a runtime dependency merely to obtain these patterns.

## 3.2 NautilusTrader

Adopt:
- event-driven normalized market-data domain;
- adapters at the system boundary;
- the same event model for live processing and replay;
- separation between data engine, decision logic and execution.

Canonical rule:

> Live capture and historical replay feed the same normalizer, MarketState, FeatureEngine and ForcedFlowEngine.

There must not be a separate simplified backtest implementation of the signal.

## 3.3 Cryptofeed

Adopt normalized callbacks plus exchange-specific book-integrity handling. Sequence/checksum/data-quality failures are first-class. A normalized schema must not erase venue-specific semantics or integrity metadata.

## 3.4 Tardis-style event-time discipline

Preserve exchange timestamp and local receive timestamp, and replay in original event order/inter-arrival semantics.

Every event keeps at least:

~~~text
exchange_event_ts
local_receive_ts
~~~

Cross-venue lead/lag must not confuse network delay with price discovery.

## 3.5 Exchange-native semantics

Bybit, Binance and Hyperliquid must not be treated as if similarly named feeds have identical meaning.

Example: Bybit allLiquidation pushes all liquidations in 500 ms batches. A venue that publishes only sampled/latest liquidation updates must not be normalized into the same quantitative liquidation-volume measure without provenance and venue-specific interpretation.

---

# 4. CORE ARCHITECTURE

~~~text
Bybit / Binance / Hyperliquid
            |
            v
       Venue Adapters
            |
            +----------------------+
            |                      |
            v                      v
   immutable raw events      data-quality events
            |
            v
       MarketState
      /    |      \
 local L2 trades  ticker/context
            |
            v
       FeatureEngine
            |
            v
     ForcedFlowEngine
            |
            +--> state transitions
            +--> evidence snapshots
            +--> candidate observations
            |
            v
        Capture/Replay
            |
            v
       OutcomeEngine
            |
            +--> expectancy research
            +--> Trading Diary factors
            +--> future admission research
~~~

Raw facts, reconstructed state and derived interpretation are separate layers.

---

# 5. EVENT MODEL

Use small immutable normalized events while preserving raw provenance; do not create one giant mutable market object.

Minimum common envelope:

~~~text
event_id
venue
instrument
normalized_symbol
channel
event_type
exchange_event_ts
local_receive_ts
venue_sequence / update_id when available
local_sequence
connection_session_id
raw_payload_ref or raw_payload
schema_version
adapter_version
~~~

Representative event types:

~~~text
TradeEvent
BookSnapshot
BookDelta
LiquidationEvent
TickerEvent
OpenInterestObservation
FundingObservation
MarkIndexObservation
DataQualityEvent
ConnectionEvent
~~~

Rules:
1. Raw event is a fact.
2. MarketState is reconstructed state.
3. Feature is a derived interpretation.
4. State-machine output is a research hypothesis.
5. No later layer rewrites earlier facts.

---

# 6. TIME MODEL

For every live message retain exchange_event_ts and local_receive_ts. Where a venue provides more times, retain them too.

For Bybit order book preserve ts, cts, u and seq. Bybit documents that cts can be correlated with public-trade T.

Derived receive latency:

~~~text
receive_latency_ms = local_receive_ts - exchange_event_ts
~~~

Lead/lag calculations include latency/data-quality guards. A degraded network path must not manufacture a leader venue. System clock quality must be observable; cross-venue research is invalid when local timing uncertainty is larger than the effect being measured.

---

# 7. VENUE ADAPTER CONTRACT

Each venue adapter owns:
- WebSocket connection/reconnect;
- native subscription syntax;
- raw payload preservation;
- timestamp extraction;
- native sequence/update semantics;
- native side interpretation;
- symbol mapping;
- conversion into normalized immutable events;
- venue-specific data-quality events.

It does NOT own OFI calculations, exhaustion thresholds, cross-venue conclusions, strategy decisions, Robot admission or order placement.

A normalized event retains enough provenance to reconstruct what the venue actually meant.

---

# 8. BYBIT FIRST-SLICE DATA

Initial research venue: Bybit USDT linear perpetuals.

## 8.1 Public trades

Use for taker/aggressor direction, executed price, quantity/notional, short-horizon trade imbalance and price-impact measurement.

## 8.2 Order book

Preferred initial depth: L50.

Current Bybit documented push frequencies for linear/inverse:
- L1: 10 ms;
- L50: 20 ms;
- L200: 100 ms;
- L1000: 200 ms.

L50 is an initial design compromise, not a permanent parameter.

## 8.3 All liquidations

Bybit allLiquidation.{symbol}:
- covers all liquidations;
- pushes every 500 ms;
- provides update time, side, executed size and bankruptcy price.

Do not infer unseen order-book execution detail from bankruptcy price.

## 8.4 Ticker/context

Use derivatives context for last, mark, index, open interest, funding and required venue context. If a field is slower or from a separate source, persist its true observation time; never forward-fill it as tick-level truth.

---

# 9. LOCAL ORDER BOOK STATE MACHINE

Required states:

~~~text
DISCONNECTED
    |
    v
WAIT_SNAPSHOT
    |
    v
VALID
    |
    +-- integrity/reconnect/reset anomaly --> INVALID
                                           |
                                           v
                                      WAIT_SNAPSHOT
                                           |
                                           v
                                         VALID
~~~

Rules:
- initial snapshot creates the book;
- deltas apply only under valid native sequencing rules;
- zero size deletes a level;
- insert/update follows native semantics;
- a new authoritative snapshot replaces the local book;
- reset/reinitialization clears previous continuity as required;
- no book-dependent feature claims VALID while integrity is uncertain.

For Bybit standard snapshot/delta books:
- new snapshot means reset/replace;
- u=1 is reinitialization/reset evidence;
- retain seq and u for integrity/debug evidence.

If full-depth Bybit book is evaluated later, use the official REST snapshot + buffered-delta synchronization contract instead of transplanting L50 assumptions.

Fail closed:

> An invalid book suppresses book-dependent ForcedFlow transitions. It does not guess missing levels.

---

# 10. TWO-STAGE MARKET-DATA UNIVERSE

Do not open expensive L2/trade/liquidation processing for the whole Scanner universe from day one.

~~~text
broad cheap watch universe
          |
          v
shock/anomaly trigger
          |
          v
focused microstructure universe
(trades + L2 + liquidation + context)
~~~

Initial laboratory universe:
- BTCUSDT;
- ETHUSDT;
- SOLUSDT.

Expand to a compact liquid-alt cohort only after capture/replay integrity is proven.

Future Focus Mode may activate from a cheap precursor such as volatility/turnover/liquidation anomaly, but the exact trigger remains research work and must not be tuned before a clean baseline exists.

---

# 11. FEATURE ENGINE

Do not start with one opaque Microstructure Score. Persist independent versioned factors.

## 11.1 Aggressive trade flow

~~~text
buy_notional_W
sell_notional_W
net_aggressive_flow_W = buy_notional_W - sell_notional_W
trade_imbalance_W = net_aggressive_flow_W / total_notional_W
~~~

Keep raw counts/notional and derived ratios.

## 11.2 Order Flow Imbalance (OFI)

OFI includes changes in best/near-book supply and demand rather than only executed trades. Exact formula/version must be explicit and tested against reconstructed book semantics.

## 11.3 Depth imbalance

~~~text
depth_imbalance =
(bid_depth - ask_depth) / (bid_depth + ask_depth)
~~~

Compute at explicit depth/distance bands rather than silently aggregating arbitrary depth.

## 11.4 Spread

Persist spread_abs, spread_bps and spread_percentile. Spread is both a market-state factor and an execution-cost constraint.

## 11.5 Microprice

Use a documented imbalance-aware microprice from best bid/ask and size. It is a short-horizon state feature, not a fair-value oracle.

## 11.6 Liquidation pressure

Persist venue-native facts and normalized research measures:

~~~text
long_liquidation_notional_W
short_liquidation_notional_W
net_liquidation_pressure_W
liquidation_percentile_or_zscore
~~~

Cross-venue liquidation values remain provenance-aware and are not blindly summed when semantics differ.

## 11.7 Open-interest change

Use to contextualize leverage opening/closing and liquidation bursts. OI direction alone is not proof of trader side.

## 11.8 Mark / index / last dislocation

Candidate factors:

~~~text
last_minus_mark_bps
mark_minus_index_bps
local_dislocation_percentile
normalization_velocity
~~~

Purpose: distinguish local perp stress from broader underlying movement.

## 11.9 Marginal Price Impact

Core feature:

~~~text
impact =
abs(mid_or_reference_price_change_bps)
/
aggressive_notional
~~~

The proposed signature is not one value but the trajectory:

~~~text
forced/aggressive flow rising
while
impact per unit flow falling
~~~

Persist numerator and denominator separately.

## 11.10 Liquidity refill

Measure response after visible liquidity is consumed:

~~~text
consumed_bid_depth
new_bid_depth_after_consumption
bid_refill_ratio =
new_bid_depth_after_consumption / consumed_bid_depth
~~~

SHORT mirrors with asks. A static large order is not absorption; repeated response to consumption is the target.

## 11.11 Resilience / recovery time

Candidate measures RecoveryTime_25, RecoveryTime_50 and RecoveryTime_75: time required for an explicit fraction of depleted depth/spread state to recover after a shock.

## 11.12 Cross-venue divergence

Candidate measures:

~~~text
return_divergence
low/high continuation disagreement
lead_lag_ms
leader_confidence
cross_venue_price_gap_bps
~~~

No venue is permanently hard-coded as leader.

---

# 12. NORMALIZATION

Prefer symbol/regime-relative rolling percentile, robust z-score, volatility scaling, depth scaling and turnover scaling.

Candidate normalized factors:

~~~text
liq_z
ofi_z
impact_percentile
spread_percentile
refill_percentile
oi_delta_z
~~~

Do not initially define fixed liquidation/OI/refill thresholds without captured evidence. No tuning against one memorable chart or symbol.

---

# 13. FORCED-FLOW STATE MACHINE

Do not begin with ML. Use an explainable deterministic research state machine backed by separately stored factors.

LONG-side concept:

~~~text
NORMAL
  |
  v
SHOCK
  |
  v
FORCED_SELLING
  |
  v
EXHAUSTION_CANDIDATE
  |
  v
ABSORPTION
  |
  v
REVERSAL_CONFIRMED
~~~

Any active state may transition to INVALIDATED or DATA_INVALID.

Semantics:
- NORMAL: no qualifying stress.
- SHOCK: material short-horizon displacement / flow anomaly.
- FORCED_SELLING: aggressive sell pressure + liquidation/deleveraging evidence + downside continuation. It is not a LONG signal.
- EXHAUSTION_CANDIDATE: forced/aggressive sell flow remains elevated but incremental downside impact weakens.
- ABSORPTION: consumed bid liquidity repeatedly refills and/or book resilience improves.
- REVERSAL_CONFIRMED: research-only state with local stabilization plus independent confirmation. It authorizes no order.

Core concept:

~~~text
Flow up
Impact/Flow down
~~~

SHORT is mirrored exactly.

---

# 14. CROSS-VENUE CONFIRMATION

Cross-venue data is an independent witness, not a permanently trusted leader.

Initial addition after Bybit-only stability: Binance. Hyperliquid is a third venue only if measured incremental value justifies complexity.

Maintain per-symbol rolling lead/lag estimates over bounded lag candidates and persist:

~~~text
leader_venue
estimated_lead_ms
confidence
observation_count
timing_health
~~~

Guards:
- disable lead inference during receive-latency anomalies;
- require enough synchronized observations;
- do not infer direction from one stale venue;
- preserve native liquidation/OI semantics separately;
- do not force unlike fields into fake identical units.

The useful question is:

> Are independent markets still confirming the local move, or has local forced flow become increasingly idiosyncratic?

---

# 15. RAW CAPTURE

High-frequency raw market data is NOT Trading Diary data.

Create a dedicated bounded Microstructure Capture surface.

Requirements:
- append-only during capture;
- raw or losslessly reconstructable venue payload;
- event envelope and timestamps;
- explicit schema/adapter versions;
- connection/session identity;
- ordered event identity;
- compression/batching only if order/meaning stays unchanged;
- no secrets/private account payloads;
- bounded retention/configuration;
- capture failure is observable;
- capture must not block the serialized Robot execution owner.

Storage format is deliberately deferred. Benchmark actual event rate and replay needs before choosing JSONL/Parquet/binary/other.

---

# 16. DETERMINISTIC REPLAY

Replay is a first-class architecture requirement.

~~~text
live raw events
     |
     v
same normalizer
     |
     v
same MarketState
     |
     v
same FeatureEngine
     |
     v
same ForcedFlowEngine

historical replay
     |
     +-----------------------> same path
~~~

Do not create separate backtest-only signal logic.

Replay preserves exchange order, local receive order, relevant inter-arrival timing, reconnect/reset/data-quality events and venue identity.

Determinism:

> The same captured stream + same versions/configuration produces the same state transitions/features/outcomes.

---

# 17. OUTCOME ENGINE

The first purpose is to prove/disprove edge, not create trades.

For each frozen research transition/candidate, measure explicit forward horizons, initially candidate windows such as:

~~~text
1 s
3 s
10 s
30 s
1 min
3 min
5 min
15 min
~~~

Persist:
- forward return by declared price source;
- MFE and MAE;
- time to MFE/MAE;
- continuation versus reversal;
- spread/liquidity state;
- event/sample count;
- data-quality eligibility.

Evaluate realizable execution:

~~~text
gross move
- spread
- actual/estimated book slippage
- taker fee
- latency penalty / delayed-entry sensitivity
= net research expectancy
~~~

A directionally predictive feature that cannot clear costs is not a trading edge.

Passive-entry research is a separate future cohort because fill probability/adverse selection differ fundamentally from taker entry.

---

# 18. TRADING DIARY BRIDGE

Do NOT write every trade/book delta into Trading Diary. Microstructure Capture owns high-frequency evidence.

Diary receives only decision-time factor snapshots attached to an existing setup/decision or separately authorized research setup.

Candidate future keys:

~~~text
micro.market_state
micro.data_quality
micro.aggressive_flow_1s
micro.aggressive_flow_5s
micro.ofi_1s
micro.depth_imbalance
micro.spread_bps
micro.liquidation_z
micro.oi_delta
micro.last_mark_dislocation_bps
micro.mark_index_dislocation_bps
micro.marginal_impact
micro.impact_decay
micro.bid_refill
micro.ask_refill
micro.recovery_time_50_ms
micro.crossvenue_divergence_bps
micro.leader_venue
micro.lead_ms
micro.lead_confidence
~~~

Every factor has stable key, version, source/provenance, observation time and applicability/data-quality semantics.

Missing data stays missing; never silently convert it to zero/False.

---

# 19. RELATIONSHIP TO EXISTING PATTERNS

Two independent research tracks are allowed.

## 19.1 Standalone microstructure opportunity

A ForcedFlow transition may eventually become its own frozen research candidate. Separate evidence and owner authorization are required before Robot integration.

## 19.2 Pattern confirmation/filter

Wedge, L-shape and Ikigai Box may later consume microstructure factors as decision-time evidence.

Research comparison:

~~~text
pattern-only
vs
same pattern + healthy microstructure confirmation
~~~

Possible future use: reject weak setups, delay admission, prioritize evidence or improve expected value.

It must NOT rewrite pattern geometry or invent cross-pattern score comparability.

Geometry asks: What price structure formed?

Microstructure asks: What participant/flow state is occurring now?

Keep the domains separate.

---

# 20. ROBOT INTEGRATION BOUNDARY

The laboratory has no order-placement authority.

Forbidden:

~~~text
ForcedFlowEngine -> exchange order
ForcedFlowEngine -> ActionExecutor
ForcedFlowEngine -> protection mutation
~~~

Future permitted path, only after explicit authorization:

~~~text
ForcedFlowEngine
-> immutable evidence/candidate
-> shared read-only eligibility/admission assessment
-> canonical admit_robot_candidate()
-> existing Robot execution/protection/reconciliation
~~~

No second execution engine, order journal, protection system or recovery coordinator. LIVE remains out of scope.
