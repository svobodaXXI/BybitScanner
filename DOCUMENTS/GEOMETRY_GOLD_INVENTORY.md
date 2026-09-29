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
