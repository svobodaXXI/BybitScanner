# Owner requirements — PAPER reliability and modular-monolith consolidation
Date: 2026-10-29. Owner-approved requirements; **future implementation backlog**, NOT an implemented/deployed feature.
Tracking: https://github.com/svobodaXXI/BybitScanner/issues/676
Related deferred unified operator command: https://github.com/svobodaXXI/BybitScanner/pull/675

## Priority: DO NOT CHANGE
**Immediate P0: finish safe update and launch of BybitScanner Robot on VPS with working PAPER_AUTO, Scanner, MIRROR, STOP/TAKE, and stop reentry.** Do not block P0 waiting for a full architecture refactor. Do not claim current VPS is updated until runtime SHA/health prove it. LIVE absolutely prohibited.

## Non-negotiable owner requirements
1. Eliminate *recurring* operational deadlocks: no more repetitive manual diagnosis, chains of ad-hoc commands or the need for owner to intervene whenever an inert, independently provable stale candidate exists. Recover automatically where strict evidence permits. Uncertainty remains fail-closed.
2. Consolidate scattered status registries, recovery decisions, Admission gates, protective logic, order/position records and operator scripts into **one coherent modular monolith**. Reuse existing services/code; **do not** create an extra order execution engine, independent DB, duplicate controllers or redundant trading state authorities.
3. Design mechanisms to *cooperate*: one scoped candidate error must not block unrelated proven-safe operations, while global restrictions must still stop new entries and unsafe process termination whenever any exposure/order/protection is unresolved.
4. One authoritative serialized PAPER writer, one DB, consistent ownership of all entry/exit orders, fills, positions, STOP/TAKE obligations and candidate transitions. Telegram, Terminal and PowerShell are thin adapters to shared application commands and shared operation status.
5. Use an evidence-based desired-vs-actual reconciliation loop: prove per-candidate, per-symbol, per-order, and per-protection obligation state; automatically terminalize strictly proven zero-position/zero-order/zero-fill stale candidates (e.g. AXTI-like missing baseline). NEVER infer FLAT solely from absence of a record.
6. Make operations durable and idempotent: one operation ID for retries, single accountable status source, timeout/partial-fill/restart recovery by reconciling prior operation before deciding any further dispatch. No blind repeats of market close orders or invented fills/PnL.
7. Make lifecycle operations cohesive: freeze admission/reentry before permitted maintenance; separately preserve protection until confirmed FLAT; then safe-stop, fast-forward update by immutable approved SHA, restart through canonical services, reconcile and verify readiness. A future **single owner command** for close→reconcile→upgrade→PAPER_AUTO 24/7 is a **queued approach**, NOT the main project goal and not the present P0.
8. Automatic 24/7 operation must never trade after boot/crash until source-of-truth position and STOP/TAKE coverage are reconstructed, checked, and Admission explicitly re-enabled. An unsafe state remains BLOCKED with an intelligible reason; never SIGKILL, manually edit DB, or bypass security/protection.
9. Telegram **«Закрыть все позиции»** and future Terminal button must reuse one shared PAPER close-all implementation and reporting endpoint, not each invent order-execution code. Marker: `UNIFIED_PAPER_CLOSE_ALL_TERMINAL_REUSE`.
10. Keep owner workload minimal: implement directly in GitHub, deploy to VPS only when safe, use only necessary focused tests, surface real results over artifacts/infrastructure. One command per operator step only when unavoidable.

## Incident making this necessary
On VPS code `d6555455`, Robot was `ROBOT_RUNNING / RECONCILIATION_REQUIRED`; `POST /api/close-all` refused with `409 robot_reconciliation_required`; `POST /api/robot/reconcile` refused for inert AXTI BOX candidate `box-robot-80bb1d9f57df9d65bd3884f7906a679f4e1be1be56f2f28be0ae61b32688ee3a`. Two PAPER positions AIOZUSDT and AKEUSDT remained protected but could not be flattened through that route. Fix #673 is in stable `76ec619f`, while running process still used old code. This exposes circular update/flat dependency. Neither changing source on disk while process runs nor stopping with exposure is a safe resolution.

## Reference architectural approaches
- [NautilusTrader execution reconciliation](https://nautilustrader.io/docs/latest/concepts/execution/reconciliation/): authoritative order/position/execution evidence.
- [Kubernetes Operator pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/): continuously reconcile target and actual state; **no Kubernetes deployment implied**.
- [AWS idempotency guidance](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_prevent_interaction_failure_idempotent.html): retry-safe command identity.
These are engineering references, not instructions to add external platforms.

## Delivery sequence and acceptance
**NOW P0:** safely settle current two positions, resolve AXTI without bypassing protections, deploy approved stable, prove actual VPS build SHA, Robot READY, Scanner RUNNING, PAPER_AUTO, STOP/TAKE healthy and reentry enabled.

**Later P1:** shared candidate/order/protection proofs, autonomous bounded scoped reconciliation and regression test for the AXTI stale-ownership case. **Later P2:** durable operation journal, single lifecycle coordinator reusing existing mechanisms, bounded recovery on restart, unified Telegram/Terminal statuses and owner-approved one-action maintenance.

Accept only observed behavior: inert candidate cannot indefinitely deadlock independent safe operations; active/ambiguous exposure never loses protection; repeated request cannot double-close; startup fails closed pending reconciliation; no duplicate writers, DBs or order engines. Protect existing project behavior and instructions.
