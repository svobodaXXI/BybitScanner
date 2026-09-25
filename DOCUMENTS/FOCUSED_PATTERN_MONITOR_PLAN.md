# Focused Pattern Monitoring After Scanner Discovery

Status: PLANNED / NOT IMPLEMENTED  
Date: 2026-09-25  
Scope: post-discovery monitoring of symbols that remain structurally interesting after the full Scanner has moved on.

## 1. Problem

A full-universe Scanner pass is intentionally sequential and may take a long time.

Example:

1. Scanner sees a forming Wedge/Triangle on RDDTUSDT 5m;
2. Robot starts monitoring that known setup;
3. Scanner continues through hundreds of other tickers;
4. much later the original breakout develops;
5. while Scanner is elsewhere, the same symbol may form:
   - mirror-level retest;
   - bare-candle continuation trigger;
   - L-shape;
   - Ikigai Box;
   - future Flag/channel;
   - another distinct Wedge/Triangle.

Waiting for the next full-universe pass risks discovering a secondary structure too late.

The required architecture therefore needs two different monitoring roles:

- **known setup evolution**;
- **new pattern discovery on an already-interesting symbol**.

They must not be conflated.

## 2. Architectural split

### 2.1 Full Scanner

Purpose: discover interesting setups across the whole eligible universe.

It remains responsible for broad market discovery and the per-symbol multi-pattern contract:

```text
symbol
  -> all enabled 5m patterns
  -> all enabled 1m patterns
  -> next symbol
```

It must not stay blocked on one symbol waiting for a future breakout.

### 2.2 Robot candidate monitor

Purpose: evolve an **already known trading setup**.

Examples:

- breakout state;
- mirror-level retest;
- retest LIMIT;
- bare-candle entry rule belonging to the same setup;
- late admission of the same setup;
- fills;
- STOP/TAKE;
- recovery/reconciliation.

This belongs to the existing Robot lifecycle and should reuse
`RobotBreakoutMonitor` and related durable state.

### 2.3 FocusedPatternMonitor

Purpose: keep watching selected symbols for **new independent pattern observations**
after broad discovery has moved on.

Examples:

- a Triangle breakout is followed by a new Ikigai Box;
- a Wedge breakout is followed by an L-shape;
- a future Flag/channel forms after expansion;
- a second distinct accumulation/distribution structure appears.

The focused monitor is not a second full Scanner and not a Robot execution engine.

Its responsibility is:

```text
active watched symbol
    -> new closed candle
    -> run enabled pattern detectors
    -> create PatternObservation(s)
    -> normal Scanner/admission boundary
```

## 3. Mature-project principles adopted

Use the same broad separation found in mature event-driven trading systems:

- shared market-data provider/cache;
- independent strategy/detector consumers;
- discovery separated from execution;
- existing positions/candidates receive dedicated lifecycle monitoring;
- new signals are emitted through the normal signal/admission pipeline rather
  than being fabricated inside an execution engine.

For BybitScanner this means:

- Robot must **not** call the whole Scanner loop again;
- Robot must **not** own Ikigai/L-shape/Flag detectors;
- FocusedPatternMonitor must reuse the same detector implementations as Scanner;
- Scanner and FocusedPatternMonitor must reuse the same candle source/cache where practical;
- no duplicate per-pattern REST polling loops.

## 4. Durable watch registry

A Scanner discovery or Robot candidate may create a durable focused-watch subscription.

Conceptual record:

```text
FocusedSymbolWatch
    watch_id
    symbol
    source_timeframe
    parent_observation_id / candidate_id
    reason
    enabled_detector_families
    started_at
    structural expiry policy
    state = ACTIVE | EXPIRED | CLOSED
```

Possible reasons:

- WEDGE_FORMING;
- TRIANGLE_FORMING;
- BREAKOUT_EPISODE;
- OPEN_ROBOT_TRADE;
- POST_BREAKOUT_REVERSAL_WINDOW.

The watch is a monitoring subscription, not an order authorization.

## 5. Event flow

Target flow:

```text
FULL SCANNER
    |
    +--> PatternObservation
           |
           +--> Robot candidate monitor
           |      (same setup evolution)
           |
           +--> Durable FocusedSymbolWatch
                  |
                  +--> new 1m/5m closed candles
                         |
                         +--> Wedge/Triangle
                         +--> L-shape
                         +--> Ikigai Box
                         +--> future Flag
                                  |
                                  +--> new PatternObservation
                                          |
                                          +--> normal admission
```

The full Scanner can continue scanning other symbols immediately.

## 6. Same-setup vs new-setup ownership rule

This distinction is binding.

### Same setup evolution -> Robot candidate monitor

Examples:

- breakout of the original Wedge;
- return to its mirror level;
- original setup's retest;
- original setup's bare-candle trigger;
- entry repricing and late admission.

These events modify/evolve the same durable candidate.

### New structure -> FocusedPatternMonitor

Examples:

- new Box after a Wedge/Triangle breakout;
- new L-shape after expansion;
- new Flag/channel;
- distinct later Wedge/Triangle.

These must create a new PatternObservation with their own pattern identity and
provenance.

Do not mutate the original candidate into a different pattern.

## 7. Market-episode model

The monitor should preserve a lightweight causal/provenance link between
related observations without merging them into one trade.

Conceptually:

```text
ACCUMULATION
  Wedge / Triangle / future Flag-channel
        |
        v
BREAKOUT / EXPANSION
        |
        v
POST-BREAKOUT STRUCTURE
  Box / L-shape / another compression
        |
        v
REVERSAL or CONTINUATION
```

One market episode may therefore produce several independent trade candidates.

Example:

```text
Trade A: Triangle breakout SHORT
Trade B: later Box reversal LONG
```

Each trade keeps its own:

- candidate_id;
- pattern provenance;
- entry;
- STOP;
- TAKE;
- fills;
- protection;
- journal/recovery state.

## 8. Existing-symbol ownership and WAIT_FOR_FLAT

Current Robot safety assumes one provable Robot owner/exposure on a symbol.

Therefore a new opposite-direction pattern that appears while an earlier Robot
trade is still OPEN must not silently open a second conflicting position.

Initial policy:

```text
new PatternObservation
    + existing OPEN Robot trade on same symbol
        -> persist observation
        -> WAIT_FOR_FLAT
        -> when flat, re-check freshness/eligibility
        -> admit if still valid
        -> otherwise expire
```

Do not implement automatic close-and-reverse in this first slice.

A later explicit design may authorize close-and-reverse, but it is not implied
by focused monitoring.

## 9. Watch lifetime

Focused watches must not live forever.

Expiry should be structural rather than a single arbitrary wall-clock timeout.

A watch may remain ACTIVE while at least one is true:

- parent candidate is APPROVED/OPEN;
- breakout episode remains structurally current;
- post-breakout reversal/continuation window remains valid;
- a secondary observation is WAIT_FOR_FLAT and still fresh.

Terminate when:

- parent setup is structurally stale;
- price invalidates the episode;
- all child observations expire/close;
- no active candidate/trade remains and the post-breakout watch window closes.

Exact structural windows remain pattern-owned and must be specified before code
implementation. Do not invent one global N-candle TTL.

## 10. Market-data strategy

Focused monitoring should use the existing runtime market-data infrastructure
rather than new independent polling processes.

Preferred sources:

- Robot's existing symbol-specific market-data subscriptions/cache where the
  required timeframe evidence is already available;
- existing Scanner candle loader only where a closed-candle series is required
  and no cache representation exists.

Desired long-term boundary:

```text
shared market data/cache
    -> Full Scanner
    -> FocusedPatternMonitor
    -> Robot candidate monitor
```

Do not introduce:

- one REST loop per detector;
- one process per watched symbol;
- Robot-triggered full-universe Scanner calls;
- a second execution journal or Robot lifecycle.

## 11. Diagnostics

For every watched symbol/timeframe, diagnostics should show:

- watch active / inactive;
- latest closed candle consumed;
- detector invoked;
- no structure;
- rejected by pattern eligibility;
- duplicate observation;
- WAIT_FOR_FLAT;
- admitted;
- expired;
- detector exception.

This is internal/logging evidence, not Telegram spam.

## 12. Implementation sequence

### Phase 1 — prerequisite Scanner architecture

Complete `SCANNER_MULTIPATTERN_ORCHESTRATION_PLAN.md`:

- one snapshot per symbol/timeframe;
- detector fan-out;
- multi-observation collection;
- plural envelope candidates.

### Phase 2 — focused watch registry

Add durable watch identity/state only.

No trading side effect.

### Phase 3 — FocusedPatternMonitor

Subscribe only to active watched symbols and evaluate closed-candle detector
fan-out.

Reuse the same detector modules as Full Scanner.

### Phase 4 — observation/admission bridge

Route new focused observations through the same normalized Scanner/Robot
admission boundary used by ordinary discovery.

### Phase 5 — WAIT_FOR_FLAT

Persist opposite/conflicting observations without execution while a prior trade
owns the symbol; revalidate when the symbol becomes flat.

### Phase 6 — future extensions

Only after the above is stable:

- future Flag detector;
- explicit close-and-reverse policy, if owner-authorized;
- richer market-episode analytics.

## 13. Verification

Minimum required focused checks:

1. full Scanner can leave a symbol while focused watch continues;
2. focused watch receives later closed candles for that symbol;
3. mirror/retest evolution stays with the original candidate monitor;
4. a newly formed Box/L-shape becomes a new observation, not a mutation of the original candidate;
5. active trade + opposite new observation results in WAIT_FOR_FLAT, not a second conflicting position;
6. once flat, stale child observation expires and fresh child observation can proceed;
7. no duplicate candle fetch loops/processes are introduced;
8. unrelated symbols are not added to focused monitoring without a durable reason.

Final real acceptance remains owner-run and must be integrated into the normal
full-pass/runtime acceptance policy.

## 14. Non-goals

This plan does not authorize:

- LIVE trading changes;
- multiple simultaneous Robot owners on one symbol;
- close-and-reverse;
- universal pattern geometry;
- detector threshold changes;
- a second Scanner process;
- a second Robot lifecycle;
- continuous monitoring of the whole universe outside the existing Scanner.

## 15. Completion criterion

Done means that after Full Scanner discovers an interesting setup and moves on,
the project continues to monitor that symbol efficiently for both:

1. evolution of the original setup, via the Robot candidate monitor; and
2. emergence of new independent structures, via FocusedPatternMonitor,

without requiring the next full-universe scan and without coupling pattern
detection into the Robot execution engine.
