# AUTOPILOT — Take Control of Current Trade

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

The AUTOPILOT view reuses the area where the manual trading panel normally appears and replaces it with AUTOPILOT-specific control buttons.

Required buttons in this area:
- `Статистика`;
- `Подробности сделки`;
- `Все открытые сделки`;
- `Взять управление текущей сделкой`.

## Take-control behavior

`Взять управление текущей сделкой` is the inverse handoff of sending a manually controlled trade to AUTOPILOT.

When the user activates this action for the currently displayed AUTOPILOT-managed position:
1. control ownership of that position is transferred from AUTOPILOT/robot to the user/manual controller;
2. the existing open position remains open — the handoff must not close and reopen it;
3. the ordinary manual trading terminal opens on the same ticker;
4. the existing position, current STOP, TAKE and relevant live orders remain visible and manageable from the manual terminal according to the manual-trading rules;
5. AUTOPILOT must stop making autonomous risk-increasing or strategy-management decisions for that transferred position after authoritative ownership transfer;
6. the transfer must be explicit and auditable so there is never ambiguous simultaneous ownership by robot and user.

## UX intent

This provides a direct escape hatch from robot management into ordinary manual trade management while preserving the live position and market context.

The AUTOPILOT panel therefore acts as a live supervisory surface rather than a second manual order-entry panel.
