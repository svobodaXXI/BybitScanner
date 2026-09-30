# Broadening Formation / «Рупор» — Scanner plan

Status: DESIGN / QUEUED  
Owner evidence: ENAUSDT 1m, 2026-09-30  
Depends on: GEO-U1 Universal Pivot-Consensus Envelope Geometry

## 1. Owner observation

The owner supplied a Scanner chart and a TradingView re-markup for ENAUSDT 1m.

Current Scanner output labeled the structure as a compressing triangle, but the owner's manual geometry indicates:

- the upper boundary should begin from the later/higher edge of the local episode rather than the earlier Scanner-selected upper anchor;
- the lower boundary should begin from the next meaningful opposite extremum;
- with those anchors, the two boundaries **diverge** rather than converge;
- the resulting structure is therefore not a wedge/compression triangle but a broadening formation / megaphone («Рупор»).

The screenshot is visual evidence only until exact source-time OHLC and historical cutoff are recovered.

## 2. Why this belongs in the universal geometry layer

This is not a symbol-specific ENA fix.

The failure class is:

1. wrong local episode / anchor selection;
2. line pair chosen before enough multi-pivot evidence is considered;
3. converging-vs-diverging classification becomes wrong as a consequence.

GEO-U1 must construct both boundaries from the same deterministic pivot-consensus mechanism. Pattern classification happens only after the two boundaries and their local episode are fixed.

## 3. Broadening Formation definition for BybitScanner

Working name:
- EN: Broadening Formation / Megaphone
- RU: Рупор

A candidate is eligible for this family when:

- both boundaries belong to one local episode;
- both have sufficient distributed pivot consensus;
- price materially interacts with both sides;
- pair width increases from start to end rather than compresses;
- the widening is not caused by one isolated outlier pivot;
- body-integrity/locality/historical-cutoff rules remain valid.

The exact sub-taxonomy (broadening wedge, ascending/descending broadening formation, symmetric megaphone) is deferred until enough owner examples exist.

## 4. Shared geometry classification

After GEO-U1 produces a valid EnvelopePairConsensus:

- end_width < start_width -> converging family candidate:
  - wedge / triangle / compression depending on slope relation and pattern-specific rules;
- end_width approximately equal to start_width -> channel/range-like, not a compression signal by default;
- end_width > start_width -> **broadening family candidate**.

Do not classify as Wedge/Triangle merely because the pair has two valid lines.

The width relation must be measured on the accepted consensus boundaries, not on raw seed lines.

## 5. Anchor handling

The ENAUSDT case reinforces the owner anchor rule:

- first boundary anchor must correspond to the actual local terminal extreme that starts the formation episode;
- the opposite boundary begins from the next meaningful confirmed opposite extremum of the same episode;
- later line fitting/ranking must not rescue an earlier wrong anchor pair merely because it yields a visually neat converging figure.

GEO-U1 should therefore expose:
- local episode start;
- first accepted same-side extreme;
- next accepted opposite extreme;
- all inlier pivots supporting each boundary;
- any rejected earlier seed and its rejection reason.

## 6. Scanner product behavior

The owner now wants Broadening Formation included in Scanner search.

Future Scanner integration:
- detect it as an independent pattern family;
- send a normal Telegram chart/card under the same product conventions as other patterns;
- include it in per-symbol multi-pattern orchestration;
- preserve independent symbol × timeframe × pattern × formation identity;
- do not suppress Wedge/Triangle/Box/L-shape merely because a Broadening Formation also exists.

Trading/Robot behavior is **not authorized** by this plan. The owner currently wants detection/search first. No Robot button until a separate strategy/risk contract exists.

## 7. Validation path

1. Recover exact ENAUSDT 1m source-time candles and decision cutoff from runtime artifacts if available.
2. Freeze it as:
   - negative control for the old false compression classification;
   - positive control for Broadening Formation once exact anchors are authoritative.
3. Add at least one genuine converging Wedge/Triangle control so the change does not simply flip classifications.
4. Run GEO-U1 shadow metrics:
   - consensus boundaries;
   - width_start / width_end;
   - width_change;
   - two-sided oscillation;
   - support/touch clusters.
5. Only after separation is demonstrated, enable Broadening Formation classification in production.
6. Final acceptance remains one complete real Scanner/Telegram pass.

## 8. Non-goals

- no ENA-specific threshold;
- no chart-only relabel;
- no Robot/trading rules yet;
- no LIVE work;
- no implementation during the currently active G6 run.

## 9. Queue identity

Task ID: **GEO-U2 — Broadening Formation / «Рупор» Scanner family**

Dependency: GEO-U1.
