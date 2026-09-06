# DOM MARKET EXECUTION SEMANTICS

Date: 2026-09-06
Status: AUTHORITATIVE CORRECTION
Applies from merge commit: `3598d23e3c75de725e9e226840e8b265b0db53b1`

## Purpose

This document records the corrected product semantics for marketable/aggressive DOM selections and supersedes any earlier documentation that required a separate confirmation dialog for this specific DOM hold-mode path.

## Authoritative behavior

For PAPER DOM hold-mode:

- a resting BUY/SELL selection remains a LIMIT and follows the existing canonical resting DOM LIMIT lifecycle;
- a BUY selection above the current Ask, or a SELL selection below the current Bid, is treated as MARKET;
- that MARKET action executes immediately from the DOM selection without a separate confirmation dialog;
- the action must still retain durable mutation identity, single-attempt ownership, authoritative state application, no blind retry after ambiguity, and current account/session fencing;
- LIVE mutation behavior and runtime authorization gates are unchanged.

## Superseded statements

The following older statements are no longer authoritative:

- `DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md`, Stage 5: the line saying marketable/aggressive DOM LIMIT explicit confirmation is still open;
- `DOCUMENTS/POST_RECOVERY_AUDIT_CHECKPOINT.md`: the follow-up section and invariant asserting that a marketable/aggressive DOM selection cannot dispatch MARKET without explicit confirmation.

Those statements reflected an intermediate interpretation that was rejected during real-phone product acceptance.

## Verification

Code commit before merge:

`430edd4608aed5c9f9933d5d002417008d30c326`

PR:

`#29 — fix: restore instant DOM market execution`

Merge commit:

`3598d23e3c75de725e9e226840e8b265b0db53b1`

Verification evidence:

- focused DOM marketable test + `DomPanel.test.tsx`: 7/7 PASS;
- production `npm run build`: PASS;
- real-phone PAPER acceptance: PASS;
- observed accepted behavior: marketable DOM selection executes immediately as MARKET with no confirmation dialog.

## Architectural note

This correction changes product interaction semantics only. It does not declare a new shared-core slice. Any remaining lifecycle consolidation for the immediate DOM MARKET path must be evaluated separately as a concrete architectural follow-up against the existing shared Market lifecycle.
