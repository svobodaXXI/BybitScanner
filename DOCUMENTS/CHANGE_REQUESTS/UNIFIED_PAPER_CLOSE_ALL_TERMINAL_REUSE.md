# Unified PAPER Close All — shared command contract (owner request 2026-10-29)

Status: implementation requirement, NOT proof that it is deployed or working. This is the contract marker for the active PAPER Lifecycle work.

## Single owner-facing action
The Telegram bot's **«Закрыть все позиции»** and the future Terminal's equivalent **MUST invoke one shared backend application command**, not implement independent cancellation, market closing, reconciliation, or protection cleanup. Any PowerShell/operator entrypoint also delegates to that command. Search marker: `UNIFIED_PAPER_CLOSE_ALL_TERMINAL_REUSE`.

## Required semantics
- PAPER account only. LIVE is prohibited. Command has one durable operation ID, deduplicated retries, explicit progress, and one final `FLAT` or `BLOCKED` result; an accepted HTTP request is not proof of FLAT.
- Atomically/durably close new-entry admission including PAPER_AUTO, queued candidates and re-entry after STOP before processing exposure; synchronously settle/cancel outstanding ENTRY requests and verify fills, without touching protective exit orders prematurely.
- Resolve actual position ownership for **all PAPER exposures**. Existing `close_all_now()` is Robot-owned only; account-wide/manual exposure requires explicit authority and must never be skipped while claiming all-flat. Reuse existing authorized PAPER execution and Robot close/guard paths; no independent Telegram or Terminal execution logic.
- Issue market-close requests only through canonical executor with safe idempotency; reconcile authoritative fills and position projections, remaining orders and STOP/TAKE/protection obligations. Never report FLAT until zero exposure, zero working ENTRY/EXIT and zero unresolved protection obligations are proven together immediately before finalization.
- If close confirmation is unknown, retain active protection and fail closed into a durable recoverable state. No blind repeated market closes, manual SQLite editing, SIGKILL, or bypass of reconciliation/admission. Recovery after service restart resumes the same operation by ID, not a new close.
- Backend API defines shared request/status schema, with server-side authorization and identity checks; Telegram confirms the explicit owner's action before dispatch, Terminal later uses the exact same API and reports the same status. No duplicate business logic in clients.

## Implementation anchors
- Existing Robot-only action: `terminal/application/robot_control.py::close_all_now` -> `POST /api/robot/close-all-now`.
- Existing account-wide `PaperRuntime.close_all()` is **not** automatically safe to substitute for the Robot-specific action; ownership and reconciliation checks are mandatory.
- Unified PAPER lifecycle controller is the integration owner: prefer augmenting the existing stable maintenance orchestrator over creating an unrelated daemon.
- Terminal integration TODO marker: `UNIFIED_PAPER_CLOSE_ALL_TERMINAL_REUSE`. Wire future Terminal 'Закрыть все позиции' to the same backend command/status endpoint as Telegram; do not port close mechanics into UI.

## Acceptance evidence
A single Telegram action safely makes two PAPER positions FLAT even with active Autopilot and in-flight entries; terminal command contract shares the exact backend entrypoint; process failure/resume and ambiguous market acknowledgments never duplicate exits; no protection gap. Test these narrow cases and verify actual VPS behavior before labeling operationally ready.

The legacy Robot Control Decision Section 4 deliberately separates close from pause; this new **proposed** unified action does not silently rewrite its semantics. Change owning decision/spec and implement explicitly before exposing the new combined behavior.
