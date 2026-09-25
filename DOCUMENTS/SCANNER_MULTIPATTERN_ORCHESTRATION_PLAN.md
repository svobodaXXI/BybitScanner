# Scanner Multi-Pattern Per-Symbol Orchestration Plan

Status: PLANNED / NOT IMPLEMENTED  
Date: 2026-09-25  
Owner intent: for each ticker, Scanner must exhaust all enabled pattern families on 5m and 1m before moving to the next ticker.

## 1. Problem statement

The desired Scanner contract is **multi-signal per symbol**, not "first/best signal per symbol".

For every eligible ticker, Scanner must:

1. obtain the 5m candle snapshot;
2. evaluate **all enabled pattern families** on that same 5m snapshot;
3. emit every independently valid 5m signal;
4. obtain the 1m candle snapshot;
5. evaluate **all enabled pattern families** on that same 1m snapshot;
6. emit every independently valid 1m signal;
7. only then advance to the next ticker.

A signal from one detector must never short-circuit sibling detectors or the second timeframe.

Target traversal:

```text
SYMBOL A
  5m snapshot
    -> Wedge family
    -> Triangle Compression
    -> L-shape
    -> Ikigai Box
    -> collect all valid observations/signals
  1m snapshot
    -> Wedge family
    -> Triangle Compression
    -> L-shape
    -> Ikigai Box
    -> collect all valid observations/signals
NEXT SYMBOL
```

The order above is an orchestration contract, not a ranking contract. Pattern families remain independent.

## 2. Current repository facts

Current `main.py::run_scan_pass()` already loops in the outer order:

```text
for symbol in symbols:
    for timeframe in ("5", "1"):
```

and L-shape / Ikigai Box are invoked before Wedge/Triangle notification handling. Therefore a found Wedge does not currently contain an explicit `break` or `return` that skips 1m or the other independent detectors.

However, two architectural limitations remain:

### 2.1 Candle ownership is still coupled to the envelope analyzer

`analyzer.analyze_symbol()` owns candle loading and also runs Wedge/Triangle geometry, confirmation, chart and report side effects. L-shape and Box receive the resulting `analysis_result["data"]`.

This means independent detectors are logically separate but their market-data snapshot is still obtained through one pattern-family coordinator. A failure inside that coordinator can prevent the shared snapshot from reaching sibling detectors.

### 2.2 Envelope geometry is single-winner

`geometry.engine.analyze_geometry()` evaluates many upper/lower candidate pairs but ultimately selects and returns one `best_geometry`.

`wedge.analyzer.analyze_wedge()` then classifies only that geometry into one of:

- Falling Wedge;
- Rising Wedge;
- Triangle Compression;
- No wedge / Unknown.

Therefore the current envelope family cannot emit multiple independently valid envelope structures on the same `symbol x timeframe` even when several candidate geometries survive validation.

This is a real multi-signal limitation and is separate from L-shape or Ikigai Box.

## 3. Mature-project design principles to reuse

The implementation should follow the same broad separation used by mature trading engines such as Hummingbot V2 and QuantConnect LEAN:

### Shared market-data snapshot, multiple independent consumers

One market-data provider/snapshot feeds several independent strategy/detector modules. A detector does not own the market-data acquisition loop for its siblings.

For BybitScanner this means:

```text
Candle snapshot
    |
    +--> Envelope detectors
    +--> L-shape detector
    +--> Ikigai Box detector
```

Do not create four independent ticker loops or four independent network fetches for the same `symbol x timeframe`.

### Collect observations, do not stop at first match

The Scanner boundary should conceptually produce a collection of observations:

```text
PatternObservation[]
```

rather than one global `best_pattern`.

Ranking may still exist **inside a detector family** to remove duplicate representations of the same structure, but a winner in one family must not suppress a different valid family.

### Detector-specific geometry remains detector-specific

Do not create a universal geometry engine merely to support multi-pattern scanning.

Keep:

- Wedge/Triangle: envelope / trendline geometry;
- L-shape: HIGH/LOW -> trough -> breakout topology;
- Ikigai Box: impulse -> box -> second-leg topology.

Unify only orchestration, source snapshot metadata, stable observation identity, delivery sequencing and error isolation.

## 4. Planned implementation

### Slice A — per-timeframe fan-out

Introduce a Scanner-owned `symbol x timeframe` snapshot boundary.

Required behavior:

1. fetch candles once for `symbol x timeframe`;
2. pass the exact same snapshot to every enabled detector;
3. isolate each detector's failure so one detector/chart/report error cannot suppress siblings;
4. complete all enabled detectors for 5m before starting 1m;
5. complete all enabled detectors for 1m before advancing to the next symbol.

No parallel process, message bus or new Scanner service is needed.

### Slice B — normalized collection boundary

Add a thin internal collection contract for Scanner observations. It may initially remain an in-process Python structure, but it must represent multiple observations from the same symbol/timeframe.

Minimum identity/provenance:

- symbol;
- timeframe;
- pattern family/name;
- direction where applicable;
- source/decision candle timestamp;
- detector-specific frozen identity/anchors;
- detector version or equivalent provenance where already available.

Do not make Robot execution depend directly on this collection. Scanner detection and Robot admission remain separate boundaries.

### Slice C — envelope multi-candidate support

Add a bounded plural geometry API, e.g. `analyze_geometries()`, that returns all independently eligible current envelope candidates needed by Scanner.

Constraints:

- preserve existing validation/locality/freshness/anchor rules;
- preserve deterministic ranking;
- deduplicate multiple line-pair representations of the **same** formation;
- do not emit every raw candidate pair;
- allow distinct valid structures to survive even if they have different pattern classifications;
- keep the existing single-result API as a compatibility wrapper where other callers still require one winner.

The goal is not "maximum number of signals". The goal is "all distinct valid current structures".

### Slice D — delivery/admission independence

Each resulting Scanner observation gets its own existing family-specific delivery/admission treatment.

Examples:

- Wedge/Triangle: existing quality/filter/signal-memory/Telegram path;
- L-shape: existing L-shape eligibility and Telegram path;
- Ikigai Box: existing confirmed/WATCH logic and Box Robot handoff rules.

One observation must not overwrite or suppress another merely because it shares the ticker.

Signal memory must stay scoped by at least `symbol x timeframe x pattern` plus stable formation identity where available.

## 5. Required behavioral invariants

The implementation is incomplete unless these invariants hold:

1. **No first-signal short-circuit** — finding any pattern does not end the timeframe or symbol pass.
2. **5m then 1m per ticker** — next ticker cannot begin until both timeframes finish.
3. **One snapshot per symbol/timeframe** — all sibling detectors consume the same candle evidence.
4. **Independent errors** — one detector/render/delivery failure does not suppress sibling detection.
5. **Multi-signal delivery** — several different valid patterns on one ticker/timeframe may all be delivered.
6. **No raw-candidate spam** — plural envelope support deduplicates equivalent geometry representations.
7. **Independent signal memory** — dedup state cannot collide across timeframe/pattern/formation.
8. **Robot stays separate** — multiple Scanner signals do not automatically authorize multiple Robot positions/orders.
9. **Full-pass acceptance unchanged** — final owner acceptance remains one complete real pass over all eligible tickers, both timeframes and all connected pattern families with normal Telegram delivery.

## 6. Diagnostics needed for disputed cases

For future examples such as "Wedge was sent but a visible L-shape on the same chart was not", the Scanner should be able to prove that every detector actually ran for that `symbol x timeframe`.

Minimal structured diagnostics should distinguish:

- detector invoked;
- no structure;
- structure found but eligibility rejected;
- duplicate already delivered;
- delivery failure;
- detector exception.

Do not add verbose Telegram diagnostics; console/log evidence is sufficient.

This prevents a detector-rule rejection from being confused with an orchestration short-circuit.

## 7. Non-goals

This task does **not** authorize:

- changing L-shape/Box/Wedge geometry rules merely to increase signal count;
- running each pattern in a separate process;
- repeated REST fetches per detector;
- broad async/concurrency conversion;
- a new universal pattern engine;
- automatic Robot admission for every simultaneous Scanner signal;
- LIVE execution changes.

## 8. Verification plan

Use minimal focused verification:

1. traversal test proving:
   `A:5m all -> A:1m all -> B:5m all -> B:1m all`;
2. fan-out test proving all enabled detectors receive the same snapshot object;
3. error-isolation test proving one detector failure does not block siblings or 1m;
4. envelope plural-candidate tests proving:
   - equivalent geometry representations dedupe;
   - two distinct valid current structures can both survive;
   - legacy single-winner compatibility remains unchanged for callers that still use it;
5. final owner acceptance only through the existing full real Scanner pass rule.

Do not add broad suites or repeat already-green unrelated checks.

## 9. Completion criterion

Done means the production Scanner can, for one ticker, emit every independently valid enabled pattern on 5m and 1m, with no first-match short-circuit, using one shared snapshot per timeframe, and then move to the next ticker.

