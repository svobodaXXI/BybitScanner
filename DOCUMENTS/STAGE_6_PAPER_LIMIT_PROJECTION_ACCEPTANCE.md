# Stage 6 — PAPER LIMIT projection acceptance

Date: 2026-09-06
Status: ACCEPTED
Authoritative code checkpoint before this documentation: `030060b0a04af9b8fe26e41382701ba68cda39b9`

## Accepted invariant

For PAPER active LIMIT orders, the following surfaces describe the same authoritative order set:

- Trading Panel LIMIT count/list;
- DOM own-order projection;
- Chart active LIMIT line projection;
- backend `paper_state(...).active_limit_orders` backed by durable SQLite state.

## Automated evidence

### Backend runtime / matching / execution

PASS:

- `tests/test_terminal_paper_runtime.py`
- `tests/test_terminal_paper_matching.py`
- `tests/test_terminal_paper_execution_projection.py`
- `tests/test_terminal_paper_exactly_once.py`

Result: 24 passed.

Additional account/runtime HTTP/context suite:

- `tests/test_terminal_active_account_restore.py`
- `tests/test_terminal_paper_http.py`
- `tests/test_terminal_paper_context.py`

Result after fixture maintenance: 53 passed + 4 subtests passed.

Relevant LIMIT fill behavior already covered in `test_terminal_paper_http.py`:

- duplicate book update does not repeat a partial LIMIT fill;
- foreign-account LIMIT is ignored by the PAPER matcher/projection;
- full LIMIT fill atomically removes the order from `active_limit_orders`, updates the position, and advances `state_revision`.

### Restart persistence

Added focused regression coverage:

- `tests/test_terminal_paper_limit_restart.py`

Result: 1 passed.

This proves an active PAPER LIMIT survives closing and reopening `PaperRuntime` on the same SQLite database with the same `order_id`, side, price semantics and time-in-force, and remains present in `active_limit_orders`.

### Frontend projection gate

PASS: 9 test files / 40 tests.

- `src/paperTrading/paperTradingStore.test.ts`
- `src/orders/paperLimitProjection.test.ts`
- `src/orders/paperLimitCreate.test.ts`
- `src/chart/PendingLimitLine.test.tsx`
- `src/components/DomPanel.test.tsx`
- `src/components/ChartPanel.fastLimit.test.tsx`
- `src/components/ModePanel.limitConfirm.test.tsx`
- `src/components/ChartPanel.averageEntry.test.tsx`
- `src/components/ChartPanel.stop.test.tsx`

Production frontend build: PASS (`tsc -b && vite build`).

The Vite chunk-size warning and jsdom `HTMLCanvasElement.getContext()` warnings are non-blocking and did not cause test failures.

## Real-phone PAPER acceptance

Acceptance performed against Vite preview on the local network.

Observed PASS:

1. One resting PAPER LIMIT was created.
2. The same order was simultaneously visible in:
   - Trading Panel LIMIT projection;
   - DOM own-order projection;
   - Chart active LIMIT line projection.
3. A normal cancel action was executed.
4. The order disappeared from all three frontend projections together.

Result: PASS.

## Conclusion

The Stage 6 PAPER LIMIT projection gate is accepted for the tested scope. The frontend surfaces derive from the authoritative PAPER order state, durable restart persistence is covered, and fill/cancel removal semantics are covered.

Any future change in this area should be driven by a newly identified concrete defect or requirement, not by reopening already accepted projection behavior without evidence.
