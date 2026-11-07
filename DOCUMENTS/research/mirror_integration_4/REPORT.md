# MIRROR-INTEGRATION-4 — live read-only inputs for the OBSERVE_ONLY sidecar

**Status:** implemented and fault-tested offline; **no shared file, Robot, Scanner, backend, frontend, runtime, PAPER DB or LIVE
change**. Economics remain `NOT PROVEN` (RETEST-5/6/7). Every sidecar record stays `OBSERVE_ONLY`, `executable=False`,
`admission_allowed=False`. Not ready to be started by any launcher yet: see "Readiness".

## What this slice adds (stacked on INTEGRATION-3, #559)

| Piece | File | Role |
|---|---|---|
| `BybitClosedKlineSource` | `mirror_retest_live_sources.py` | Closed 5m candles and 1m proof from public `GET /v5/market/kline` (no keys) through the existing `create_bybit_rest_session` (same proxy as the backend). |
| `ProtectionHealthGate` | `mirror_retest_live_sources.py` | Read-only `GET /api/robot/protection-health` → the sidecar's `protection_busy()`. |
| Sidecar changes | `mirror_retest_sidecar.py` (+21/−2) | Cursor starts at candidate creation (nothing earlier is read); protection is re-checked every `PROTECTION_RECHECK_EVERY = 10` candidates inside a cycle; missing 1m proof holds the cursor (`fine_unavailable`). |
| Fault injection | `tests/test_mirror_retest_fault_injection.py` (20 tests) | Added here; see below. |

## Properties checked

| Property | Mechanism | Evidence |
|---|---|---|
| Network errors on public candles | any exception / non-200 / `retCode≠0` / malformed row / duplicate / misaligned / inconsistent OHLC → `CandleSourceUnavailable` → `[]`, cursor held, `unavailable` counted; never raises into the sidecar | `test_network_failures_never_yield_candles`, `test_rate_limits_and_garbage_hold_the_cursor_and_never_raise` (HTTP 429, body 10006, garbage, `null`), `test_flapping_network_converges_to_the_fault_free_result_without_duplicates` (1 request in 3 fails → identical to the fault-free result, nothing skipped or repeated) |
| 1m proof fails permanently | cursor held; no `RETEST_UNPROVEN`, no `RETEST_PROVEN` from partial data | `test_a_permanently_failing_1m_request_blocks_the_retest_but_never_fakes_it`, `test_a_hole_in_the_1m_coverage_never_becomes_an_unproven_retest` |
| No look-ahead | only candles with `start+interval ≤ exchange time of the response`; exchange/local clock disagreement > 1 interval → unavailable; feed lag → stale → nothing | `test_candles_after_exchange_time_are_never_consumed_even_when_the_server_leaks_them` (server ignores `end`), `test_observations_at_time_t_do_not_depend_on_data_after_t` (identical output with and without future rows), `test_a_local_clock_far_ahead_of_the_exchange_…` |
| Closed 5m/1m continuity | a missing 5m candle is passed through and becomes one `DATA_GAP WAIT`; the cursor holds until the exchange serves it; 1m coverage of a 5m candle must be exactly 5 consecutive minutes | `test_a_missing_5m_candle_in_the_wire_data_is_a_gap_…`, existing `test_fine_candles_must_cover_the_whole_closed_5m_candle` |
| Fail-closed protection | busy unless `ok` ∧ `healthy is True` ∧ `unhealthy_symbols == {}` ∧ `ingress.current_pending == 0` (int); timeout / HTTP≠200 / bad JSON / any exception → busy; busy at the start → no read at all; busy mid-cycle → stop at the next re-check | `test_protection_health_errors_mean_busy` (4 error types), `test_protection_with_pending_ingress_or_unknown_fields_has_priority`, `test_protection_turning_busy_mid_cycle_stops_processing_at_once` |
| No influence on Robot / execution | live module: GET only, no trading endpoint, no signing, no store/owner access, no top-level `terminal.*` import; the sidecar cycle under fault leaves the SQLite file byte-identical | `test_live_adapters_are_read_only_and_import_no_trading_modules`, `test_sidecar_cycle_under_fault_leaves_the_database_untouched`, existing `test_sidecar_has_no_trading_or_owner_path` |
| Bounded load | ≤ `MAX_PAGES_PER_CALL = 3` requests and ≤ 3000 candles per call; 10 s HTTP timeout; no threads or sleeps in tests | `test_source_requests_per_call_are_bounded` |

**Sensitivity check:** removing the "still forming at exchange time" guard makes 3 tests fail
(`…never_consumed_even_when_the_server_leaks_them` and two existing live-source tests); the file was restored afterwards.

**Result:** 258 tests pass across the MIRROR/retest suite (12 files; 20 of them new here, 64 more in the earlier part of this slice), 28 s,
run at BelowNormal priority on the notebook. One finding of the work, not a defect: a deterministic pattern in which *every*
1m request fails blocks the retest indefinitely (fail-closed by design); a flaky 1-in-3 failure converges exactly.

## Limits (not shown by these tests)

- **Not run against the real network or a running backend.** The public kline endpoint, the proxy path and the real
  `/api/robot/protection-health` response were exercised only through simulations of their wire format. The long
  fault-injection trial on a DB copy planned on the PC was not repeated (CPU protection of the live PAPER_AUTO).
- **No runner.** `MirrorSidecar` has no entry point, thread or launcher; nothing in the repository starts it. A separate
  decision is needed for how/where it runs (own process vs backend thread) and who restarts it.
- `_default_session()` lazily imports `terminal.runtime.paper_http_server` (the whole backend module, no instance) to reuse
  `create_bybit_rest_session`. Harmless to state, but it makes the sidecar process heavy; a small shared factory would be a
  change to a shared file and was deliberately not made.
- Memory/CPU of a long-running sidecar are unmeasured; the bounds above are structural, not profiled.
- Gate semantics rely on the current `protection-health` fields (`healthy`, `unhealthy_symbols`, `ingress.current_pending`);
  a change to that payload turns the sidecar off (busy) rather than wrong.

## Overlap with open PRs

Only the stacked MIRROR PRs (#547, #548, #552, #557, #559) share files with this branch, because it is stacked on them.
No terminal/Autopilot-UI PR touches any file of this slice; no shared Robot/Scanner/backend/frontend file is changed.
Base of the Draft PR is `research/mirror-integration-3`, following the stack convention.

## Readiness for an OBSERVE_ONLY runtime acceptance

**Not yet.** Missing, in order: (1) an owner decision and a minimal launcher for the sidecar process; (2) a bounded
dry run against the live public endpoint and the running backend with the PAPER runtime stopped or at least with
Autopilot `OFF`; (3) CPU/memory sampling in that run. The input side (closed candles, protection gate, look-ahead,
continuity, fail-closed) is ready and covered.
