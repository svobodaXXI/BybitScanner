# RSR-ANCHORS-2 — read-only research handoff

Status: RESEARCH COMPLETE, IMPLEMENTATION NOT STARTED (owner decision pending).
Date: 2026-10-13. Base: `stable/adfb50b-forward` @ `0fc3331` (after PR #491, TRI-START-3).
Scope: evidence only. No Geometry Engine, test, Gold or threshold change was made.

## Owner-confirmed reference (RSRUSDT 5m, Bybit linear)

Window: 200 candles, index 0 = 2026-10-11 17:10 UTC (`1791738600000`),
index 199 = 2026-10-12 09:45 UTC (`1791798300000`) = decision bar.
The window matches the G-TRI-1 original report pivots exactly (offset 0).
The 10:00 UTC breakdown candle (`1791799200000`) is after the decision bar and is not used.

| Anchor | Index | UTC | Price |
|---|---|---|---|
| Upper A1 | H144 | 2026-10-12 05:10 | 0.0025760 (high) |
| Upper A2 | H192 | 2026-10-12 09:10 | 0.0023975 (high) |
| Lower B1 | L148 | 2026-10-12 05:30 | 0.0022359 (low) |
| Lower B2 | L178 | 2026-10-12 08:00 | 0.0022518 (low) |

Screenshot binding: chart time = UTC+3, log price scale; the anchors were bound from the owner
TradingView screenshot and confirmed as the strict convex hull of highs/lows before the breakdown.

Scanner baseline at `0fc3331`: `[153,188,148,190]` (H153→H188 / L148→L190), Triangle Compression detected.

## Root cause at baseline (two independent stages)

1. **Upper — pivot filter.** H192 is a raw 3/3 pivot but `pivots.filter_pivots(min_change=0.003)`
   drops it: |0.0023975 − 0.0024023| / 0.0024023 = 0.20 % < 0.3 % versus the last kept high H188,
   although the opposite pivot L190 lies between them (a new swing).
2. **Lower — candidate generator.** L148→L178 is never built: `build_candidate_lines`
   requires `min_confirmations=2`; only L178 is within 0.6 % (L161 4.86 %, L170 3.02 %,
   L183 2.98 %, L190 3.12 %).

Counterfactual with only H192 restored: H144→H192 is generated (confirmed by H188 0.42 % and H192)
and passes validation, locality, boundary, anchor sequence and freshness; winner `[144,192,148,183]`.

## Variants tested (monkeypatched copies of `0fc3331`, read-only)

- **T** — Triangle-only two-point boundary: extra lines through two confirmed same-side pivots
  (span ≥ 30) where no confirmed same-side pivot after the first anchor (up to the decision bar)
  lies beyond the line (hull edge). Added after `filter_candidates`; admitted only when
  `anchor_sequence.family == "triangle"`; all existing gates unchanged; `min_confirmations`
  not lowered globally.
- **P** — global alternation-aware pivot filter: a same-side pivot within `min_change` of the last
  kept one is still kept when a raw opposite pivot between them deviates from the last kept price
  by ≥ `min_change` (noise protection retained: e.g. H157, H168 stay dropped).
- **Q+T** — T plus extra lines generated from the P pivot list, admitted only for triangles; the
  global pivot lists passed to evaluation remain unchanged.

## Results

Regression set: Geometry Gold `manifest_v1` (PONS, 1000BONK, 1000TOSHI, 1000XEC, AEVO),
`manifest_g_tri_2` (KAS, LIT, MANA, MEGA, ARX), KERNEL and RSR exact G-TRI-1 windows,
all 11 `geometry_formation_fit` cases.

| Variant | RSR result | Other changes |
|---|---|---|
| Base | `[153,188,148,190]` | — |
| T | `[144,184,148,178]` (lower exact, upper H184 not H192) | **none** |
| P | `[144,192,148,183]` | PONS, TOSHI, AEVO, MEGA fail; KERNEL → None; MANA/ARX get a (non-forbidden) geometry; formation_fit INJ, WLD, XRP, PONS, AEVO, AAVE, AZTEC change |
| P+T | **`[144,192,148,178]` — exact owner reference** | same breakage as P |
| Q+T | `[144,184,148,178]` | **none** |

P+T ranked pool for RSR (key: CANONICAL, −body breaches, score; all fresh, EXPLORATORY):
`[144,192,148,178]` 0 breaches 221.31 (2-pt) > `[144,188,148,178]` 0 / 221.22 > `[144,184,148,178]` 0 / 215.33
> `[144,192,148,183]` 2 / 224.41 > … > old winner `[153,188,148,190]` 4 / 225.53.
The exact reference wins on body breaches, but its score margin over `[144,188,…]` is only 0.09 (fragile).

## Conclusion

- T is a clean, narrow fix for the lower boundary (no regressions in the set above).
- The exact upper anchor H192 is reproduced only by the global pivot change P, which is a disputed
  general-rule change (breaks 4 Gold cases and KERNEL). Per task rule 7, implementation stopped.
- Under Q+T, why H144→H192 still loses to H144→H184 was **not** investigated.

## Options for the owner

1. Implement T only; regression asserts `[144,184,148,178]` (partial reference).
2. T now, plus a separate narrow task to explain why the Q-generated H144→H192 line does not win
   without changing global pivots.
3. P+T: exact reference, but requires an owner-approved global pivot-rule change and re-baselining
   PONS, TOSHI, AEVO, MEGA, KERNEL and formation_fit.

Assistant recommendation: option 1 now, option 2 as a separate task.

## Reproduction notes

OHLC source: Bybit public `v5/market/kline` (category=linear, symbol=RSRUSDT, interval=5); window
selected by exact equality with the G-TRI-1 report pivots (`recover.py` method). The RSR OHLC window
has not yet been frozen as a repository fixture; experiment scripts were scratch-only and are not
part of the repository.
