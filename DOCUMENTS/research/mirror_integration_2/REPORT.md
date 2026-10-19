# MIRROR-INTEGRATION-2 — OBSERVE_ONLY path and the shared contract it needs

**Status:** independent OBSERVE_ONLY pipeline implemented and verified on all 67 saved RETEST-4 cases;
**live wiring stopped at the shared-file boundary** (contract below). Economics remain `NOT PROVEN` (RETEST-6–8).
No Robot, Scanner, Telegram, admission, protection, API, Workspace, PAPER DB, PAPER_AUTO or LIVE change.

## Observable candidate path (implemented, `mirror_retest_observer.py`)

```text
Scanner->Robot Wedge candidate snapshot --boundaries_from_candidate_snapshot--> frozen upper/lower Boundary (as_of = created_at)
closed 5m candle --geometry.naked_retest (1m resolves ambiguous contact, tolerance 0)--> NAKED_BREAKOUT / RETEST_PROVEN / RETEST_UNPROVEN / DATA_GAP
available facts --retest_account_risk.freeze_r0 (#552) + retest_campaign budget--> R0 decision
research policy --mirror_retest_robot_bridge.observe_for_robot (#547)--> WAIT / DENY / (ALLOW reported as WAIT)
decision WAIT | BLOCK + reasons --ObservationJournal--> idempotent JSONL record (executable=False, admission_allowed=False, OBSERVE_ONLY)
```

- Never ALLOW: a research-policy ALLOW becomes `WAIT robot_execution_not_authorized`; the journal refuses any executable record.
- Fail-closed: no account facts → `WAIT r0_wait:daily_gate_unavailable`; unknown obligations → WAIT; latched or exhausted
  account → BLOCK; data gap → WAIT; terminal campaign → BLOCK with exit intent as data only.
- Tolerance 0 (physical contact): RETEST-5 found no ATR zone passing its train gate, so no new parameter.

## Verification on saved historical cases (`tools/research_mirror_integration_2.py`, cache-only)

67 boundaries, 131 observations (`observations.jsonl`, `summary.json` here):

| Event | Decision | n |
|---|---|---|
| NAKED_BREAKOUT | WAIT (`r0_wait:daily_gate_unavailable`, `policy_wait:robot_execution_not_authorized`) | 67 |
| RETEST_PROVEN | BLOCK (`campaign_not_active`, exit intent `CLOSE_REMAINDER` as data) | 62 |
| RETEST_UNPROVEN | BLOCK (fail-closed, no exit intent) | 2 |
| still active at window end | — | 3 |

Final phase equals the published RETEST-5 refined outcome for **67/67** boundaries; executable / admission-allowed
observations: **0**. Tests: `tests/test_mirror_retest_observer.py` (14) with two real cases as fixtures
(`tests/fixtures/mirror_integration_2/`: 1000LUNCUSDT upper — proven, BRUSDT upper — unproven; Bybit public klines).

## Shared contract required for live observation (NOT implemented — agreement first)

| # | Need | Existing source | Proposed minimal read interface |
|---|---|---|---|
| 1 | Candidate snapshots (Wedge, `robot_geometry`, `scanner_geometry_cursor`, `created_at`) | `robot_candidates` via `SQLiteStore.get_robot_candidate` / `load_robot_candidates_by_status` | read-only accessor of new Wedge candidate snapshots since a cursor |
| 2 | Closed 5m (+1m) candles per observed symbol | closed-candle evidence prepared off the owner (`robot_catchup_evidence`, `paper_runtime.py`) | read of already prepared closed candles; no REST on the owner thread |
| 3 | Account facts for R0 | `daily_loss_gate` facts + obligations (see `mirror_retest_r0/CONTRACT.md`) | two read accessors from #552 |
| 4 | Durable observation sink + display | none (Autopilot audit `robot_auto_decisions` is not for MIRROR) | separate append-only sink; expose through the decisions read API proposed in #553 |
| 5 | Execution point | — | **off the owner hot path** (protection ingress overflow risk): a separate read-only observer reading 1–3, never in `observe_autopilot_candidate` |

Files the wiring would touch (untouched): `terminal/runtime/paper_runtime.py`, `terminal/persistence/sqlite_store.py`
(read accessor only), `terminal/application/robot_autopilot_shadow.py`, `terminal/application/robot_autopilot.py`,
`terminal/runtime/paper_http_server.py` (only if #553 agrees on a GET).

## Limits

- Offline replay has no account facts, so the live R0 branch is exercised only by unit tests with synthetic gate facts.
- Candidate-to-boundary transform requires 1m geometry; Box, L-shape and horizontal levels are not covered.
- `new_attempt_worst_case`, realized costs and remaining reward come from a real attempt plan; observation has none, so
  the research policy can never reach ALLOW here (by design).

## Next step

Agreement of contract rows 1–5 (owner/coordinator). Then a separate PR with read accessors only and a sidecar observer;
still OBSERVE_ONLY, no admission.
