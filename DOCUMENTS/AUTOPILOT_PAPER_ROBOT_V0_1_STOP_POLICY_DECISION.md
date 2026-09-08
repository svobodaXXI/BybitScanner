# BybitScanner — PAPER Robot v0.1 STOP Policy Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

Purpose: define the initial STOP-selection policy for the minimal PAPER Falling Wedge 1m robot prototype without introducing a parallel STOP engine or duplicate market-data computation.

---

# 1. SCOPE

Applies only to the first PAPER robot prototype setup:

- pattern: `Falling Wedge`;
- timeframe: `1m`;
- direction: `LONG`;
- entry mode: confirmed upside breakout;
- execution: existing common PAPER order/protection lifecycle.

This decision does not authorize runtime implementation or LIVE trading.

---

# 2. ACCEPTED STOP POLICY

After the qualifying 1m breakout candle closes above the admitted upper Falling Wedge boundary and an entry is otherwise admissible:

1. use the already-available breakout candle from the existing scanner/market-data path;
2. derive the candidate STOP from the breakout candle low;
3. place the STOP slightly below that low using a small technical buffer;
4. measure STOP distance from the actual entry/fill price;
5. if the resulting STOP distance exceeds `2%`, reject the trade before opening exposure;
6. if the distance is `<= 2%`, submit the STOP through the existing common STOP/protection execution lifecycle.

Conceptually:

```text
candidate_stop = breakout_candle.low - technical_buffer
stop_distance = (actual_entry - candidate_stop) / actual_entry

if stop_distance > 2%:
    NO TRADE
else:
    submit STOP through common execution/protection path
```

The `2%` threshold and exact technical-buffer definition remain `NEEDS VALIDATION` as trading parameters, while the architectural ownership boundary below is `ACCEPTED DESIGN`.

---

# 3. OWNERSHIP / REUSE BOUNDARY

The robot does NOT own a separate STOP engine.

The robot policy owns only:

- selecting the stop level;
- applying the trade-admission distance rule;
- emitting the resulting protection intent.

Existing shared infrastructure remains authoritative for:

- breakout candle data;
- actual entry/fill price;
- quantity/position state;
- STOP order creation;
- STOP lifecycle/state;
- protection synchronization;
- close/reconciliation/accounting events.

No robot-specific market-data reader, extremum detector, STOP state store, or duplicate order lifecycle is introduced for this policy.

---

# 4. RATIONALE

This policy is selected for the first prototype because it:

- reuses already-computed breakout evidence and OHLC data;
- ties risk to the actual confirmation candle rather than an unrelated fixed price percentage;
- prevents exceptionally large breakout candles from creating an uncontrolled structural STOP;
- requires only a small policy calculation on the robot path;
- preserves the common PAPER/LIVE execution architecture for later evolution;
- can later be replaced by another `StopPolicy` without changing execution.

Future candidate policies may include structural-extremum, pattern-boundary, ATR/volatility, or adaptive policies, but they must reuse the same execution/protection contract rather than create parallel STOP machinery.

# END_OF_DOCUMENT
