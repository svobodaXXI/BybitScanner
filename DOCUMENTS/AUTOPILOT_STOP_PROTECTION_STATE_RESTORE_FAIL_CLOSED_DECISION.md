# AUTOPILOT STOP Protection — State Restore Failure Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

If persisted authoritative STOP-protection state cannot be restored correctly at backend startup, AUTOPILOT must fail closed for new entries.

## Required behavior

- Do not silently reset STOP-protection state to zero.
- Do not allow new AUTOPILOT entries while the restored state is unreadable, invalid, incomplete, or contradictory.
- Risk-reducing management of already-open positions remains allowed under the existing STOP-protection safety rules.
- The backend must expose a degraded/blocked state so the frontend can display why AUTOPILOT entries are unavailable.
- Entry permission may resume only after the authoritative STOP-protection state is successfully restored or explicitly repaired through the approved recovery workflow.

## Rationale

STOP protection is an account-level risk control. Losing or corrupting its persisted state must never fail open.
