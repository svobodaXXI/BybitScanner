# MIRROR-INTEGRATION-5 — bounded trial of the OBSERVE_ONLY path on real public candles

**Status:** the input→decision→journal path works end to end on real public Bybit candles; **not ready to run beside a live
PAPER_AUTO** because of one measured cost (below). No Robot, Scanner, Telegram, backend, frontend, PAPER DB or LIVE change;
nothing was started. All 60 records are `OBSERVE_ONLY`, `executable=False`, `admission_allowed=False`.
Economics remain `NOT PROVEN`.

## What was run (2026-10-19 22:19–22:37 UTC, notebook, BelowNormal, 0.35 s between requests)

`tools/research_mirror_integration_5.py` drives the **existing** `MirrorSidecar` + `BybitClosedKlineSource` +
`ProtectionHealthGate` (no new detector). Candidates: the last 30 Wedge arrivals with envelopes
(2026-10-19 12:06–12:52 UTC) from a **read-only copy** of the PC PAPER DB and its candidate envelopes (468 available).
This is a *catch-up over real recent candles*, not a real-time observation: the candidates are ~10 h old at run time.

| Phase | Result |
|---|---|
| A. real gate, backend stopped | `backend_unreachable`, 3 cycles skipped, **0 candle requests, 0 candidates tracked, 0 records** — expected limit, fail-closed |
| B. idle gate injected (offline only), real candles | 23 candidates tracked (7 unusable: not 5m or no usable frozen geometry), 302 kline requests, 0 errors, median 281 ms, 2 cycles, source `unavailable=0 stale=0` |
| C. same, with an injected outage (first 4 requests + every 7th) | 461 requests, 12 failures absorbed, 27 cycles → **identical** observation set to B (60 = 60) |
| D. restart on B's journal | 60 lines before and after, **0 duplicate ids**, new lines only after the run ceiling |

**Observed events (B):** 31 `NAKED_BREAKOUT` (decision `WAIT`) on 19 symbols and 29 `RETEST_PROVEN` (decision `BLOCK`);
2 breakouts without a retest yet. Reasons: `policy_wait:robot_execution_not_authorized` (31),
`r0_wait:daily_gate_data_unavailable` (31, the DB copy is old), `campaign_not_active:RETEST_PROVEN` (29),
`observe_only` (60). Candle closes of the records: 12:20–20:30 UTC; run ceiling (exchange time) 22:23:50 UTC.

## Independent checks on the raw responses

| Check | Result |
|---|---|
| Continuity of closed 5m (2722 candles, creation→cursor) | **0 gaps** |
| Freshness | 0 stale candidates (every cursor within 2 candles of the exchange time) |
| Look-ahead (candle delivered at exchange time ≥ its close, all 2722 candles + 60 records) | **0 violations** |
| Every `RETEST_PROVEN` has a physical 1m contact with the line inside its 5m candle | **29/29**, 0 without contact |
| Every `NAKED_BREAKOUT` re-derived from a *fresh, separate* request with the owner rule (UP: `open < line(t_open)` and `close > line(t_close)`, DOWN mirrored) | **31/31 confirmed** (`verify_breakouts.json`) |
| Only public endpoint used; PAPER DB file unchanged | `https://api.bybit.com/v5/market/kline` only; size/mtime identical |

**Correction recorded:** `summary_run1.json` lists 31 `strict_body_mismatch` entries. That field came from a defect in my
first version of the check (it tested "body entirely beyond the line" instead of the owner rule "body crosses the line").
The detector was right; the check was fixed (`owner_rule_breakout`, unit-tested) and the 31 breakouts were re-verified
independently as above. The run file is kept unedited as evidence.

## Blocker found: per-cycle DB cost

On the 73 MB PAPER DB copy, without tracemalloc: `read_account_facts` ≈ **5–7 s CPU (10–18 s wall)** per call and
`read_new_wedge_arrivals(after=0)` ≈ **2 s CPU**, **every cycle** (idle cycle 2 of phase B cost 6.3 s CPU with no new data).
Notebook CPU; the PC is probably faster, but the cost scales with DB size and would compete with a running PAPER_AUTO
(the reason the PC trial was stopped earlier). The total process CPU of this trial (257 s) is inflated by tracemalloc and
by 27 phase-C cycles; the two measurements above are the clean ones. Peak traced memory 50 MB.

## Limits

- Backend stopped → the real protection gate could only be shown fail-closed; the healthy/pending path remains unit-tested only.
- Candidates are the PC's, up to ~10 h old; no real-time latency (candle close → record) was measured.
- Account facts came from an old DB copy (hence `daily_gate_data_unavailable`); R0 sizing was not exercised.
- 7 of 30 candidates were unusable by design (not 5m / no 1m-grid geometry).
- The idle gate in B–D is an offline-trial injection (no backend ⇒ no protection work exists); it must never be used with a running backend.

## Remaining blockers before a real OBSERVE_ONLY runtime acceptance

1. **Cost per cycle:** read account facts and arrivals incrementally or at a coarse interval (e.g. every few minutes), not every cycle; re-measure CPU without tracemalloc.
2. **A runner:** `MirrorSidecar` still has no entry point/launcher; owner decision on the process and its restart.
3. A short real-time dry run with the PAPER runtime up (or Autopilot `OFF`), to exercise the healthy protection gate and measure close→record latency.

Readiness for a separate runtime acceptance: **input side ready and verified on real candles; blocked by (1) and (2).**
