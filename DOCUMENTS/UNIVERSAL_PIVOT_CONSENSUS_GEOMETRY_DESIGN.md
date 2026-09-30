# Universal Pivot-Consensus Geometry — future design

Status: DESIGN / QUEUED, no production authorization  
Owner direction: 2026-09-30  
Scope: shared two-boundary geometry for Wedge, Triangle, Triangle Compression / squeeze and future related envelope patterns.

## 1. Problem statement

Current BybitScanner geometry already has pivot-based candidate generation, ATR-normalized touch diagnostics, body-integrity gates, locality, compression metrics and ranking. The owner wants the next generation to make the boundary itself emerge from repeated market confirmation:

- a boundary should be supported by many relevant pivots/extrema, not merely by one anchor pair;
- isolated local pierces may be tolerated when the majority of extrema still form one coherent line;
- both boundaries should be materially used by price: repeated oscillation from one side to the other is preferred over structures that hug only one side;
- the terminal part should preserve genuine compression / squeeze structure instead of selecting a visually convenient pair of lines;
- the same geometric search principle should feed Wedge, Triangle and Compression rather than each pattern inventing its own trendline finder.

CASHCATUSDT 1m owner comparison (Scanner chart vs TradingView drawing, 2026-09-30) is the current visual target. It is VISUAL_ONLY until exact source-time OHLC/cutoff is frozen.

ENAUSDT 1m owner comparison (Scanner false compression vs TradingView broadening re-markup, 2026-09-30) is the first visual reference showing why converging-vs-diverging classification must happen only after correct local anchors and consensus boundaries are established. Exact source-time OHLC/cutoff must be recovered before it becomes numeric Gold evidence.

## 2. External implementations surveyed

Research concepts only; no external code is copied.

### pytrendline — ednunezg/pytrendline
https://github.com/ednunezg/pytrendline

Useful ideas:
- enumerate trendline hypotheses from point pairs;
- require a minimum number of near-line points;
- use explicit distance tolerance;
- reject/penalize candle-body crossings;
- group/deduplicate similar lines;
- restrict search to pivots for performance.

### trendln — GregoryMorse/trendln
https://github.com/GregoryMorse/trendln

Useful ideas:
- extrema-first support/resistance construction;
- several search backends, including Hough-style line discovery;
- windowed best-line selection rather than one global line over all history.

### trend-line-detector — mvpp/trend-line-detector
https://github.com/mvpp/trend-line-detector

Useful ideas:
- Williams-fractal pivots;
- at least three pivot touches;
- candle-through validation;
- composite line quality from touch count, span, recency and fit;
- deduplication of near-equivalent lines.

### Auto Trendlines — casoon/pine-scripts
https://github.com/casoon/pine-scripts/tree/main/indicators/market_structure/auto_trendlines

Useful ideas:
- combinatorial pivot-pair hypotheses;
- refit through all inlier pivots rather than keeping the raw seed pair;
- ATR-based tolerance;
- optional outward/outer-envelope refinement;
- composite score using touches, span, fit tightness and violations.

### SRLines — FXDavid-OffbeatForex/SRLines
https://github.com/FXDavid-OffbeatForex/SRLines

Useful ideas:
- a touch counts as a new test only after price has moved away sufficiently, preventing dense consolidation pivots from inflating strength;
- wick pokes need not immediately kill a level; body-close evidence can be treated more seriously.

## 3. BybitScanner design choice

Do **not** adopt stochastic RANSAC or a black-box ML line fitter. Determinism, historical replay stability and exact owner-debuggability are project requirements.

Use a deterministic **pivot-consensus envelope**:

1. generate admissible line seeds from confirmed pivot pairs;
2. collect all same-side pivots that fall inside an ATR-normalized inlier band;
3. require evidence to be distributed across the structure, not concentrated in one tiny cluster;
4. refit a consensus line through the inlier set;
5. shift/refine it outward only when needed to preserve support/resistance envelope semantics;
6. evaluate violations and distinct touches;
7. build upper/lower pairs from the strongest independent consensus boundaries;
8. evaluate two-sided oscillation and compression;
9. only then classify the pair as Wedge / Triangle / Compression.

This is RANSAC-like in spirit but exhaustive and deterministic.

## 4. Proposed shared data model

### BoundaryConsensus

For each upper/lower boundary record:

- seed anchors;
- fitted slope/intercept;
- inlier pivot indices;
- distinct touch-cluster indices;
- touch_count_distinct;
- support_span;
- support_coverage_ratio;
- mean/max ATR-normalized residual;
- isolated excursion count;
- sustained body-breach runs;
- first/last confirmed touch;
- outward envelope shift, if any;
- deterministic quality tuple.

Important: multiple adjacent pivots from one congestion zone count as one **touch cluster** until price has moved away by a defined separation distance and returned.

### EnvelopePairConsensus

For an upper/lower pair record:

- both BoundaryConsensus objects;
- common local episode / START / END;
- width at start/end;
- compression ratio;
- alternating touch sequence;
- cross-boundary traversal count;
- balance of touches between sides;
- fraction of meaningful swings that reach the opposite boundary band;
- apex/intersection diagnostics when relevant;
- locality and historical-stability evidence.

## 5. Universal search pipeline

### Stage A — pivot extraction

Reuse the existing confirmed-pivot path and historical cutoff semantics. No hindsight pivots.

### Stage B — deterministic line hypotheses

For each side:

- enumerate chronologically admissible pivot pairs inside the allowed local episode;
- prune impossible slope direction/chronology before expensive scoring;
- each pair is only a seed, not automatically the final line.

Expected cost for typical 10–30 pivots remains manageable: pair seeds O(P²), consensus collection O(P) per seed. If later profiling proves this too slow, optimize after correctness rather than weakening geometry.

### Stage C — consensus inliers

For each seed:

- compute pivot-to-line residual normalized by ATR;
- form an inlier set inside a calibrated band;
- require at least a minimum number of **distinct touch clusters**, not merely raw pivots;
- require support to span a meaningful share of the candidate interval.

Initial implementation must reuse/extend the current `geometry.touches` and envelope metrics rather than create a parallel touch engine.

### Stage D — consensus refit

Refit the line using all inlier pivots.

Preferred deterministic method:
- ordinary/weighted least squares on inliers;
- optional deterministic outer-envelope shift after refit so upper resistance does not move inside the accepted high-pivot cloud and lower support does not move inside the low-pivot cloud.

Do not introduce random sampling.

### Stage E — excursion / violation semantics

Preserve the existing important distinction:

- isolated wick/local pierce: tolerable diagnostic when consensus remains strong;
- repeated/sustained body violation: structural reject;
- post-END breakout: not a reason to invalidate the historical formation.

The existing seven-consecutive-body-breach rule remains authoritative until owner evidence changes it. The new consensus layer must not silently weaken it.

### Stage F — two-sided oscillation

Add a universal pair metric for whether price actually uses **both** boundaries.

From ordered touch clusters derive a side sequence, e.g.:

`U -> L -> U -> L -> U`

Metrics:
- alternating_touch_count;
- completed_cross_boundary_traversals;
- longest_same-side run;
- touch_balance;
- opposite_boundary_reach_ratio.

This directly captures the owner preference against patterns where price repeatedly hugs one side and does not complete meaningful swings toward the other.

Do not choose a universal hard threshold from one screenshot. Start as explicit diagnostics/ranking inputs and calibrate against Geometry Gold + new real references. Promote to a hard gate only if evidence shows a stable boundary across valid/invalid cases.

### Stage G — terminal compression / "arc" evidence

Do not fit a literal polynomial arc in v1.

Represent the owner's visible terminal "arc / squeeze" using the pivot sequence:

- shrinking pair width;
- contracting swing amplitudes;
- shortening/consistent terminal traversals when applicable;
- extrema remaining close to their consensus boundaries.

This remains a pair-level compression/terminal-shape metric. If later real cases prove that a curved boundary itself is required, that is a separate design decision.

### Stage H — pattern classification

The geometry engine returns one shared EnvelopePairConsensus. Pattern modules classify it:

- Falling/Rising Wedge: slope orientation + convergence + owner anchor chronology;
- Triangle variants: slope relation / horizontal-or-sloped side semantics;
- Triangle Compression / squeeze: compression plus valid two-sided envelope use;
- Broadening Formation / Megaphone («Рупор»): valid two-sided consensus with increasing pair width, after excluding widening caused only by isolated outliers;
- future two-boundary patterns: pattern-specific classifier on top of the same geometry.

Pattern-specific rules must not fork the underlying pivot-consensus line search.

## 6. Selection order

Future selector should prefer, lexicographically or via an explicitly inspectable score tuple:

1. hard-valid chronology/locality/body-integrity;
2. stronger two-boundary consensus;
3. more distinct touch clusters;
4. wider support span / coverage;
5. better alternating cross-boundary use;
6. tighter ATR-normalized residual;
7. fewer isolated excursions;
8. stronger terminal compression;
9. existing pattern-specific tie-breakers / freshness.

Avoid one opaque aggregate "quality" number masking a structural failure. Keep component diagnostics visible in Geometry Gold reports.

## 7. Integration with current code

Reuse first:
- `geometry/engine.py` orchestration;
- `geometry/touches.py` ATR-normalized distances/outlier vocabulary;
- `geometry/envelope_metrics.py` body-fit evidence;
- `geometry/compression.py` width/compression primitives;
- `geometry/pair_metrics.py` pair-level chronology/locality;
- `geometry/ranking.py` only as the final selector, not as a substitute for invalid construction.

Likely future modules:
- `geometry/consensus_boundary.py` — seed -> inliers -> refit -> touch clusters;
- `geometry/oscillation.py` — alternating upper/lower touch sequence and traversal metrics.

Do not create separate Wedge/Triangle/Compression line-fitting implementations.

## 8. Validation plan

### Reference recovery
- recover exact CASHCATUSDT 1m source-time candles/cutoff if available from runtime artifacts;
- freeze it as a real comparison case only after exact source evidence is recovered;
- retain the owner TradingView drawing as visual intent, not a numeric oracle.

### Geometry Gold expansion
Add cases only when exact candles + expected structural outcome are available:
- strong multi-touch both-side examples;
- isolated-pierce-but-valid examples;
- one-side-hugging negatives;
- false pair with many local points but poor span;
- historical stability under appended future candles.

### Shadow report before selector mutation
First compute consensus metrics beside the current winner and report deltas. No production winner change.

### Production cutover
Only after real references show a robust separation:
- switch candidate construction/selection in one bounded slice;
- preserve the existing G1–G5 regressions;
- then require the permanent full owner Scanner/Telegram acceptance.

## 9. Non-goals

- no ticker-specific thresholds;
- no machine learning;
- no random RANSAC;
- no literal curved-line fit in v1;
- no weakening of historical cutoff, locality or sustained body-integrity gates;
- no trading/Robot/risk change;
- no implementation during the active 2026-09-30 G6 run.

## 10. Queue identity

Task ID: **GEO-U1 — Universal Pivot-Consensus Envelope Geometry**

This is a future Geometry follow-up. It does not interrupt the currently running RVL-G6 acceptance. Implementation must begin with source recovery + shadow metrics, not with detector threshold tuning.
