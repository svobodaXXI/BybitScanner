# CR-ROBOT-LEGACY-PROTECTION-RECOVERY-001 — Evidence-backed legacy PAPER protection recovery

Status: IMPLEMENT_IN_PROGRESS  
Baseline: `main` @ `1d9f86ecd525873a0720ec29a15e85753aaec642`  
Scope: PAPER Robot v0.1 only. LIVE is out of scope.

## Objective

Recover legacy pre-D2.3 Robot trades whose durable protection obligation is already `TRIGGERED` but whose `robot_trades.entry_quantity` and `entry_position_version` are both NULL, without weakening the normal D2.3 ownership gate, fabricating fills, or adding a second protection/execution lifecycle.

The recovery must reconstruct the missing canonical entry attestation only when immutable PAPER execution evidence proves it exactly. After that one-time attestation, the existing protection-obligation dispatcher, stable `exec_id`, `PaperMarketExecutor`, FLAT proof, Robot trade finalizer, and reconciliation flow remain authoritative and unchanged.

## Incident boundary

Maintenance reconciliation can currently enter `RECONCILIATION_REQUIRED` and deterministically stop on a legacy `TRIGGERED` protection obligation before reaching later stale-ledger checks. The current dispatcher correctly refuses an autonomous close when either canonical D2.3 entry-attestation field is missing.

A pre-dispatch-only legacy bypass is insufficient and is rejected by this CR: after a correlated close execution reaches FLAT, the existing finalizer again requires `trade.entry_quantity` to prove `actual_entry_notional_usdt` and `realized_pnl_pct`. A parallel recovery attestation would therefore duplicate ownership semantics across multiple safety gates.

## Decision

Use **evidence-backed canonical attestation backfill**, not quarantine/abandon and not a second legacy dispatch path.

The operator authorizes a specific legacy trade recovery, but the operator does not type or invent the quantity/version. The runtime derives them from durable evidence and persists them into the existing canonical `robot_trades.entry_quantity` and `entry_position_version` fields only if every proof below passes.

This is a one-time compatibility repair for pre-attestation rows. Modern trades continue to use the normal entry-time attestation path and can never use this recovery merely because their current aggregate position happens to match.

## Eligibility — fail closed

A legacy attestation may be created only when all of the following are simultaneously true:

1. Runtime is `(ROBOT_RUNNING, RECONCILIATION_REQUIRED)`; admission remains closed.
2. The target `robot_trade` exists, is still OPEN, and both `entry_quantity` and `entry_position_version` are NULL. Exactly-one-missing or already-populated rows are not legacy-recovery eligible.
3. The linked Robot candidate exists, belongs to the same account/symbol/trade, and remains `OPEN`.
4. A durable protection obligation exists for that trade, is still `TRIGGERED`, and no execution exists for its stable close `exec_id`. `DISPATCHING` is not eligible because side-effect certainty is already ambiguous.
5. Exact entry execution identity can be recovered from the candidate's durable entry state. For the initial micro-slice, support only the existing entry form(s) whose order/execution linkage can be proven from current repository evidence; do not generalize to unsupported historical shapes.
6. Every reconstructed entry execution belongs to the same PAPER account/symbol, has the expected entry side, positive quantity/price, and immutable identity.
7. Replaying the PAPER execution ledger for the account/symbol proves the position was FLAT immediately before the first reconstructed Robot entry execution.
8. From the first reconstructed Robot entry execution through the authorization instant, there is no non-entry execution for that account/symbol. Any manual add/reduce, replacement lifecycle, opposite-side execution, or unidentified execution rejects recovery.
9. The summed reconstructed Robot entry quantity is positive and equals all available ownership evidence: current position quantity and the triggered obligation's observed quantity.
10. The reconstructed entry VWAP equals the Robot trade's durable `average_entry` and the current position projection's `average_entry` under the repository's existing Decimal semantics.
11. Current position side matches the Robot trade direction, the position is non-flat, and current position version is positive.

If any proof is absent, ambiguous, inconsistent, or unsupported, persist nothing and leave the trade/obligation unresolved.

## Canonical values

When the proof passes:

- `entry_quantity` = exact quantity reconstructed from the identified Robot entry executions;
- `entry_position_version` = the current authoritative position projection version, but only because the execution-ledger proof establishes that no position-mutating execution occurred after the reconstructed entry lifecycle. Therefore the current version is still the post-entry version required by D2.3.

No value is inferred from Working Volume, Scanner notional, candle data, current market price, historical candle replay, or a manually typed quantity/version.

## Durable audit evidence

Do not add a second ownership schema if the existing candidate state can record the recovery evidence atomically with the canonical backfill.

The recovery transaction should durably record, under the existing OPEN candidate's execution metadata, a compact `legacy_entry_attestation` record containing at least:

- version/source marker such as `execution_ledger_reconstruction_v1`;
- operator/client action identity;
- target `trade_id` and protection `obligation_id`;
- reconstructed entry order identity and execution identities;
- proven entry quantity;
- proven/current position version;
- authorization timestamp.

The canonical trade-field update and this audit record must commit atomically or neither commits. Repeating the same authorization is idempotent; conflicting reuse fails closed.

If the existing persistence API cannot make the audit record and canonical field update atomic without a schema change, stop and return to SPEC rather than silently weaken auditability.

## Post-attestation behavior

The attestation operation itself submits **no Market order** and changes no position/protection/order state.

After successful attestation, the operator may run the existing maintenance reconciliation. That existing path must then:

1. use the unchanged D2.3 ownership gate;
2. dispatch the already-latched obligation with its existing stable `order_id`/`exec_id` through the existing `PaperMarketExecutor`;
3. require correlated execution plus authoritative FLAT before finalization;
4. compute PnL using the now-proven canonical `entry_quantity` under the existing owner-frozen D2.3 formula;
5. resolve the obligation and close the Robot trade exactly once;
6. continue to later reconciliation checks, including stale OPEN-ledger candidates;
7. return to `PAUSED`, never directly to `READY`, only after the entire reconciliation pass is clean.

## Explicit non-goals

- No direct SQLite hand-edit/backfill.
- No operator-entered quantity or position version.
- No `TRIGGERED -> abandoned/quarantined/resolved` shortcut without a correlated execution/FLAT lifecycle.
- No change to normal D2.3 ownership semantics for modern trades.
- No widening of `close_all_now()` legality in `RECONCILIATION_REQUIRED`.
- No second Market executor, protection state machine, reconciliation engine, or event-sourcing subsystem.
- No automatic claim of manual/mixed positions.
- No LIVE behavior.
- No Telegram UI in this micro-slice; Telegram recovery controls follow only after backend recovery is proven.

## Required focused verification

1. Exact legacy proof succeeds and atomically fills both canonical attestation fields plus durable audit metadata.
2. Same authorization repeated is idempotent and does not change the resulting evidence.
3. One-field-missing, modern populated, closed trade, non-OPEN candidate, non-TRIGGERED obligation, or existing stable close execution is rejected.
4. Pre-entry non-flat ledger is rejected.
5. Any unidentified/manual execution after the first entry execution is rejected even when final quantity happens to match.
6. Quantity, side, VWAP, current average-entry, observed-trigger quantity, or position-version evidence mismatch is rejected.
7. Failed proof persists nothing.
8. After a successful attestation, the existing maintenance reconciliation closes the triggered legacy obligation through the existing stable execution path, reaches FLAT, finalizes the Robot trade, and resolves the obligation exactly once.
9. Repeated reconciliation and process restart create no duplicate close execution or duplicate finalization.
10. A modern trade with an ownership mismatch remains fail-closed exactly as before.
11. Reconciliation continues past resolved protection obligations and can report/repair independent stale-ledger blockers rather than falsely declaring success.

## Implementation slicing

### Slice A — proof + canonical attestation only — DONE 2026-09-17

Implemented in `terminal/persistence/legacy_protection_recovery.py` as a pure/read-only proof plus one package-internal single-writer transaction. No schema migration and no Market/execution port were added. The transaction fills the existing canonical trade fields and writes `execution.legacy_entry_attestation` into the existing candidate state atomically; same-action replay is idempotent and conflicting action reuse fails closed.

Focused regression: `tests/test_robot_legacy_protection_recovery.py` covers exact proof, atomic/idempotent persistence, no execution/obligation/position side effect, failed-proof no-write behavior, modern/partial attestation rejection, client-action conflict, pre-entry non-flat evidence, post-entry foreign execution, lifecycle/economics mismatches, and existing stable close execution.

Verified code/test head: `2053daf08048a948165b995b7e9f5f2e5986a0dc`. GitHub Actions `Robot PAPER acceptance` run #74: **PASS** (compile + deterministic acceptance suite).

### Slice B — existing reconciliation acceptance — DONE 2026-09-17

Proven in `tests/test_robot_legacy_protection_reconciliation.py`: a `TRIGGERED` obligation flows through its stable `exec_id`, the existing `PaperMarketExecutor`, a correlated execution, authoritative FLAT, and the existing Robot trade finalizer to `RESOLVED`. Repeated reconciliation and process restart create no duplicate close execution and no duplicate finalization.

No production reconciliation code required modification: the existing path consumes the canonical attestation unchanged. GitHub Actions `Robot PAPER acceptance` run #77: **PASS**.

### Slice B.1 — operator boundary — DONE 2026-09-17

`terminal/application/robot_legacy_protection_recovery.py` exposes `attest_legacy_protection_recovery(...)` as the PAPER-only operator entry point. It accepts identities only (`trade_id`, `obligation_id`, `client_action_id`), opens one short-lived `SQLiteStore` following the existing Robot operator-command pattern, and delegates every ownership proof plus the atomic canonical persistence to `terminal.persistence.legacy_protection_recovery.attest_legacy_robot_entry`.

Boundary review found no defect, so no production code was extended in this slice. Verified properties: quantity/version can never be operator-supplied (keyword-only identity signature), `(ROBOT_RUNNING, RECONCILIATION_REQUIRED)` legality and identifier/clock validation stay enforced in the proof helper, no reconcile is invoked, no execution/order/Market port is reachable, and the connection is released exactly once on both success and rejection.

Focused regression: `tests/test_robot_legacy_protection_recovery_command.py` covers canonical persistence, same-action idempotent replay, failed-proof no-write, absence of execution/position/obligation/order side effects, deterministic connection lifetime, fail-closed invalid identifiers/clock/database path, and the identity-only/no-reconcile boundary shape. The existing Slice A scenario fixture is reused rather than duplicated (`LegacyProtectionRecoveryFixture`).

This module and the new test module are now part of the `Robot PAPER acceptance` workflow compile and run surface. Verified code/test head: `eea52e77a4b66a2b23b525a210a3549153945148`. GitHub Actions `Robot PAPER acceptance` run #79: **PASS**.

### Slice C — runtime incident recovery — NEXT

Only after A+B are merged and verified: take a fresh read-only production/PAPER snapshot, present the exact eligible legacy trades and reconstructed evidence, obtain explicit operator authorization for the real state-changing recovery, then execute attestation followed by maintenance reconciliation. Telegram manual trading acceptance starts only after reconciliation is clean.

## Rationale

This keeps one ownership truth. Mature reconciliation systems recover from authoritative execution/order/position evidence when exact and remain unresolved when evidence is incomplete. For BybitScanner, filling the already-designed canonical D2.3 fields from provable immutable PAPER evidence is smaller and safer than introducing a permanent second legacy ownership model merely to bypass two existing safety gates.
