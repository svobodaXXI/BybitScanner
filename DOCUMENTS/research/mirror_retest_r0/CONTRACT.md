# MIRROR RETEST R0 — account risk limit and the shared interface it needs

**Status:** independent calculation implemented and tested; **shared-file wiring NOT started** (needs agreement).
Economics of the strategy remain `NOT PROVEN`. Nothing here is Robot admission or a trading permission.

## Accepted formula (unchanged)

`R0 = min(account risk limit, 0.5 * net idea potential)` — `RETEST_BOX_CHAIN_IMPLEMENTATION_PLAN.md` §2a rule 11 / §5,
already implemented as `retest_campaign.freeze_campaign_r0`. No new account-risk percentage is introduced.

## What is the "account risk limit" in the existing Robot

Existing account-level gates (read, not changed):

| Gate | Where | Loss-denominated? |
|---|---|---|
| PAPER daily-loss gate: blocks at `block_pct` (−10) of the 00:00 MSK baseline equity, resumes above −7 | `terminal/application/robot_autopilot.py` (`daily_loss_gate_facts`, `DAILY_LOSS_BLOCK_PCT`), facts assembled in `robot_autopilot_shadow.py` | **yes (USDT headroom)** |
| 19 RO aggregate cap, `RO_USDT = 250` | `terminal/application/robot_portfolio.py` | no (notional slots) |
| per-asset 2 RO, correlation, cluster, direction | `robot_portfolio.DEFERRED` — not evaluated | — |
| symbol ownership, mandatory STOP/TAKE, continuity/protection health | Robot admission / protection | no |

The only loss-denominated account gate is the daily-loss gate, so:

```text
headroom = current_adjusted_equity - baseline_equity * (1 + block_pct / 100)      # distance to the existing block
limit    = headroom - sum(worst_case_loss_to_STOP of every open position and pending entry)
R0       = min(limit, 0.5 * net idea potential)
```

`block_pct` is read from the gate facts, not hard-coded. 19 RO / ownership / protection gates stay separate and mandatory;
this budget does not replace them (plan §5).

## Implemented (independent, pure) — `retest_account_risk.py`

- `daily_loss_headroom_usdt(daily_gate)`; `account_risk_limit(daily_gate, committed_worst_case_usdt)`;
  `freeze_r0(idea_potential_net_usdt, daily_gate, committed_worst_case_usdt)`;
  `position_worst_case_loss_usdt(direction, quantity, entry_price, stop_price, fee_rate)`.
- Fail-closed: disabled / unavailable / malformed gate, unknown or negative obligation, unknown potential → `WAIT`;
  latched gate, exhausted headroom or limit, non-positive potential → `DENY`; a position without a valid STOP has
  unknown worst case → `WAIT`. Unrealized PnL is already inside the gate's adjusted equity, so subtracting the full
  worst case is deliberately conservative.

## Shared interface still required (not implemented — owner/coordinator agreement first)

Read-only, owner-thread, same transaction as the admission check (plan §5: budget check atomic with ownership):

1. **`daily_loss_gate` facts on demand.** Today they exist only inside an Autopilot decision (`robot_autopilot_shadow.py`,
   `_daily_loss_gate` → `robot_autopilot.daily_loss_gate_facts`) and have no read accessor. Need one function returning the
   same mapping (`enabled`, `data_available`, `latched`, `baseline_equity_usdt`, `current_adjusted_equity_usdt`, `block_pct`).
2. **Account obligations list.** For every open position and pending entry: `direction`, `quantity`, `entry_price` (average
   entry; limit price for pending), and the protective `stop_price`; plus the documented PAPER per-side fee rate
   (`paper_runtime.py:1228`). Sources exist (`position_projections`, `protection_projections`, `paper_limit_orders`) but no
   single read function exposes them in this shape.
3. A MIRROR adapter must call (1) and (2) once per decision and pass the result unchanged; it must not cache across decisions.

Files that would be touched by the wiring (**not touched now**): `terminal/application/robot_autopilot_shadow.py`,
`terminal/application/robot_autopilot.py`, `terminal/application/robot_portfolio.py`, `terminal/runtime/paper_runtime.py`.

## Boundaries kept

No change to Robot, Scanner, admission, protection, API or Workspace; no PAPER_AUTO, backend, PAPER DB or LIVE access.

---

# Observation read API — MIRROR → AUTOPILOT Terminal (2026-10-20)

**Verdict: CONTRACT REQUIRED.** No existing route or structure can carry MIRROR observations. This section proposes the
minimum; **no backend, frontend or GFL/AUTOPILOT file is changed here and nothing is to be implemented before agreement.**

## Why the existing mechanisms are not enough

Inventory of every `GET` in `terminal/runtime/paper_http_server.py` (`do_GET`, stable `501b774`) against the need of
`AUTOPILOT_UI_MONITORING_READ_CONTRACT.md` (#553: candidates, ALLOW/WAIT/BLOCK decisions, reasons; read-only, bounded, account-scoped):

| Existing source | What it gives | Can it carry MIRROR events? |
|---|---|---|
| `GET /api/robot/autopilot` | mode, reason, version | no (state of the mode only) |
| `GET /api/health` | identity, `robot_admission_ready`, `paper_live_safe` | no |
| `GET /api/robot/protection-health` | health, unhealthy symbols, ingress counters, `autopilot_shadow_deferred` counters | no event list; counters only |
| `GET /api/open-positions`, `/api/paper-state` | positions and their protection | no (positions, not candidates/decisions) |
| `GET /api/diary/trades`, `/api/diary/statistics` | closed-trade evidence | no (history) |
| `GET /api/diary/setups` (`project_setup_store`) | D2 Trading-Diary setup instances/decision events | **rejected**: it is the owner's Trading Diary (statistics, outcomes). OBSERVE_ONLY research rows would mix hypotheses into those statistics, and feeding it needs a *write* path into a shared store (`DiaryDecisionStore.append_decision_event`) |
| `GET /api/workspace/state`, `/stream` | market-data diagnostics | no |
| `ObservationJournal` (JSONL, MIRROR) | the observations — **not exposed by any route** | this is the data; only the read route is missing |

The decisions Autopilot already audits (`robot_auto_decisions`) are also not exposed by any GET; UI-5 states the same
("a verified read schema … has not yet been established"). So MIRROR does not duplicate an API — there is none to reuse.

## Proposed contract (minimal, to be agreed)

**Endpoint:** a new `GET /api/robot/mirror-observations` next to `/api/robot/protection-health` (same namespace, same
off-owner style). Query: `after` (int, default 0) = `seq` of the last record seen; `limit` (int 1–200, default 100).

**Response `200`:**

```json
{
  "ok": true,
  "source": "MIRROR_RETEST_JOURNAL",
  "strategy_id": "MIRROR_RETEST",
  "mode": "OBSERVE_ONLY",
  "account_scope": "paper",
  "journal_present": true,
  "observations": [],
  "next_seq": 60,
  "truncated": false,
  "malformed_lines": 0,
  "observed_at_ms": 1792500000000
}
```

`observations` holds at most `limit` records in ascending `seq`.

**One observation** (verified on the 60 real records of the INTEGRATION-5 trial: every record maps, ~520 bytes each,
200 records ≈ 100 KiB):

| Field | Type | Source | Note |
|---|---|---|---|
| `seq` | int ≥ 1 | line number in the append-only journal | stable cursor; assigned by the projection, not stored |
| `observation_id` | string | `Observation.observation_id` | immutable decision id, idempotent (hash of boundary, event, candle close) |
| `candidate_ref` | string | prefix of `boundary_id` | **= Robot candidate id**; exact key, never a ticker match |
| `boundary_id`, `boundary_side` | string, `upper`\|`lower` | `boundary_id` | |
| `symbol` | string | `symbol` | |
| `timeframe` | `"5"` | constant for Wedge candidates | not in the journal today (see MIRROR-side changes) |
| `pattern` | string \| null | candidate envelope | not in the journal today; `null` = "no data source" |
| `event` | `NAKED_BREAKOUT`\|`RETEST_PROVEN`\|`RETEST_UNPROVEN`\|`DATA_GAP` | `event` | |
| `phase`, `campaign_direction` | string \| null | `phase`, `campaign_direction` | |
| `decision` | **`WAIT`\|`BLOCK` only** | `decision` | MIRROR never emits `ALLOW`; a consumer must show any other value as unavailable |
| `reasons` | string[] | `reasons` | machine reason codes (`r0_wait:…`, `policy_wait:…`, `campaign_not_active:…`, `observe_only`) |
| `candle_close_time_ms` | int | `candle_close_time_ms` | exchange time of the closed 5m candle that caused the event |
| `recorded_at_ms` | int \| null | wall clock at journaling | not in the journal today; freshness for the UI |
| `mode`, `executable`, `admission_allowed` | `"OBSERVE_ONLY"`, `false`, `false` | as stored | the route must refuse (`503`) any line that violates them |

Not exposed by default: `facts` (contains R0 account numbers); an optional `include_facts=1` may be added later.

**Absent / unreadable data:** journal file missing → `200`, `journal_present:false`, empty list (UI: "Нет источника данных");
unreadable or any other failure → `503 {"ok":false,"error":"mirror_observations_unavailable"}`; malformed lines are skipped
and counted in `malformed_lines`, never repaired. The UI must treat unknown/absent as unavailable, never as ALLOW or healthy.

## Authorization and read-only guarantees

- Served only by the existing backend bound to `127.0.0.1` (`HOST`). Same access model as the other Terminal GET routes
  (`/api/robot/protection-health`, `/api/robot/autopilot`): no token; **no new token, no new write route, no POST**.
- **Off the owner thread:** no `runtime.call`; like `protection-health` the handler reads a server attribute and a file,
  so PAPER_AUTO order handling is never queued behind it.
- **Read-only on the data:** opens the journal for reading only, never creates, repairs or truncates it; no SQLite, no PAPER DB.
- **Bounded:** `limit ≤ 200`, response ≤ ~100 KiB, reads at most a fixed window of the file (proposed 1 MiB from the cursor
  or from the end), O(window) per request; no polling is imposed on the UI.
- No exchange access, no credentials, no account balances in the response.

## Files and functions

Created or changed only when the contract is agreed:

| File | Change | Owner |
|---|---|---|
| `mirror_retest_projection.py` (new, pure) | `project_observations(path, *, after, limit) -> dict`; validates the invariants above; unit-testable without a server | MIRROR |
| `mirror_retest_observer.py` | `Observation` gains optional `candidate_ref`, `pattern`, `timeframe`, `account_id`, `recorded_at_ms` (defaults keep old journals valid) | MIRROR |
| `mirror_retest_sidecar.py` | fills the new fields from the tracked envelope and the wall clock | MIRROR |
| `terminal/runtime/paper_http_server.py` | one `GET` branch beside `/api/robot/protection-health` (~line 2786) calling the projection; one server attribute `mirror_observation_journal_path` next to `server.diary_setup_store_path` in the server factory (~line 4255) | **Robot/PAPER_AUTO owner (shared file)** |
| `tests/test_mirror_retest_projection.py`, a route test in the style of `terminal/diary/test_setup_http_route.py` | cursor, limit, malformed lines, missing file, invariants, no `runtime.call` | MIRROR |

## Compatibility

- **#553 / UI-5 (`AUTOPILOT_UI_MONITORING_READ_CONTRACT.md`):** satisfies its items 1–2 for MIRROR (candidate key, symbol,
  timeframe, pattern, decision id, time, `WAIT|BLOCK` + reason codes, "no data source" state), GET-only, bounded,
  account-scoped, off the owner thread. Items 3–4 (ingress, protection) stay with the existing `protection-health`. The route
  does not replace the Robot's own candidate/decision projection that UI-5 still asks the Robot owner for: MIRROR observations
  are a separate, labelled source (`source`, `strategy_id`, `mode`).
- **GFL-4 (#574) and GFL-1..3 (#567–#571): no conflict.** GFL-4 changes only `terminal/frontend` (`App.tsx`,
  `ChartPanel.tsx`, `ModePanelLegacy.tsx`); the GFL contract proposes *different* routes (`GET /api/scanner/signal-geometry`,
  `POST /api/geometry-feedback`; placeholders, not implemented). UI-1..12 (#546–#564) touch no `paper_http_server.py`.
  Only a textual overlap is possible later: if both the GFL routes and this one are approved, each adds a branch/attribute in
  `paper_http_server.py` — different blocks, merge-level coordination only.
- Identity: the key is `candidate_ref` (Robot candidate id). If GFL's `signal_id` is later defined as the same value it can
  be added as an alias field; this was not verified and is not assumed.

## Minimal next step

Robot/PAPER_AUTO owner decision on the single shared edit in `paper_http_server.py` (one GET branch + one attribute).
In parallel MIRROR may implement its own side without touching shared files: `mirror_retest_projection.py`, the optional
`Observation` fields, and tests. Until the route exists, the UI keeps showing the explicit missing-source state.

## MIRROR side implemented (2026-10-20, branch `research/mirror-observation-projection`)

`mirror_retest_projection.py` is the pure read half of the contract above; **the shared backend edit is still not made**.
`Observation` now also carries optional `candidate_ref`, `pattern`, `timeframe`, `account_id`, `recorded_at_ms`
(filled by the sidecar; they are not part of `observation_id`; old journals stay valid and show `null` for what they never had).

Minimal call for the future backend adapter (one GET branch beside `/api/robot/protection-health`, no `runtime.call`):

```python
from mirror_retest_projection import ProjectionUnavailable, project_observations

try:
    body = project_observations(
        server.mirror_observation_journal_path,
        after=int(query.get("after", ["0"])[0]), limit=int(query.get("limit", ["100"])[0]),
        journal_id=query.get("journal_id", [None])[0], account_scope="paper")
except ValueError:                       # bad after/limit
    status, body = 400, {"ok": False, "error": "invalid_mirror_observation_query"}
except ProjectionUnavailable:            # unreadable, too large, or ANY line granting trading permission
    status, body = 503, {"ok": False, "error": "mirror_observations_unavailable"}
else:
    status = 200
```

Behaviour beyond the table above (all covered by `tests/test_mirror_retest_projection.py`):

- `seq` = 1-based number of a complete non-empty line; gaps left by skipped lines stay visible. A last line without a newline
  is an append in flight: ignored, `partial_tail:true`, not malformed.
- The **whole file** is validated on every call (limit `MAX_SCAN_BYTES` = 8 MiB, over it → unavailable): one line with
  `mode != OBSERVE_ONLY`, `executable`/`admission_allowed` not exactly `false`, or a decision other than `WAIT`/`BLOCK`
  refuses the whole answer (`ProjectionViolation`), also when that line is outside the requested page.
- Malformed lines, repeated `observation_id` and lines of another `account_id` are skipped and counted
  (`malformed_lines`, `duplicate_lines`, `foreign_account_lines`); never repaired.
- Truncation/replacement: `cursor_reset:true` and the page restarts at seq 1 when the file is shorter than the cursor or
  the caller's `journal_id` (hash of the first line, returned in every answer) no longer matches.
- Never emitted: `facts`, `r0_*`, any account number. Unknown legacy fields are `null`, not guessed (so `timeframe` is `null`
  for records written before this change).
- Verified on the 60 saved INTEGRATION-5 observations (31 `NAKED_BREAKOUT`, 29 `RETEST_PROVEN`; ~31 KB).
