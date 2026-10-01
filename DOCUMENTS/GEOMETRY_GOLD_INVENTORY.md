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
