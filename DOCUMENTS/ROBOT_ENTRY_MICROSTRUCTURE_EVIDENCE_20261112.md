# Shared Robot entry microstructure evidence — first implementation slice

**Owner direction:** 2026-11-12. **Status:** research-only implementation proposal; no proven edge, no trading authority.
**Primary example:** ICNTUSDT Linear, 2026-11-07, 14:00–14:16 MSK.
**Related design:** unmerged PR #321 (`MARKET_MICROSTRUCTURE_FORCED_FLOW_RESEARCH_ARCHITECTURE.md`); existing H-017 DMI-crossing rules in `TRADING_STRATEGY_SPEC.md`.
**Classification:** existing entry-evidence hypothesis refinement / ICNT observation; no new H-ID and no Robot policy change.

## Objective and ownership

Improve the **quality/timing** of the canonical Robot entry without duplicating a strategy inside the Simulator:

```text
Scanner pattern / frozen geometry
       + closed-candle DMI/ADX/RSI context
       + on-demand real trades / validated L2 / optional OI and liquidations
              |
       shared Robot entry-evidence feature layer (NO ORDERS)
              |
       research observation -> validated policy (later)
              |
       existing admission -> risk -> protected execution
              |
        same core called by historical SIMULATION
```

The Simulator supplies historical event time, market data and virtual execution; it does not own a second entry algorithm. The VPS may receive the *same* verified code through the existing PR/release process after separate approval. No new external runtime service, broad all-symbol L2 subscription, trading DB or parallel execution engine.

## Hypotheses to test independently

**Continuation (ICNT):** closed-candle +DI/-DI, +DI/ADX, -DI/ADX, and DI/20 cross events (single or clustered) and RSI recovery provide preparation context; aggressive-buy acceleration, price response, retention after pullback and a renewed buy wave may improve entry timing. A high positive delta alone failed as a reliable discriminator in the 14:02 versus 14:10 example. Record each event at its *availability time*. ADX crossing 20 is not required in the unvalidated hypothesis.

**Forced-flow exhaustion (related PR #321):** continued aggressive selling (possibly actual LONG liquidations) with falling marginal downside price impact, repeated **verified** bid refill and local stabilization may be reversal evidence; SHORT is symmetric. An absence of liquidations in historical data is UNKNOWN, never evidence of zero liquidations. Falling OI alone does not identify who closed.

Keep continuation and reversal-exhaustion as **different labeled cohorts**, but derive their factors in the **same common feature layer**. Price response, CVD/OFI, trade rate, depth recovery and trade-size periodicity are independent observable factors, not proof of one large participant.

## Reuse and external design decisions

| Reference | Borrowed principle, not trading thresholds |
|---|---|
| TradingView [Volume Footprint](https://www.tradingview.com/support/solutions/43000726164-volume-footprint-charts-a-complete-guide/) / [Volume Delta](https://www.tradingview.com/support/solutions/43000725057-volume-delta/) | per-price imbalance / cumulative delta; prefer **actual Bybit taker side** to candle-estimated delta, record method/provenance |
| TradingView [CVD Absorption + Confirmation](https://www.tradingview.com/script/LzJGJVHc-CVD-Absorption-Confirmation-Orderflow-Volume/) | test delta-price divergence and independent confirmation; not a ready-to-trade signal |
| [Hummingbot Strategy V2](https://hummingbot.org/strategies/v2-strategies/) | separate data provider, controller/strategy observation and order executor |
| [NautilusTrader L2 replay](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/tutorials/backtest_orderbook_binance.py) | preserve native ordered book updates and replay the same strategy against historical evidence |
| Bybit native public trades / WebSocket orderbook / allLiquidation | preserve side semantics, exchange event time, sequence, snapshot/delta integrity and missing-data provenance |

Do not copy third-party source or claim that a published script's indicators have proven predictive value.

## Minimal implementation / authority

`robot_entry_flow_evidence.py` is the **single pure shared analytical primitive**, independently importable by the canonical Robot and the Simulator. It compares **two completed, contiguous, equal-duration market-flow windows**, with explicit price source. It emits relative taker imbalance, price response, purchase acceleration, weakening impact of continued sells/buys and **optional** validated refill evidence. It refuses future/unordered/mixed-price windows. Missing L2 refill stays UNKNOWN. It produces **no order or admission decision**.

Existing `research/wilder_dmi.py` owns causal H-017 DMI crosses. Reuse it; do not implement a second ADX. The same applies to existing historical trade cache/replay and Robot risk/execution mechanics. RSI, OI, liquidation semantics, repetitive-size tests and source-health windows are additional independent factors, **not yet wired** to the primitive.

## Shortest dependent delivery path

1. **This slice:** publish the pure common flow observation and focused unit tests; no runtime integration or new numeric policy thresholds.
2. **Next slice:** connect existing verified event/time adapters (one focused symbol at a time) and closed DMI/RSI to shared read-only Robot observation; call the *same module* in SIMULATION. Keep data gaps fail-closed for book-dependent evidence.
3. **Evidence gate:** replay ICNT positive and false 14:02/14:10 observations, then frozen multi-symbol positive/negative matched cohorts. Compare baseline Robot entries vs factors, with availability-time discipline, spread, fees, fill, slippage, latency, MAE/MFE, net expectancy and stop frequency. No tune-on-test.
4. **Only with positive independent results and owner approval:** attach versioned factors to existing Robot strategy/admission/risk boundary, preserve STOP/TAKE/PAPER authority; merge, sync, independently approve safe VPS release. LIVE remains prohibited.

**No edge, entry timing improvement, profitable backtest, or production trade authorization is claimed by this document or the initial module.**
