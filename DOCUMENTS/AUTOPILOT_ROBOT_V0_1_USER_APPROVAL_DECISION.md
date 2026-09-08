# BybitScanner — Robot v0.1 User Approval Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

Decision:

For Robot v0.1, user confirmation happens exactly once at the scanner-signal candidate stage through Telegram actions:

- `Взять в работу`
- `Пропустить`

Selecting `Взять в работу` transitions the candidate to `APPROVED` and authorizes the robot to wait for the defined breakout condition. No second user confirmation is required immediately before PAPER entry.

Selecting `Пропустить` rejects the candidate for Robot v0.1.

After approval, the robot remains subject to all other candidate-expiry, breakout, sizing, STOP, TAKE, execution, and safety rules. Approval does not itself create an order.

Architecture rule:

Telegram is only the approval surface. Candidate lifecycle and execution remain owned by their common authoritative project components. Robot v0.1 must not create a parallel approval-specific execution path.

# END_OF_DOCUMENT
