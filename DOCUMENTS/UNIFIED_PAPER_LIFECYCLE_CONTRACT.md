# Unified PAPER lifecycle: one owner action, no repeated investigations

Status: design contract / NOT deployed. Scope: VPS PAPER only; LIVE forbidden.

## External mechanisms reused
- Freqtrade's stop-entry mode: disable entries while independently continuing exits and STOP management.
- Kubernetes-style level-triggered reconciliation: compare persisted desired state to observed execution/position truth every pass; idempotent steps resume after crashes.
- systemd restart/watchdog: supervise a recovery-capable service, not blindly restart an unsafe writer.

## Single controller, one command
Persistent **desired intent**, not transient Telegram toggle:
`RUN_PAPER`, `QUIESCE_FOR_UPGRADE(target_sha)`, `STOP_PAPER`.
All existing controls dispatch an intent to one durable coordinator; no second process may write PAPER DB. Internal stages are:
1. **QUIESCE**: atomically fence new Admission (including scanner/reentry and outstanding unfilled ENTRY); keep STOP/TAKE, protection monitor, reconciliation and exit executions alive.
2. **DRAIN**: cancel outstanding new-entry LIMITs through the current owner and verify their durable acknowledgements; protect partial fills; let existing protected positions naturally resolve. No manual closes.
3. **RECONCILE**: derive ownership from canonical fills/orders/positions, including never-started Box with missing baseline. No synthetic ownership, no fabricated FLAT.
4. **SAFE_STOP**: only after authoritative FLAT + zero pending entry/exit obligations and canonical stop permission. Existing runtime remains alive if any proof fails.
5. **UPGRADE**: verify exact signed/approved stable SHA, full clean install, atomic release choice and rollback asset; no git pull over a running code directory.
6. **START_RECOVER**: single systemd owner, PAPER-only env, reopen same DB, replay unsettled protection obligations, verify READY/protection and only then lift Admission and restore persisted PAPER_AUTO and reentry intent.
7. **RUN/REPORT**: one concise success/blocked status, durable log with stage, reason, target commit, DB identity and action IDs.

## Safety requirements
- No concurrent backend writers or second SQLite instance; controller coordinates through the active backend before stop.
- Never infer safety from working LIMIT count alone. Proof checks all symbol fills, ownership baseline and position projections; fail closed on ambiguity.
- Keep stop/exit protection active during quiesce. A backend crash while PAPER STOP/TAKE is internally simulated is an availability risk, so do not advertise hard 24/7 continuity until protected startup recovery, supervision and reboot tests pass.
- Do not enable unrestricted `Restart=always` or boot-time trading: start must reconstruct protection and fail closed before Admission, and explicit STOP must persist across reboot.
- If update fails after canonical safe-stop, rollback only with schema-compatibility evidence; otherwise stay STOPPED and report.
- Old-head AXTI deadlock cannot be fixed merely by installing new Python files: an active old process will still use old reconciliation. Bootstrap migration needs a separately approved safe bridge or wait until canonical stop becomes possible. Do not kill backend on open exposure.

## Definition of done
Single owner action requests upgrade; no further owner commands under normal conditions. Interrupted execution resumes at same durable stage without duplicate entry/exit. Deterministic tests: AXTI baseline missing/FLAT; baseline missing with fills/order/exposure (blocked); partial fill; protected open position; crash/reboot during each stage; failed deployment rollback; denied LIVE; explicit STOP persists. VPS acceptance proves health, real protection and successful target SHA.
