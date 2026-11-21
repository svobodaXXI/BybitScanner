# Safe transition across a reconciliation deadlock — owner requirement and universal invariants

**Status:** queued implementation, NOT built, deployed or proven. Tracker: https://github.com/svobodaXXI/BybitScanner/issues/678. Related architecture: #676; deferred unified Close-All: #675.

## Incident / why this mechanism is required
2026-10-29 VPS active old SHA `d6555455`. Fixed stable `76ec619f` has AXTI stale Box-candidate repair #673, but cannot be loaded into the old running Python backend. Robot `ROBOT_RUNNING/RECONCILIATION_REQUIRED`; `POST /api/robot/reconcile` returns 409 for `box-robot-80bb1d9f57df9d65bd3884f7906a679f4e1be1be56f2f28be0ae61b32688ee3a`. Coordinated `/api/close-all` returns 409 `robot_reconciliation_required`. Canonical `paper_maintenance.py` requires safe stop before ff-only update, and shutdown cannot be certified while Robot is unresolved and PAPER exposure is protected by the old process. AIOZUSDT SHORT 2618 and AKEUSDT SHORT 100 were OPEN, with confirmed STOP/TAKE and healthy coverage at last observed snapshot. PAPER_AUTO owner-set OFF v11. Never assume they are now FLAT without a new proof.

Cycle: **stale candidate → reconcile blocked → coordinated flatten blocked → safe stop blocked → repair cannot run**. The current safeguards correctly refuse unsafe transitions, but lack a demonstrably safe recovery path, creating a liveness deadlock.

## Universal principles (apply to all analogous situations)
1. **Safety AND progress:** unsafe operations remain blocked, but provably repairable inconsistencies require a finite, auditable canonical recovery path. Don't defeat safety to achieve progress.
2. **Single mutation owner:** one serialized PAPER runtime and one DB own all executions, positions, order identities, STOP/TAKE and candidate state; external maintenance scripts orchestrate authorized API commands and cannot become a second writer. systemd supervises processes; it does not certify trading safety.
3. **Scope of failure:** distinguish candidate-local, symbol-local, order/position-local, protection-local, and globally unsafe faults. A candidate-local problem need not veto an independently proven safe, unrelated protection/closure operation. Global shutdown needs a complete global proof.
4. **Evidence, not intuition:** no position, working order, fill, open trade, protection obligation or competing owner (for the exact candidate/symbol) must be proved by authoritative records and absence checks before tombstoning an inert candidate. Missing row does not equal proven FLAT.
5. **Admission vs protection are different:** freeze entries/Autopilot without disabling protective EXIT work; never promise STOP/TAKE continues after the process protecting it has stopped.
6. **Idempotent, durable operation:** record operation ID, immutable build SHA and DB identity and phases; on crash/timeout re-check previous execution, do not blindly retry market orders; reconcile partial fills and economic data.
7. **Bounded attempts and escalation:** retries are limited and evidence-driven, with a specific blocker/status for owner; no infinite cycle of diagnostic commands.
8. **Version-aware transition:** fixed source must become active only through a proven safe handover; no hot-patching a running process by merely changing files, and no simultaneous old/new trading owner.
9. **Proof before READY:** deployed exact SHA, durable Robot READY, Scanner RUNNING, PAPER_AUTO confirmed (if authorized), protection healthy, stop-reentry settings and ownership reconciled. HTTP 200 and active systemd units are not enough.
10. **No bypasses:** LIVE permanently prohibited; no direct SQLite surgery, PID killing, unsafe restart, weakening Admission, or dropping STOP/TAKE to deploy.
11. **One cohesive control plane:** existing Robot recovery, PaperRuntime, runtime intent, stop/maintenance and Telegram/Terminal commands become layers of one shared lifecycle contract. Retire contradictory paths rather than layering another coordinator.
12. **Minimal owner work:** automatic safe recovery or one operation with clear result; development focused on the immediate observed blocker, with only required tests.

## Required engineering result
Implement a **safe recovery/version transition bridge**, not a new trading engine. Start with the exact AXTI deadlock and use a regression fixture. For provably never-started stale candidates, canonical owner should terminalize them without touching other symbols; if evidence uncertain, protect current positions and surface a precise BLOCKED reason. Define safe transition preconditions (globally FLAT before a shutdown unless an explicitly proven protection-continuity handover exists), single-flight maintenance, immutable target SHA, durable stepwise journal, and post-start verification. Reuse merged fixes #673/#674 where applicable.

## Acceptance criteria
- Reproduced AXTI scenario can transition without bypassing ownership/Admission, without unprotected AIOZ/AKE exposure, and without double close.
- Partial execution, timeouts, stale price, active limit, unresolved protection or duplicate ownership preserve safeguards and report action-specific blockers.
- Exactly one serialized writer and protection authority at a time; any reboots recover admission-closed until reconciliation.
- Actual VPS shows running corrected build SHA and verified readiness, or the operation remains BLOCKED with protection preserved.
- Never represent this design document as deployed code.

**Priority:** current immediate work is launching Robot on VPS. Implement bridge to resolve this as its required dependency; broader consolidation #676 follows, and owner one-command flatten/deploy workflow #675 stays queued until specifically scheduled.
