# AUTOPILOT UI-5 — monitoring read contract

Date: 2026-10-19. Status: **PROPOSAL / REQUIRES ROBOT OWNER AGREEMENT**.

Purpose: render candidates, ALLOW/WAIT/BLOCK decisions, protection and ingress in the already approved AUTOPILOT first screen, without any change to execution, admission or runtime ownership.

## Confirmed frontend read sources

- `GET /api/robot/autopilot`: `mode`, `reason`, `version`.
- `GET /api/health`: `robot_admission_ready`, `paper_live_safe`.
- `GET /api/robot/protection-health`: `healthy`, `unhealthy_symbols`.
- `GET /api/open-positions` and `GET /api/paper-state?symbol=...`: account open positions and per-position protection.
- `GET /api/diary/trades`: historical/entry evidence (not a live candidate/decision feed).

These routes are used by UI-1..4. A **verified read schema for current candidates, decisions, and ingress counters has not yet been established**; do not fabricate data or invent a route.

## Requested minimal shared API contract

Before shared backend edits, the Robot/PAPER_AUTO owner should identify existing authoritative **GET-only** projections (prefer reuse over a new endpoint) for:

1. Candidates: stable candidate ID, account scope, symbol, timeframe, pattern, frozen signal ID, status and authoritative update timestamp. Separate candidates from actual positions.
2. Decisions: immutable decision ID, candidate ID (or signal identity), decision time, `ALLOW | WAIT | BLOCK` semantics or explicit mapping from canonical runtime statuses, reason code/text, and freshness/decision version. UI must never convert an unknown status into ALLOW.
3. Ingress: event queue current count, capacity, high-watermark, dropped/overflow count, latency/continuity health and observation timestamp; absent fields render `Нет источника данных`.
4. Protection: reuse current health and per-position status, with observed timestamp if available; health should not imply every order has STOP/TAKE confirmation.

### Acceptance boundary

- Data source must be authoritative and account-scoped, read-only, bounded and safe under PAPER_AUTO load; no polling in this first slice beyond explicit refresh.
- UI receives status, history and explanatory codes; controls that mutate Robot/Scanner/Autopilot are **out of scope** until their existing control endpoints, authorization and safety contract are individually agreed.
- Navigation to AUTOPILOT never arms, pauses, resumes or transfers control.
- No second execution engine, no new candidate admission path, no synthetic operational state.
- Unknown/stale/conflicting data is marked unavailable, **never shown as healthy, ALLOW or protected**.

## Scope and coordination

Owner of shared contract: Robot/PAPER_AUTO direction. UI owner may implement solely in `terminal/frontend` after the contract is agreed.

Potential shared modules/functions to identify **before** any code edits: the existing HTTP GET route registration/response serializers for autopilot state, candidate decisions, ingress/health and protection. Their precise paths and function names are not yet verified; no shared edit is authorized.

UI-1 branch: `feat/autopilot-terminal-ui-1`; UI-2/3/4 stacked separately. MIRROR RETEST research and PR #552 remain separately owned by Codex. No merge to stable, no backend/runtime/DB/LIVE operations.

Next step: confirm the existing read route + schema with Robot owner, then implement a frontend-only monitored section with focused tests and an explicit missing-source state.
