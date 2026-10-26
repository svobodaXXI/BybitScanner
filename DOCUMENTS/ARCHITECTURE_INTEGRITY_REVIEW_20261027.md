# ARCHITECTURE INTEGRITY REVIEW — planning record (2026-10-27)

Status: **owner discussion recorded; audit proposed, NOT executed**.
Scope: BybitScanner Scanner → durable candidate → admission → PAPER Robot → execution/protection → closure → reconciliation → verifiable statistics. No runtime changes, no LIVE authorization.

## 1. Why this record exists

The owner requested documentation of the architectural/planning discussion and a future audit of disconnected, overlapping or conflicting elements. This is an actionable planning record, **not** a finding that any currently deployed component is defective.

## 2. Retrospective — what could have been sequenced differently

These are planning assessments, not proven root causes:
- We invested deeply in standalone formation geometry and calibration before proving a small, stable end-to-end PAPER trade cycle and trade accounting.
- Module-local tests can succeed while integration between Scanner, candidate persistence/admission, Robot execution, protection, closure and recovery fails. Vertical integration checks should have appeared earlier.
- Multi-grid, re-entry, extra patterns, multi-timeframe and multiple future Robots increase dependencies; they should not precede a proven baseline cycle.
- Trading-strategy performance (net PnL after commissions/slippage, drawdown, trade distribution, out-of-sample/forward evidence) needs its own evidence track; technical correctness alone cannot establish a profitable system.
- Already useful architectural decisions to preserve: separate Scanner and Robot authority, durable state/candidates, PAPER-first, fail-closed risk and protection, recovery/reconciliation, reuse of common pattern/Robot interfaces. No rewrite or microservice conversion is justified by this discussion.

## 3. Existing authority / priority boundaries

Respect `AGENTS.md`, current top priority in `DOCUMENTS/BACKLOG.md`, owning specs and active quest. The 2026-10-04 BACKLOG reset defines the critical path as `real defect → smallest fix → focused regression → merge → PAPER acceptance`, with Robot readiness/recovery, execution/protection, natural PAPER acceptance ahead of speculative infrastructure. This audit must **not** displace a live safety/recovery blocker. It may enter the critical path only where evidence links an integrity issue to a real blocker or acceptance gate.

## 4. Proposed audit — «Рейд: Целостность торгового контура»

### Questions and categories
1. **Disconnected / orphaned**: implemented components with no reachable production caller, no event consumer, or no durable lifecycle owner. Distinguish unused production code from intentional SHADOW/test/research code.
2. **Duplicated authorities**: multiple sources of truth for candles, signals, order/position state, STOP/TAKE, capital/limits or acknowledgements.
3. **Conflicting semantics**: different candle-close boundaries, symbol/timeframe timestamps, candidate identity, state transitions, fill accounting, partial-fill STOP, duplicate obligations or restart behavior.
4. **Broken dependencies/interfaces**: dropped/misordered events, stale data, incompatible models, unhandled errors and cross-process assumptions.
5. **Incomplete joins**: stages separately implemented but without a verified path from candidate through order, protection, exit, reconciled ledger and stats.
6. **Operational hazards**: reconnection, REST/WS catch-up, restart/replay, idempotence, stale messages, degraded readiness and fail-closed behavior.
7. **Observability**: every rejected/blocked transition produces a traceable reason; outcome accounting and cost basis are independently reproducible.

### Audit boundary (inspect in this order)
- A: Bybit WS/REST ingestion → closed-candle cache → Scanner snapshots/decision time.
- B: Geometry detectors → selection → durable candidate/Telegram → Robot admission.
- C: Trade plan/RR/risk/ownership → PAPER entry and partial fills → STOP/TAKE.
- D: Order/position event processing → recovery/reconciliation → close and deduplicated journal.
- E: Journal → PnL/fees/slippage → statistics/independent strategy assessment.
- F: Shared infrastructure vs pattern-specific adapters, and Telegram/Terminal controls.

### Evidence and method
1. Identify actual `main` HEAD and active PAPER owner/runtime versions before making any runtime claim; find owning specs and existing tests.
2. Build a dependency map with each node's file/class, producer, consumer, state store, authority, interface and error path. Label current version and evidence.
3. Trace **one real persisted candidate and PAPER lifecycle** where available; use focused deterministic replay for gaps, never infer live availability or fills from code existence.
4. Record every finding as `verified conflict`, `verified duplication`, `isolated by design`, `unconfirmed hypothesis` or `validated integration`; add severity P0 (safety/loss), P1 (blocked lifecycle), P2 (maintainability/observability). Include file paths, evidence/reproduction, affected transition and narrowest remedy.
5. Prioritize **one** evidenced defect at a time. Apply minimal fix and targeted regression, then required project checks and owner-run PAPER acceptance. No speculative refactoring.
6. Keep a separate coverage matrix: `code exists` / `unit checked` / `integration verified` / `natural PAPER accepted`. Avoid binary “works/does not work” labels where evidence is incomplete.

### Deliverables / acceptance for the audit itself
- Current-code dependency graph **with cross-links and state/control flows**, not a decorative linear chain.
- File/class → responsibility → inputs/outputs → state owner → counterpart interface table.
- Findings register with evidence, severity, duplicate/conflict type, runtime impact, prioritized minimal corrective action.
- Boundary report: what is proven integrated and what remains untested; recommended next smallest vertical slice.
- Explicit note that no Scanner/Robot was started by the agent and no LIVE controls were changed.
Audit documentation is complete when the map and findings are evidence-backed; **no XP/achievement or PAPER success is awarded for documentation alone**.

## 5. Decisions for subsequent planning

- Keep delivery-first PAPER reliability as active priority, especially recovery/protection and complete signal→order→protection→closure→statistics.
- Queue architecture integrity mapping as a **bounded read-only audit**, escalated only for confirmed conflicts obstructing PAPER acceptance or safety.
- Do not replace components with Freqtrade code, claim faster/slower performance, convert to microservices, build three Robots, or rewrite code without measurements and a specific approved defect.
- Freqtrade is a useful architectural reference for comparing capabilities (market data, strategy, risk, execution, position management, persistence, analytics/backtesting), **not evidence of its profitability or of equivalence in BybitScanner**.
- Benchmark latency/CPU/memory/reliability only using comparable workloads and measurement conditions.
- Strategy profitability remains unknown until sufficient independently verifiable PAPER/forward statistics exist.

## 6. Known signals from previous work; NOT automatically current defects

Earlier investigations concerned WebSocket disconnects, closed-candle cache/catch-up, Robot readiness and reconciliation, partial-fill STOP/protection, emergency closure and late Box admission. These are inspection candidates; fresh repository/runtime evidence is required to classify their **current** status. Do not restart investigations broadly if resolved in the authoritative branch.

## 7. Suggested backlog ticket

**ARCH-INTEGRITY-1 — read-only audit of disconnected/duplicated/conflicting links in the PAPER vertical path.**

Priority: queued behind current product-critical safety/recovery blocker, unless direct blocker evidence elevates it. Entry: record current revision + owning contracts; inspect only path A→E; output dependency diagram, verified findings and first bounded follow-up; no runtime start, migration, LIVE action, broad cleanup or large refactor. Exit: owner can identify actual proven integration gaps and smallest next correction.

## 8. Not done in this record

No source-code dependency walk, runtime/state inspection, performance benchmark, PAPER acceptance, strategy evaluation or defect correction was performed as part of this documentation. No assertion of current server status is made.
