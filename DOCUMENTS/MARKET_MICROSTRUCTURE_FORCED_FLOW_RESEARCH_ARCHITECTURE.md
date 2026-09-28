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
