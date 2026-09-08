# AUTOPILOT STOP Protection — Persistence Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

The authoritative STOP-protection state must persist across backend/runtime restarts.

The backend/risk engine is the sole authority for this state. Frontend state is non-authoritative and may be reconstructed from backend snapshots.

At minimum, persisted state must be sufficient to restore the current protection/recovery lifecycle without resetting risk history, including relevant local/global STOP trigger state, recovery progress, current restriction level, pause state, contribution ledger/global score, and emergency-override state where applicable.

Startup restoration must reconstruct the authoritative STOP-protection state before AUTOPILOT may make new risk-increasing decisions.

A backend restart must NOT silently reset STOP protection to a clean state.

If persisted STOP-protection state is missing, unreadable, inconsistent, or cannot be reconciled safely, the runtime should fail closed for new AUTOPILOT risk until the state is resolved rather than assuming zero protection state.

## Rationale

STOP protection is a risk circuit, so its state must survive process/UI restarts and cannot depend on the browser or phone session.

This decision complements the backend-authority rule recorded for STOP protection.
