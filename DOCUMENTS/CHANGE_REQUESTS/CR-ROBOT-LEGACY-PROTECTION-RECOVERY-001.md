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
5. Exact entry execution identity can be recovered from the candidate's durable entry state. Only two historical entry shapes are supported, and no other shape may be generalized to:
   - **single durable LIMIT entry** (`entry_path == "LIMIT"`): the candidate's durable `limit_order_id` yields the complete entry execution set (Slice A);
   - **composite LIMIT partial + exactly one same-side top-up** (`entry_path == "MIXED"`): supported only under the closed-ledger conditions of Slice A2 below.

   Any other historical shape — N-leg entries, multiple top-ups, entries on symbols carrying unrelated execution history, or entries whose ownership cannot be locked by durable Robot-authored evidence — remains unsupported and must fail closed.
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

### Slice A2 — composite MIXED legacy entry proof — DONE 2026-09-17

Read-only analysis of the live PAPER database established that the remaining legacy incident (`1000TAGUSDT`) is a composite entry that the Slice A proof correctly refuses with `legacy recovery currently supports only durable LIMIT entry identity`. This slice narrowly extends the **pure proof only**. No new persistence path, no schema change, no second execution/protection/reconciliation lifecycle, and no change to the operator boundary (input stays identity-only).

#### Implementation and blocker fix — verified 2026-09-17

Slice A2 was implemented at `8440295fb908b9d3c97d499b3f1508533e43679a` (Robot PAPER acceptance #81 PASS). Review identified a missing competing-ownership guard; fixed at `1f40d9c78d3890387ce1a49589d416318efa3656` (Robot PAPER acceptance [#82](https://github.com/svobodaXXI/BybitScanner/actions/runs/35266412792) PASS).

The MIXED pure proof now requires durable candidate/trade snapshots and rejects any other candidate or trade for the same account/symbol, regardless of lifecycle status. This deliberately conservative closed-history check does not infer ownership from the two executions alone. The existing attestation transaction reads those records before proof and persists nothing on rejection. LIMIT proof behavior and the application boundary, reconciliation, execution/protection lifecycle, schema, HTTP/CLI/Telegram and LIVE behavior are unchanged.

Focused coverage includes competing durable candidates/trades, missing ownership evidence, rejection without canonical writes, successful MIXED attestation, multiple LIMIT fills, non-strict top-up ordering, missing/invalid partial anchors, and existing LIMIT regression. Verification: A2 class 18 tests; full legacy recovery 25 tests; command/reconciliation/robot-control regression 61 tests; local Robot PAPER acceptance compile surface and 67 tests PASS; protected task finish PASS. No live PAPER database, real attestation/reconciliation or Robot start/resume was used.

#### Supported shape — exhaustive

Slice A2 applies if and only if all of the following hold:

- `robot_trades.entry_path == "MIXED"`;
- exactly one proven LIMIT partial fill, reached through the candidate's durable `limit_order_id`;
- exactly one subsequent same-side execution (the top-up);
- the PAPER execution ledger for that account/symbol contains **exactly those two executions across its entire history**;
- no opposite-side execution anywhere in that history;
- no unrelated or manual execution history on the symbol;
- no competing candidate/trade ownership for the symbol.

#### Fail-closed conditions — all simultaneously required

1. Both canonical entry fields (`entry_quantity`, `entry_position_version`) are NULL; exactly-one-missing or already-populated rows are not eligible.
2. The linked candidate exists, is still `OPEN`, and matches the trade's account, symbol and trade linkage.
3. A durable protection obligation exists for the trade and is still `TRIGGERED` (`DISPATCHING` is not eligible).
4. No execution exists for that obligation's stable protection-close `exec_id`.
5. The candidate carries a durable `limit_order_id`.
6. That order id yields exactly one LIMIT execution.
7. `first_partial_at_ms` and `first_partial_price` are present and consistent with that LIMIT execution.
8. Exactly one later same-side execution exists.
9. That second execution's timestamp is `<= robot_trades.entry_time_ms`, proving Robot already knew of it when it finalized the entry.
10. The summed entry quantity is positive and equals both the current position quantity and the obligation's `observed_quantity`.
11. The exact VWAP of both executions equals `robot_trades.average_entry` **and** the current `position.average_entry` under the repository's existing Decimal semantics.
12. The LIMIT-only VWAP does **not** equal the stored `average_entry` (otherwise the top-up is not Robot-owned).
13. `position.version == 2`, matching exactly two position mutations.
14. The current position side matches the Robot trade direction and the position is non-flat.
15. No competing candidate/trade claims ownership of the same executions.
16. No existing `legacy_entry_attestation` and no conflicting `client_action_id` reuse.

Any mismatch, ambiguity, absent anchor, or unsupported shape persists nothing and leaves the trade and obligation unresolved.

#### Evidence rationale

Ownership of the top-up execution is **not** provable from identity convention: the live ledger contains no execution carrying Robot's deterministic `robot-retest-limit-*`, `robot-topup-limit-*` or `robot-confirm-market-*` action identity, and every historical entry execution instead carries Trading Workspace identity (`tw_<uuid4>`), which a manual Workspace action would carry too. Attribution is therefore established from durable Robot-authored evidence instead:

- `entry_path == "MIXED"` is a durable classification written only by the single Robot production path that creates trades (`robot_breakout_monitor` → `create_robot_trade`); manual/Workspace flows never create `robot_trades`. Robot itself recorded that its entry was composite.
- The exact VWAP equality is the **attribution lock**: Robot's own durable `average_entry` equals the VWAP of the full two-execution set and is not equal to the LIMIT-only price. Had the top-up belonged to anyone else, Robot's stored `average_entry` would be the LIMIT-only value.
- `entry_time_ms` ordering proves the second execution preceded finalization, so it is a top-up rather than later averaging.
- `position.version == 2` proves exactly two position mutations formed the position.
- The obligation's `observed_quantity` and the current position quantity independently cross-check the same sum.
- Healthy modern `MIXED` trades in the same database (`BLESSUSDT`, `BIRBUSDT`, `AKTUSDT`) all carry `entry_position_version = 2`, confirming this is the established semantics of the shape rather than an inference invented for this repair.

Because the ledger is closed at exactly two executions, no alternative attribution of the top-up exists that remains consistent with Robot's own durable `average_entry`.

#### Scope boundary

- Not a generic multi-leg recovery and not an N-leg framework.
- Not applicable to symbols carrying any extra execution history; closed-ledger is a load-bearing condition, not a convenience.
- No operator-supplied quantity or position version.
- No manual evidence override of any kind.
- PAPER only; LIVE remains out of scope.

### Slice C — runtime incident recovery — NEXT

Only after A+B are merged and verified: take a fresh read-only production/PAPER snapshot, present the exact eligible legacy trades and reconstructed evidence, obtain explicit operator authorization for the real state-changing recovery, then execute attestation followed by maintenance reconciliation. Telegram manual trading acceptance starts only after reconciliation is clean.

#### Precondition — re-prove immediately before attestation

The read-only proof must be re-run immediately before any real attestation, not merely once during planning. The PAPER backend keeps writing to the live ledger, and Slice A2 eligibility depends on the symbol's ledger remaining closed. **Any new execution on `1000TAGUSDT` invalidates closed-ledger eligibility** and must abort the recovery rather than proceed on a stale proof.

#### Recorded incident state — read-only snapshot 2026-09-17

Runtime is `(ROBOT_RUNNING, RECONCILIATION_REQUIRED)`. Exactly two Robot trades in the database lack canonical attestation:

- `FARTCOINUSDT` (`robot-trade-507c993dd4c0b2c02f403e95`, `entry_path = LIMIT`) — **eligible today** through the existing Slice A proof; proven quantity `1736`, proven position version `1`; ledger holds exactly one entry execution.
- `1000TAGUSDT` (`robot-trade-e844939cd6c0ea4768c38b3e`, `entry_path = MIXED`) — **requires Slice A2**; composite entry of `357` (LIMIT) + `15` (same-side top-up) = `372`, position version `2`.

Both obligations must become recoverable before reconciliation can clear the incident: `reconcile_robot()` fails the whole pass while any unresolved protection obligation remains, so recovering only `FARTCOINUSDT` would leave the runtime in `RECONCILIATION_REQUIRED`. Closing a position by hand does not help either, because an obligation whose trade closed without its own stable close execution is deliberately left unresolved.

After both obligations resolve, `0GUSDT` (`robot-trade-4ca4ac75045e1c25fcc023ef`) remains a separate, later blocker: its real position is flat while its OPEN ledger row is unfinalized, and it carries no attributable protection-obligation evidence. It is reported by the stale-ledger checks that run after the obligation stage and is explicitly out of scope for Slice A2.

## Rationale

This keeps one ownership truth. Mature reconciliation systems recover from authoritative execution/order/position evidence when exact and remain unresolved when evidence is incomplete. For BybitScanner, filling the already-designed canonical D2.3 fields from provable immutable PAPER evidence is smaller and safer than introducing a permanent second legacy ownership model merely to bypass two existing safety gates.
