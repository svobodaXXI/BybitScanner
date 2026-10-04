# Geometry Gold Inventory — RVL-G1

Status: COMPLETE INVENTORY / SCHEMA MAP  
Date: 2026-09-29  
Scope: repository evidence only; no runtime mutation.

## Purpose

Map the Geometry evidence already present in the repository before creating a new
`tests/fixtures/geometry_gold/` surface. The goal is to reuse exact frozen OHLC
where it already exists, keep screenshot-only material out of deterministic
replay, and make missing evidence explicit.

This inventory does not change detector behavior and does not replace the
owner's mandatory full-universe Scanner/Telegram acceptance.

## Evidence classes

### READY

A case is READY for deterministic Geometry Gold when the repository already
contains:
- exact/frozen OHLC for the relevant as-of window;
- enough provenance to identify the real incident/control;
- an existing expected geometry, negative assertion, or stable invariant that
  can be reused without inventing labels.

### RECOVERABLE

The real owner-observed case is known, but exact source-time OHLC and/or the
authoritative detection cutoff is not yet frozen. It may become Gold only after
that evidence is recovered.

### VISUAL_ONLY

The repository has a screenshot, annotation, outcome image, or qualitative
training note, but the inspected tracked evidence does not establish an exact
source-time candle window suitable for deterministic detector replay.

Visual references remain useful for training/triage but are not promoted to
Geometry Gold by relabelling a screenshot.

## READY — exact repository OHLC already frozen

### 1. Formation-fit historical pack

Source:
`tests/fixtures/geometry_formation_fit/historical_cases.json`

This is the strongest existing reusable Geometry evidence. It contains eleven
real 200-bar historical windows with recorded prior/expected geometry evidence:

- INJ
- WLD
- XRP
- PONS
- POL
- AEVO
- AAVE
- AZTEC
- HIMS
- QQQ
- CHIP

The existing regression
`tests/test_geometry_formation_fit.py` already exercises the real production
geometry engine against these candles and preserves formation-fit/body-boundary
evidence. Several cases intentionally expect no selected geometry after the
corrected admission rules; they are valuable negative controls rather than
missing data.

Reuse rule: do not duplicate these candles into Geometry Gold. A Gold manifest
may reference the existing fixture and add only the case-level contract needed
for the compact runner/report.

### 2. Geometry locality cases

Sources:
- `tests/fixtures/geometry_locality/1000TOSHIUSDT_5m_window.json`
- `tests/fixtures/geometry_locality/1000XECUSDT_5m_window.json`

Both contain exact 200-bar 5m windows from the 2026-09-21 17:46 MSK Scanner
pass, with provenance stating that pivots were verified against the saved
Scanner reports.

Existing contracts:
- 1000TOSHIUSDT: the old overlong 30..173 formation must not win; any admitted
  geometry must obey the locality span gate.
- 1000XECUSDT: no local formation exists, so Geometry must return none rather
  than fall back to an overlong structure.

These are READY negative/locality Gold controls.

### 3. Universal wedge-anchor case

Source:
`tests/fixtures/geometry_universal_anchor/bonk_0_198.json`

Contains the recovered original 199-candle 1000BONKUSDT window used by
`tests/test_geometry_universal_wedge_anchor.py`.

Stable contract:
- the old U81/L128 pair must never again be admitted/emitted as a wedge;
- the first anchor must terminate the preceding impulse;
- PONS from the formation-fit pack is already reused as the positive control.

This is READY and should be referenced, not copied.

### 4. L-shape freshness/staleness evidence

Source:
`tests/fixtures/l_shape_currency/CAKEUSDT_5m_window.json`

Contains 199 exact closed Bybit 5m candles through the 15:40 MSK decision
candle of the 2026-09-23 acceptance pass that emitted a roughly nine-hour-old
L-shape breakout.

This belongs to the broader geometry/pattern quality inventory, but it should
remain an L-shape-specific Gold/replay case rather than being mixed into the
Wedge/Triangle core runner.

## Existing synthetic controls — useful but not real Gold provenance

`tests/test_ikigai_box_detector.py` contains strong deterministic controls for
Ikigai Box semantics, including:
- harmless opposite-colour pause candles;
- confirmed internal counter-swing rejection;
- FLOCK-style wick/body first impulse behavior;
- mirrored LONG/SHORT behavior;
- terminal rejection wick;
- future-candle/as-of invariance;
- box freeze through break/re-entry.

These tests are valuable FAST controls. Several comments explicitly state that
the embedded OHLC is synthetic and not an archived Bybit feed. Therefore they
must not be presented as recovered owner-observed Geometry Gold cases.

## RECOVERABLE — owner-observed cases awaiting exact source-time OHLC

### G-BOX-1 — BSVUSDT 5m

Owner-observed false-positive Ikigai Box. The first impulse visibly contains a
real internal corrective swing/zigzag and should not qualify as one continuous
A→B impulse.

Required evidence before Gold admission:
- exact source-time BSVUSDT 5m candles;
- exact detector cutoff/decision candle;
- expected negative contract tied to the authoritative first-impulse rule.

A second owner screenshot, COREUSDT 5m, was identified as the same structural
class and should be treated as an additional example/control, not a separate
symbol-specific rule.

### G-BOX-2 / G-BOX-3 — post-breakdown secondary Box family

Representative owner-observed examples:
- CARVUSDT 5m
- CPUSDT 5m
- CROSSUSDT 5m
- CLOUSDT 5m

Visual family:
`compression/wedge/triangle -> downside sloping-boundary break -> later compact
secondary consolidation/Box`.

Required evidence before any case is declared positive:
- exact source-time OHLC and cutoff;
- proof that the later structure satisfies the existing Ikigai Box contract, or
  an explicit decision that a new subtype is required;
- negative controls distinguishing a genuine secondary Box from ordinary noisy
  continuation;
- proof that an earlier pattern signal does not suppress a later independent
  Box.

Do not weaken detector gates merely to force the screenshots to pass.

## EXACT_SOURCE_TIME — GEO-U1 Slice E recovery (2026-10-01)

Manifest: `tests/fixtures/geometry_gold/source_time_manifest_v1.json`
(separate from the pinned five-case `manifest_v1.json`). Fixtures:
`tests/fixtures/geometry_gold/source_time/`.

Method (same as the BONK READY precedent): each case starts from a durable
Scanner candidate in `runtime/terminal/robot_candidates/` that recorded
`scanner_source_candle_time_ms`. `analyzer.core` takes that time from the
newest `get_kline` row, i.e. the still-forming candle, whose decision-time OHLC
is not historically reproducible. The fixture is therefore the Scanner's exact
closed rows 0..198 (same indices as the recorded geometry), fetched from the
Bybit v5 public kline endpoint with an anchored start/end request. Every
fixture was validated for exact spacing, uniqueness, finite positive OHLC,
body-inside-range and the pinned cutoff, and all four recorded anchor prices
of each record equal the fetched high/low at the same index.

Recovered cases (cutoff = last closed candle open, UTC):

| case | cutoff UTC | production on fixture | SHADOW | terminal trend |
| --- | --- | --- | --- | --- |
| CASHCATUSDT 1m src1789850340000 | 2026-09-19T20:38Z | no geometry | SELECTED | NO_PERSISTENT_WIDTH_TREND |
| CASHCATUSDT 1m src1790590380000 | 2026-09-28T10:12Z | Falling Wedge (detected) | SELECTED | PERSISTENT_COMPRESSION |
| CASHCATUSDT 5m src1790002800000 | 2026-09-21T14:55Z | No wedge | SELECTED | NO_PERSISTENT_WIDTH_TREND |
| CASHCATUSDT 5m src1790272200000 | 2026-09-24T17:45Z | No wedge | SELECTED | EXPANSION |
| CASHCATUSDT 5m src1790665800000 | 2026-09-29T07:05Z | Rising Wedge (detected) | SELECTED | NO_PERSISTENT_WIDTH_TREND |
| ENAUSDT 1m src1789759320000 | 2026-09-18T19:21Z | no geometry | NO_ADMISSIBLE_PAIR | PERSISTENT_COMPRESSION (top-ranked, rejected) |
| ENAUSDT 1m src1789850520000 | 2026-09-19T20:41Z | Rising Wedge (detected) | SELECTED | NO_PERSISTENT_WIDTH_TREND |
| ENAUSDT 5m src1790098200000 | 2026-09-22T17:25Z | no geometry | SELECTED | NO_PERSISTENT_WIDTH_TREND |

Production values are observed from each fixture on current main; the recorded
runtime geometry (which included the forming candle and older code) is kept as
a separate fact and is not asserted equal. None of these cases is proven to be
the owner's 2026-09-30 screenshot.

UNRECOVERABLE_EXACT_CUTOFF (no fixture created):
- CASHCATUSDT 1m owner Scanner-vs-TradingView comparison (2026-09-30);
- ENAUSDT 1m owner broadening re-markup (2026-09-30);
- four earlier CASHCAT/ENA 1m candidate records (2026-09-12..14) without
  `scanner_source_candle_time_ms`.
Laptop Scanner artifacts end 2026-09-29 and contain no source-time record for
either owner screenshot; visual candle timing was not used.

Calibration readiness (`geometry/consensus_evidence_readiness.py`, fixed rule):
13 exact cases, provenance complete for all, NOT READY — selected
PERSISTENT_COMPRESSION 1 (need 3) and EXPANSION 1 (need 2).

## EXACT_SOURCE_TIME continuation — GEO-U1 Slice F (2026-10-01)

Manifest: `tests/fixtures/geometry_gold/source_time_manifest_v2.json`
(continues v1; v1 and its eight fixtures stay byte-identical). Same Slice E
method: Scanner closed rows 0..198, forming source candle excluded, Bybit v5
public kline, all four recorded anchor prices cross-checked.

Bounded inventory of `runtime/terminal/robot_candidates/`: 1889 records,
1378 with `scanner_source_candle_time_ms` (8 already in Gold), 1370 closed
prefixes fetched and validated with 0 provenance failures. An OHLC-only
realized-range proxy (prioritization only, never a fact) ordered 399 windows;
the cheapest exact pair counts were evaluated with the unchanged Slice D
report until the readiness gaps closed (27 evaluations, all logged in the
manifest `screening_log`).

Admitted (all three: production finds no geometry on the closed prefix;
recorded runtime pattern kept as a separate fact):

| case | cutoff UTC | pairs | SHADOW | terminal trend |
| --- | --- | --- | --- | --- |
| BILLUSDT 1m src1789759080000 | 2026-09-18T19:17Z | 90 | SELECTED | PERSISTENT_COMPRESSION |
| GOATUSDT 1m src1789850640000 | 2026-09-19T20:43Z | 30 | SELECTED | PERSISTENT_COMPRESSION |
| MCDUSDT 5m src1790004300000 | 2026-09-21T15:20Z | 54 | SELECTED | EXPANSION |

Reproducibility: these three and the two Slice E qualifying cases
(CASHCATUSDT 1m 2026-09-28 compression, CASHCATUSDT 5m 2026-09-24 expansion)
produced identical canonical report JSON in separate processes, one with
appended future rows; hashes are recorded in the manifest.

Readiness (fixed rule + opt-in reproducibility condition): 16 exact cases,
provenance 16/16, selected compression 3, expansion 2, no-trend 9,
no-admissible 2, production detected 4 -> READY. Calibration is NOT started
by this slice.

Performance observation: exact pair counts reach 11438 (fetched windows);
the slowest evaluated case is CASHCATUSDT 1m 2026-09-28 (11232 pairs, ~6 min
per run); a full expanded recompute is ~1 h. Follow-up GEO-U1-PERF: exact
pair-ranking acceleration preserving canonical results (not in this slice).

## Calibration population — GEO-U1 Slice G0 (2026-10-01)

Policy `GEO-U1-POP-1` (`geometry/consensus_calibration_population.py`):
target = Bybit USDT linear perpetuals on crypto underlyings. Instrument class
comes only from pinned public Bybit `instruments-info` metadata
(`tests/fixtures/geometry_gold/instrument_metadata_v1.json`):
symbolType "" / "innovation" -> CRYPTO_LINEAR_PERPETUAL (eligible);
"stock" / "ETF" -> EQUITY_LINKED_LINEAR and "commodity" / "forex" ->
OTHER_LINEAR (separate populations, kept but not eligible); anything
unproven -> UNKNOWN (fails closed). Never decided from ticker appearance or
trend.

Of the 16 exact cases only MCDUSDT 5m is not crypto (symbolType "stock",
McDonalds Corp, underlying MCD). PONS/AEVO fixture names were resolved to
PONSUSDT/AEVOUSDT by exact OHLC match (199/200 bars; last bar was forming).

Readiness: ALL_LINEAR (historical Slice F) 16 cases READY; TARGET_POPULATION
15 cases NOT READY - expansion 1 of 2 (removing MCD drops the expansion count
from 2 to 1). Note: the Scanner universe filter has no symbolType rule; the
2026-10-01 snapshot is 782 symbols = 394 "" + 128 innovation + 199 stock +
54 ETF + 4 commodity + 3 forex.

## Crypto EXPANSION closure — GEO-U1 Slice G1 (2026-10-01)

Manifest `tests/fixtures/geometry_gold/source_time_manifest_v3.json`
(continues v1/v2, both unchanged) and additive metadata
`instrument_metadata_v2.json` (v1 unchanged). Search queue: Slice F
EXPAND-proxy windows not yet evaluated whose pinned Bybit class is
CRYPTO_LINEAR_PERPETUAL (149), cheapest exact pair count first. Positions
1-4 were rejected (TRUTH/METIS/MAGIC no admissible pair; SKYAI1 selected
without trend); position 5 was accepted:

ENSUSDT 1m src1789759320000 (symbolType "" - Ethereum Name Service),
closed cutoff 2026-09-18T19:21Z, 199 bars 16:03..19:21Z, 120 SHADOW pairs,
SELECTED / EXPANSION (terminal ratio 1.125), production finds no geometry on
the closed prefix (recorded runtime: Rising Wedge). Three separate runs (one
with appended future rows) gave canonical report sha256
c26fc68acb127f7fd243ef807ab065ffd700e591a781ba154b973acb13b23c0c.

Readiness: TARGET_POPULATION (crypto, policy GEO-U1-POP-1) 16 cases READY -
compression 3, expansion 2, no-trend 9, no-admissible 2, production detected
4; without ENSUSDT it is NOT READY (expansion 1 of 2). ALL_LINEAR 17 cases
READY. Calibration not started.

## SHADOW calibration — GEO-U1 Slice H0 (2026-10-01)

Diagnostic only: `geometry/consensus_calibration.py`, pinned record
`tests/fixtures/geometry_gold/calibration_result_v1.json`. Defaults, policy,
readiness constants, fixtures and production are unchanged;
`production_cutover_authorized = false`.

Method (fixed in the module before any run): gate-first, lexicographic, no
scalar score. Hard gates: the 3 compression and 2 expansion cases keep their
class, the 2 NO_ADMISSIBLE negative controls are never SELECTED, exact
future-row determinism for any proposable set, population = GEO-U1-POP-1,
one flat parameter mapping, no trend-class collapse. Preference: fewer lost
selections, fewer IDENTITY_TIE_BREAK selections, fewer changed cases, fewer
changed parameters. LOW/HIGH = -/+ 25% of each parameter's semantic magnitude
(ratio thresholds: of the distance from 1.0; integers -/+ 1).

Results (16 crypto cases):
- Baseline (`DEFAULT_SHADOW_REPORT_PARAMETERS`) matches the pinned v3 facts
  exactly for all 16 cases.
- One-at-a-time: MATERIAL (evidence class changes) = minimum_side_touch_clusters,
  min_shared_support_coverage, terminal_window_bars, terminal_segments,
  compression_max_ratio, expansion_min_ratio (6 = maximum allowed);
  IDENTITY_ONLY = inlier_band_atr, max_support_gap_fraction; the other 9 are
  insensitive within their LOW/HIGH.
- Grid 3^6 = 729, 162 invalid window/segment combinations, 567 tested:
  50 pass every gate, 517 rejected (compression lost 399, expansion lost
  399, trend-class collapse 144; a negative control was never admitted).
  Every gate-passing set keeps 1 identity-tie-break selection (baseline: 1,
  CASHCATUSDT 5m src1790002800000); their only class changes are NO_TREND ->
  EXPANSION on 1000TOSHIUSDT / CASHCATUSDT 1m src1789850340000 /
  CASHCATUSDT 5m src1790665800000.
- Leave-one-out: 50/50 ROBUST, none preferred over baseline in any fold.
- Concentration: 1m 7 / 5m 9; CASHCAT 5/16, ENA 3/16; innovation 6 /
  ordinary 10; DATA_CONCENTRATION_BLOCKER — all 3 compression cases are 1m.

Conclusion: KEEP_BASELINE (no candidate preset). Any later threshold change
needs more evidence, first a 5m PERSISTENT_COMPRESSION case.

Performance: 602 parameter sets, 9632 exact case-runs (exact per-case memo of
boundaries/pairs/terminal evidence; unchanged selection code), cold run 3763 s
wall on 16 processes, 21502 s summed case time; slowest case
CASHCATUSDT 1m src1790590380000 (3753 s over all sets). GEO-U1-PERF remains warranted.

## 5m crypto compression recovery — GEO-U1 Slice H1 (2026-10-01)

Manifest `tests/fixtures/geometry_gold/source_time_manifest_v4.json` (continues
v1-v3, all unchanged) and additive metadata `instrument_metadata_v3.json`
(v1/v2 unchanged). Purpose: clear the H0 DATA_CONCENTRATION_BLOCKER (all
compression cases were 1m). Thresholds, H0 result, production and policy
unchanged; Scanner/Robot not launched.

Search: 1420 distinct Scanner records with `scanner_source_candle_time_ms`;
957 are 5m CRYPTO_LINEAR_PERPETUAL (pinned Bybit class) not yet in Gold or
previously evaluated; all 957 closed 199-bar prefixes fetched exact. A
necessary-condition filter (the realized-range half of the unchanged
PERSISTENT_COMPRESSION rule) leaves 149; ordered by exact pair count, the
first exact evaluation qualified, so the search stopped at position 1.

NXPCUSDT 5m src1789996800000 (symbolType "" - NEXPACE), closed cutoff
2026-09-21T13:15Z, 199 bars 2026-09-20T20:45Z..2026-09-21T13:15Z, 90 SHADOW
pairs / 2 admissible, SELECTED / PERSISTENT_COMPRESSION (terminal ratio 0.657,
realized 0.760; deciding component IDENTITY_TIE_BREAK between the two
admissible pairs). Production finds no geometry on the closed prefix
(recorded runtime: Rising Wedge). Three separate runs (one with future rows):
sha256 5475ad7d134259ba1e684dababb33cacb4b33bc08ed0444160da2f2d03f7609e.

After add (TARGET_POPULATION, 17 crypto cases): compression 4 (1m 3, 5m 1),
expansion 2, no-trend 9, no-admissible 2, production detected 4 -> READY.
H0 concentration rule: no trigger -> DATA_CONCENTRATION_BLOCKER cleared.
The H0 sweep was not rerun.

## Exact SHADOW performance — GEO-U1-PERF (2026-10-01)

Measured hotspot (base 3b9ea49, defaults, fresh process per case): pair
construction 60-76 s and terminal evidence 28-33 s of ~105-128 s on the
heavy cases (10-11k pairs); boundaries < 1 s; production engine ~13-17 s.
Root cause: per-bar pandas `Series.iloc` scalar/slice access inside
`_segment_evidence` and `terminal_compression_evidence` (millions of calls)
plus ~6M recomputations of the same `slope*index+intercept`.

Change (SHADOW only; production `engine.py`/`envelope_metrics.py` untouched):
the validated float64 high/low/close columns are read once as plain-float lists
(`Series.tolist()` equals `float(Series.iloc[i])` bit for bit) and each
boundary's line values are computed once per pair-build call with the same
expression. Ordering, tie-breaks, gates and every output are unchanged; no
cache outlives a call and no module-level state was added.

Parity (`tests/test_geometry_perf_parity.py`, `perf_parity_v1.json`): 17/17
default canonical report sha256 identical to base; the 7 pinned
reproducibility hashes identical plain and with future rows; representative
H0 matrix (25 sets: BASELINE, LOW/HIGH of the 6 material parameters,
boundary/pair-path parameters, 3 gate-passing, 3 rejected, most tie-breaks)
x 16 cases = 400 runs identical to the pinned H0 outcomes (the pinned H0
matrix is the BEFORE reference; it was not recomputed on the slow base).
The full before-matrix benchmark was aborted by the owner-authorized bounded
perf plan.

Bounded benchmark (same machine, Python 3.12.10, sequential fresh processes,
base then optimized, no caches): CASHCATUSDT 1m src1790590380000 127.7 ->
17.8 s; CASHCATUSDT 5m src1790665800000 104.1 -> 18.2 s; CASHCATUSDT 5m
src1790272200000 28.0 -> 4.8 s; NXPCUSDT 5m 2.0 -> 0.9 s; total 261.8 ->
41.7 s = 6.28x. Peak working set unchanged (123/118/79/67 MB). The remaining
time is mostly the unchanged production engine (~13-14 s on heavy cases),
which the calibration path does not run.

## SHADOW calibration rerun — GEO-U1 Slice H2 (2026-10-01)

Additive record `tests/fixtures/geometry_gold/calibration_result_v2.json`
(supersedes v1 for the current calibration state; v1 stays the historical
16-case H0 record). Population GEO-U1-POP-1 over manifests v1-v4 + metadata
v1-v3 = 17 crypto cases. Methodology unchanged: the H0 functions in
`geometry/consensus_calibration.py` are called unmodified (its 16-case
`load_target_population` is left as is; the 17-case loader/generator lives in
`tests/test_geometry_calibration_v2.py`). Exact path: merged GEO-U1-PERF.

- Baseline: 17/17 exact vs pinned v4 facts; unmemoized future-row check
  identical for all 17. Compression 4 (1m 3: BILL/CASHCAT/GOAT, 5m 1: NXPC),
  expansion 2, no-trend 9, no-admissible 2, production detected 4;
  identity-tie-break selections: CASHCAT 5m src1790002800000 and NXPC.
- Concentration (H0 rule): 1m 7 / 5m 10, CASHCAT 5/17, ENA 3/17,
  innovation 6 / ordinary 11; no trigger -> blocker NO.
- Sensitivity vs H0 v1: the 6 H0 MATERIAL parameters stay MATERIAL;
  `min_alternating_touches` INSENSITIVE -> MATERIAL (HIGH = 4 turns NXPC,
  alternation 3, into NO_ADMISSIBLE). NXPC is also hit by
  minimum_side_touch_clusters HIGH, terminal_window_bars LOW and
  terminal_segments HIGH (class lost), and by min_shared_support_coverage LOW
  (pair identity only). No LOW/HIGH admits a negative control.
- 7 MATERIAL > 6 -> CALIBRATION_UNDERDETERMINED (H0 active rule, unchanged):
  no grid sweep, no leave-one-out / NXPC-removal fold to evaluate;
  recommended_action MORE_EVIDENCE_REQUIRED, no candidate preset.

Runtime (16 processes, cold exact cache, PERF path): baseline 7.0 s +
future-row check 39.5 s, sensitivity 76.5 s, total 123 s; 595 exact
case-runs (35 sets x 17); slowest single run 6.2 s (CASHCAT 1m
src1790590380000). H0 v1 logged 1391 s for baseline + 35-set sensitivity on
16 cases (pre-PERF, 16 processes) - indicative only, not a controlled benchmark.

## min_alternating_touches evidence — GEO-U1 Slice H3 (2026-10-02)

Manifest `tests/fixtures/geometry_gold/source_time_manifest_v5.json` (continues
v1-v4, all unchanged) and additive metadata `instrument_metadata_v4.json`.
Evidence recovery only: no calibration rerun, no preset, cap and defaults
unchanged.

Universe (fixed before the screen): Scanner `robot_candidates` records with a
source candle time, pinned Bybit class CRYPTO_LINEAR_PERPETUAL, 1m or 5m, not
already in Gold or previously exact-evaluated = 1209 records / 467 symbols
(1m 253, 5m 956). All 1209 closed 199-bar prefixes fetched exact (0 failures;
recorded anchor prices match); all 1209 run under the unchanged defaults on
the PERF path in 121 s - the universe is exhausted. 1061 SELECTED (selected
pair alternation: 3 = 50, 4 = 425, >=5 = 586), 148 NO_ADMISSIBLE (none rejected
for alternation: body integrity / shared support only).

Acceptance rule (fixed): per stratum (alternation 3 / 4 / 5+ x 1m / 5m),
symbol not in Gold and not CASHCAT/ENA, ordered by trend class (compression,
expansion, no-trend), exact pair count, case_id; distinct symbols. Accepted
(all SELECTED / PERSISTENT_COMPRESSION, production detects none):

| case | alt | traversals | up/low clusters | shared cov | pairs/adm | ratio / realized | tie |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LDOUSDT 1m src1789759560000 | 3 | 2 | 2/2 | 0.343 | 90/1 | 0.812 / 0.593 | admissible (only one) |
| BNTUSDT 5m src1789994700000 | 3 | 2 | 2/2 | 0.288 | 375/2 | 0.709 / 0.362 | IDENTITY_TIE_BREAK |
| PUFFERUSDT 1m src1789760580000 | 4 | 3 | 2/2 | 0.444 | 150/4 | 0.621 / 0.733 | shared_support_coverage |
| GMXUSDT 5m src1789848900000 | 4 | 3 | 2/2 | 0.293 | 204/9 | 0.855 / 0.581 | negative_mean_residual_sum |
| FLOCKUSDT 1m src1789759380000 (innovation) | 5 | 4 | 3/2 | 0.389 | 207/3 | 0.761 / 0.680 | cross_boundary_traversals |
| GASUSDT 5m src1790098500000 | 5 | 4 | 3/3 | 0.253 | 216/9 | 0.752 / 0.789 | cross_boundary_traversals |

Each: three separate runs (one with future rows) identical; canonical hashes in
the manifest (`observed_h3_pair_facts`).

Diagnostic (min_alternating_touches LOW 2 / CURRENT 3 / HIGH 4 only): old 17 -
only NXPC changes (compression -> NO_ADMISSIBLE at HIGH). New 6 - the two
alternation-3 cases (BNT, LDO) change identically at HIGH; the four >= 4 cases
stay SELECTED/compression with the same pair. LOW changes nothing in either
population; no pair-only changes. Combined 23: exactly the 3 alternation-3
cases (NXPC, BNT, LDO) lose their class at HIGH. Label:
EVIDENCE_SUPPORTS_MATERIALITY (a structural boundary at alternation 3, not a
one-case artifact; the 6 new cases are all compression by the fixed preference
rule, so expansion / no-trend behaviour of alternation-3 pairs is not tested).

## Non-compression alternation-3 evidence — GEO-U1 Slice H4-A (2026-10-02)

Manifest `tests/fixtures/geometry_gold/source_time_manifest_v6.json` (continues
v1-v5, all unchanged) and additive metadata `instrument_metadata_v5.json`.
Evidence only: no sweep, no calibration rerun, cap and defaults unchanged.

Subset (reconstructed from the pinned H3 screen `source_time_manifest_v5.json`
`search.screened_all_rows`; nothing recomputed): 50 SELECTED alternation-3
cases in the 1209-record universe = NO_PERSISTENT_WIDTH_TREND 25 (1m 9, 5m 16),
EXPANSION 18 (1m 6, 5m 12), PERSISTENT_COMPRESSION 7 (1m 3, 5m 4; BNT and LDO
already accepted in H3); 47 distinct symbols. No class exhaustion.

Fixed rule: per class x timeframe, symbol not in Gold and not CASHCAT/ENA,
lowest exact pair count then case_id, distinct symbols. Accepted (all SELECTED,
alternation 3, 2 traversals, 2/2 clusters, production detects none):

| case | class | shared cov | pairs/adm | ratio / realized | tie |
| --- | --- | --- | --- | --- | --- |
| GRTUSDT 1m src1789759440000 | EXPANSION | 0.273 | 36/1 | 1.162 / 0.500 | admissible (only one) |
| DEXEUSDT 5m src1789848300000 | EXPANSION | 0.268 | 114/5 | 1.104 / 0.944 | terminal_width_trend_persistent |
| 1000TAGUSDT 1m src1789850040000 (innovation) | NO_PERSISTENT_WIDTH_TREND | 0.263 | 9/1 | 1.014 / 0.990 | admissible (only one) |
| OGNUSDT 5m src1789996800000 | NO_PERSISTENT_WIDTH_TREND | 0.288 | 90/3 | 1.007 / 0.597 | IDENTITY_TIE_BREAK |

Each: three separate runs (one with future rows) identical; hashes in
`observed_h4a_pair_facts`.

Diagnostic (min_alternating_touches LOW 2 / CURRENT 3 / HIGH 4 only): all four
become NO_ADMISSIBLE at HIGH (admissible_count 0); LOW changes nothing; no
pair-only changes. A: HIGH removes the alternation-3 expansion cases (GRT,
DEXE). B: HIGH removes the alternation-3 no-trend cases (1000TAG, OGN). C: LOW
changes nothing. D: no pair-only changes. Combined 27 (old 17 + H3 six + these
four): the 7 alternation-3 cases (compression NXPC/BNT/LDO, expansion GRT/DEXE,
no-trend 1000TAG/OGN) all fail at HIGH; every case with alternation >= 4
stays selected with the same pair. Label CROSS_CLASS_MATERIALITY_SUPPORTED; no
calibration action is inferred here.

## Structural calibration policy — GEO-U1 Slice H4-B (2026-10-02)

Owner semantic decision: freeze `min_alternating_touches` at its existing
default **3** as a structural invariant. Three alternating contacts form the
minimum repeated two-boundary sequence (`U-L-U` or `L-U-L`); two show only one
transition, while four require additional recurrence and reduce recall.

`geometry/consensus_calibration.py` records this in
`FROZEN_STRUCTURAL_PARAMETERS` and excludes the parameter from future
LOW/CURRENT/HIGH sensitivity, MATERIAL/INSENSITIVE classification, active
dimensions, grids and candidate preset optimization. Generated calibration
sets keep its value at 3; the SHADOW geometry function still accepts explicit
2/4 overrides for diagnostics. The active cap stays 6. Result metadata
exposes the frozen value/category/reason, rather than silently omitting it.

The H0 `calibration_result_v1.json` and H2 `calibration_result_v2.json` remain
historical, byte-unchanged records. Their earlier H2 MATERIAL finding is not
retroactively rewritten. The H3/H4-A evidence, GEO-U1-POP-1, manifests,
metadata, Gold fixtures, defaults and production Geometry are unchanged.
H4-B does not run calibration v3, sweep or leave-one-out and nominates no
preset; production cutover remains unauthorized. H5 is the next separately
authorized calibration run on the expanded evidence population.

## SHADOW calibration v3 — GEO-U1 Slice H5 (2026-10-03)

`tests/fixtures/geometry_gold/calibration_result_v3.json` is the exact H5
result over GEO-U1-POP-1: historical 17 eligible cases plus H3 six and H4-A
four, for **27 distinct cases**. All saved decision-time fixtures pass their
integrity checks; 22 have an exact 199-closed-bar source-time prefix, and five
are historical READY Gold cases. The excluded forming candle is not included.
Baseline matches all 27 pinned facts and remains invariant to future rows.

Baseline classes: 10 SELECTED PERSISTENT_COMPRESSION, four SELECTED EXPANSION,
11 SELECTED NO_PERSISTENT_WIDTH_TREND, two NO_ADMISSIBLE_PAIR; four
production-detected cases. Timeframes: 12 at 1m, 15 at 5m. Symbol types:
eight innovation, 19 ordinary. The existing concentration rule has no trigger
(CASHCATUSDT 5/27).

H4-B freezes `min_alternating_touches=3` as STRUCTURAL_INVARIANT. Its value is
3 in every tested set and it is absent from the 16-dimension calibratable
sensitivity domain. Eight dimensions are MATERIAL:
`minimum_swing_width_fraction`, `minimum_side_touch_clusters`,
`min_shared_support_coverage`, `max_support_gap_fraction`,
`terminal_window_bars`, `terminal_segments`, `compression_max_ratio`, and
`expansion_min_ratio`. `inlier_band_atr` is IDENTITY_ONLY; the other seven
calibratable dimensions are INSENSITIVE. Relative to the historical H2 result,
`minimum_swing_width_fraction` changed INSENSITIVE→MATERIAL and
`max_support_gap_fraction` changed IDENTITY_ONLY→MATERIAL. Thus freezing the structural
dimension did **not** reduce active dimensions from seven to six.

The unchanged active cap is six. With eight active dimensions, the H0 hard
gate is `CALIBRATION_UNDERDETERMINED`: no grid was generated (0 valid/0 invalid
evaluated; 3^8 = 6561 theoretical uncapped combinations), no grid set passed
hard gates, no preset comparison or leave-one-out was performed. The 33
baseline/one-at-a-time sets produced 891 exact case-runs. Recommendation:
`MORE_EVIDENCE_REQUIRED`; `proposed_shadow_preset=null`; baseline retained;
`production_cutover_authorized=false`. This is a SHADOW evidence result, not
permission to change Geometry, Robot, Scanner, risk, or LIVE behavior. Historical
v1/v2 calibration records and Gold manifests/metadata are unchanged.

## Calibration policy reclassification — GEO-U1 Slice H16 (2026-10-04)

Docs/policy only. Based on the accepted H15 verdict
`RECLASSIFICATION_EVIDENCE_READY`.

**Reclassification wording (forward-looking calibration policy):**
`max_support_gap_fraction` is reclassified from an active MATERIAL dimension
to a *diagnostic-only structural proxy*. Structural liveness/staleness
semantics are owned by `DerivedEnvelopeLifecycle` (SHADOW, PR #382, open and
unmerged), not by a tunable gap threshold. The parameter is removed only from
the forward active calibration set; it is excluded from the forward
calibration policy active set and must not be swept or promoted back to active
by future calibration policy; executable calibration code is unchanged until a
separate authorized slice.

**Preserved facts.** H5 (`calibration_result_v3.json`) remains historically
true: under the old proxy regime eight dimensions were MATERIAL, including
`max_support_gap_fraction` (IDENTITY_ONLY in H2 -> MATERIAL in H5).
`calibration_result_v1/v2/v3` and historical sensitivity artifacts are not
edited. Production selection (`geometry/consensus_selection.py`) still uses the
legacy `max_support_gap_fraction` until a separate, explicitly authorized
cutover; its value and all defaults are unchanged.

**Forward count, 8 -> 7.** H5 MATERIAL set (8): `minimum_swing_width_fraction`,
`minimum_side_touch_clusters`, `min_shared_support_coverage`,
`max_support_gap_fraction`, `terminal_window_bars`, `terminal_segments`,
`compression_max_ratio`, `expansion_min_ratio`. Forward active set (7) = the
same without `max_support_gap_fraction`.

**Blocker unchanged.** `MAX_ACTIVE_PARAMETERS = 6`; 7 > 6 so the forward
state remains `CALIBRATION_UNDERDETERMINED: 7 > 6`. No grid, leave-one-out or
preset nomination is authorized; `production_cutover_authorized=false`.
No Scanner/Robot/LIVE behavior change.

## VISUAL_ONLY / training-reference library

`training/reference_patterns/` contains a substantial library of annotations
and images for Wedge, Triangle, L-shape, Ikigai Box, multi-timeframe confluence,
and outcome examples.

Examples include:
- MULTI/SPXUSDT false canonical, XAIUSDT positive falling wedge,
  ZEREBROUSDT suspect rising wedge;
- VELVETUSDT nested Ikigai Boxes;
- AEONUSDT Ikigai Box and post-pump falling wedge;
- DUSKUSDT triangle breakout;
- RONINUSDT falling-wedge-to-L-shape;
- CHIPUSDT multi-timeframe confluence;
- multiple manual/scanner comparison cases.

These remain reference/training material unless an exact candle window and
source-time cutoff is independently present or recovered. Annotation text or
PNG evidence alone is insufficient for deterministic Gold replay.

## Geometry Gold case schema

The compact Gold manifest should reference existing candle fixtures instead of
copying them where possible.

Minimum case record:

```json
{
  "schema_version": 1,
  "case_id": "stable-human-readable-id",
  "pattern_family": "WEDGE|TRIANGLE|IKIGAI_BOX|L_SHAPE",
  "symbol": "SYMBOL",
  "timeframe": "5",
  "evidence_class": "READY",
  "fixture_ref": "relative/repository/path.json",
  "as_of_index": 199,
  "provenance": "owner/repository incident description",
  "expectation": {
    "kind": "POSITIVE|NEGATIVE|ANCHOR|INVARIANT",
    "contract": "machine-readable contract fields"
  }
}
```

Rules:
- `fixture_ref` may point at an existing fixture; no candle duplication;
- `as_of_index` or equivalent source-time cutoff is mandatory;
- expected anchors/identity are explicit when the case is anchor-sensitive;
- negative cases state the forbidden output, not a vague quality score;
- synthetic controls remain FAST tests and are labelled synthetic;
- screenshot-only references cannot be marked READY;
- no production detector threshold is changed as part of fixture admission.

## Minimal first Geometry Gold seed for RVL-G2

The smallest useful seed should reuse existing exact evidence:

1. PONS — positive wedge/anchor control from formation-fit pack;
2. 1000BONKUSDT — negative wrong-anchor wedge case;
3. 1000TOSHIUSDT — negative overlong/locality case;
4. 1000XECUSDT — negative no-local-formation case;
5. one formation-fit body-boundary negative (INJ or AEVO) referenced from the
   eleven-case pack.

Then add the first recovered real Ikigai Box owner defect, preferably BSVUSDT,
only after its exact candles/cutoff are frozen.

This seed gives positive + negative + anchor + locality coverage without
inventing new expected geometry or duplicating existing fixtures.

## G1 exit status

RVL-G1 inventory/schema is complete at the repository-evidence level:

- exact reusable OHLC sources identified;
- synthetic controls separated from real provenance;
- visual-only training material kept out of deterministic Gold;
- current owner-observed gaps classified as RECOVERABLE;
- compact manifest schema defined;
- minimal G2 seed identified.

Next Geometry task: RVL-G2 — create the compact manifest/runner references for
the existing READY cases, with no production detector changes.
