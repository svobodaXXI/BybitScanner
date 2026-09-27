# Development Validation Loop Optimization Plan

Status: **OWNER-APPROVED PROCESS DIRECTION — 2026-09-27**

Purpose: shorten the path from a real defect to a verified fix, reduce repeated
manual/runtime acceptance cycles, and make every discovered failure reusable as
future regression evidence.

This plan does **not** relax any existing Scanner visual acceptance, PAPER/LIVE
safety, Robot ownership, protection, fail-closed, or owner-manual runtime rules.

## 1. Core operating model

BybitScanner development is split into two developer validation labs:

### Geometry Lab

Use deterministic saved OHLC fixtures to develop Wedge/Triangle/anchor logic.

Each accepted fixture should contain:
- source-time candles used by the detector;
- pattern family / direction;
- expected formation identity;
- expected anchor/pivot locations or explicit acceptable ranges;
- negative cases where no formation should be admitted;
- provenance to the real owner-observed case.

Target location:
`tests/fixtures/geometry_gold/`

The Geometry Lab is a developer regression surface only. It does **not** replace
the owner's mandatory one complete real Scanner pass with ordinary Telegram
delivery across the eligible universe and all integrated patterns.

### Robot Runtime Lab

Use deterministic replay of real runtime incidents instead of repeatedly waiting
for the same failure on live Bybit market data.

Each replay fixture should preserve the minimum evidence needed to reproduce the
failure:
- ordered market-data events;
- symbol and lifecycle role;
- event identity / generation / sequence where relevant;
- runtime commands or state transition that preceded the incident;
- relevant timing/queue metadata;
- expected safety outcome and forbidden outcomes.

Target location:
`tests/fixtures/runtime_replays/`

The current 2026-09-27 protection ingress overflow is the first priority replay:
continuous multi-symbol `ENTRY_PENDING` order-book traffic must reproduce the
real saturation behavior without artificial drain barriers between small batches.

## 2. Incident-to-regression rule

For every repeatable real defect:

1. capture the smallest deterministic fixture that reproduces it;
2. prove RED on current code;
3. implement one bounded fix;
4. prove the exact fixture GREEN;
5. run the minimum relevant broader regression gate once;
6. only then spend owner time on real runtime / full Scanner acceptance.

Do not keep a production incident only as prose/log evidence when the relevant
inputs can reasonably be captured and replayed.

A discovered defect should therefore reduce future diagnostic cost rather than
requiring another manual rediscovery.

## 3. Validation tiers

Use four explicit cost tiers.

### FAST

Pure/unit/property tests. Seconds. Run for the changed behavior.

### REPLAY

Saved real geometry/runtime fixtures. Deterministic. Usually seconds to tens of
seconds. Required when the task fixes a previously observed real incident that
can be replayed.

### PAPER CI

Repository integration/contract checks for the affected Robot/PAPER boundaries.
Run once after the focused checks are green.

### OWNER ACCEPTANCE

Expensive real-world proof only after lower tiers pass.

Scanner visual acceptance remains exactly the existing owner rule:
one complete real eligible-universe Scanner pass, normal Telegram delivery, all
integrated patterns. No replay, local PNG, subset, or single-symbol fixture may
substitute for it.

Robot acceptance remains owner-manual real PAPER proof of the required lifecycle
after replay/CI pass.

## 4. Runtime replay requirements

Do not hide overload with test-only pacing that the real producer does not have.

For queue/ingress incidents:
- preserve continuous producer behavior;
- do not insert owner-drain barriers unless the production path has them;
- preserve per-event FIFO and distinct crossing evidence;
- do not increase queue capacity or coalesce safety evidence merely to make the
  replay pass;
- assert safety invariants as well as throughput outcome.

For the current ingress incident, the replay must distinguish:
- `ENTRY_PENDING` traffic;
- `EXPOSURE` / `OBLIGATION` traffic;
- owner processing rate;
- queue high-watermark / overflow;
- durable fail-closed latch.

## 5. Stateful/property testing

Use property/stateful testing selectively for lifecycle invariants, not as a
replacement for deterministic incident fixtures.

Priority Robot invariants:
- READY is impossible while protection is unhealthy;
- overflow closes admission/fences continuity;
- one symbol never acquires ambiguous Robot ownership;
- repeated reconcile/start/stop cannot duplicate an order or trade identity;
- lifecycle states cannot move backwards through illegal transitions;
- restart cannot silently discard durable ownership/protection evidence.

Priority Geometry invariants:
- historical anchors do not move merely because unrelated later candles are
  appended;
- anchors correspond to admissible pivots;
- forbidden body-boundary violations remain forbidden;
- identical OHLC input is deterministic;
- local geometry should not depend on irrelevant remote history beyond the
  explicitly allowed selection window.

## 6. Feature-freeze rule until the two primary quality gates are healthy

Current product focus is reduced to two bosses:

1. **Robot Stability** — current P0, including the unresolved protection ingress
   overflow.
2. **Geometry Quality** — Wedge/Triangle geometry and anchor fidelity.

Autopilot, secondary UX expansion, new pattern families, and architecture
improvements do not pre-empt these two unless the owner explicitly changes
priority.

Autopilot documentation/code already completed is preserved, not deleted; it is
simply non-blocking/deferred while Robot Stability and Geometry Quality are red.

## 7. Acceptance dashboard / compact report

Prefer one compact generated or textual report over repeated manual inspection.

The report should expose at least:
- Geometry Gold: PASS / FAIL / case count;
- Runtime Replays: PASS / FAIL / fixture count;
- focused PAPER CI: PASS / FAIL;
- owner acceptance: PENDING / PASS with the exact acceptance type.

A simple script/report is sufficient. Do not build a new service/dashboard
platform unless it demonstrably saves owner time.

## 8. Immediate application

### Current Robot P0

The 2026-09-27 runtime evidence is authoritative:
- #293 reduced reconcile from about 9.1 s to about 1.4 s;
- candle-cache owner misses remained zero;
- queue still reached 64/64;
- later `2ZUSDT` became unhealthy with `ingress_overflow`;
- covered symbols were all `ENTRY_PENDING`.

Before another speculative runtime patch, build the first continuous
multi-symbol `ENTRY_PENDING` replay that reproduces saturation without
artificial draining.

### Geometry

When Robot P0 is contained, establish the first compact golden set from known
good/bad Wedge/Triangle/anchor cases. Use it for implementation feedback; retain
the existing full Scanner acceptance as the only owner visual acceptance.

## 9. Definition of Done for this process improvement

The process improvement is considered implemented when:
- fixture directories and minimal harnesses exist;
- the current ingress failure is reproducible by replay;
- at least one real geometry defect is frozen in the geometry golden set;
- changed-behavior work uses FAST -> REPLAY -> PAPER CI -> OWNER ACCEPTANCE as
  applicable;
- project docs/quest state point to this plan;
- no existing safety/acceptance contract was weakened.
