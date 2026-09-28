# Manual Chart → Autopilot Handoff / Position Adoption

Status: **DESIGN QUEUED — 2026-09-28**

Purpose: define the future terminal UX and ownership contract for handing a
manually identified pattern or an already-open manual PAPER position to the
existing Robot/Autopilot without creating a second execution/protection stack.

This document is design authority for the future feature only. It does not
authorize implementation ahead of the current Robot Stability and Geometry
Quality gates, does not authorize LIVE trading, and does not weaken existing
Robot ownership or fail-closed rules.

## 1. Product goal

The owner must be able to work visually in the terminal, mark a formation such
as Ikigai Box, and then either:

1. hand the still-unopened setup to Robot/Autopilot for canonical admission and
   execution; or
2. hand an already-open manual PAPER position to Robot/Autopilot for continued
   management.

The owner should not need to recreate the setup in a second screen or understand
internal candidate IDs.

## 2. One Autopilot entry, context-aware behavior

The terminal exposes one owner-facing **Autopilot** action.

When pressed on the current symbol:

### No open manual position on this symbol

Open the normal Robot/Autopilot workspace. No adoption question is shown.

### Open manual position exists and no conflicting Robot-owned position exists

Show the confirmation:

**Хотите передать эту сделку роботу?**
- **Да**
- **Нет**

**Нет**
- does not mutate the manual position;
- opens the normal Robot/Autopilot workspace;
- shows the list of Robot-owned open positions so the owner can choose which
  Robot trade to inspect.

**Да**
- enters the explicit Position Adoption Gate described below;
- only after successful fail-closed adoption opens the same Robot/Autopilot
  workspace, focused immediately on the newly adopted position.

There are not two separate workspaces. "Да" and "Нет" converge on the same
Robot workspace; only ownership and selected position differ.

If the current position is already Robot-owned, pressing Autopilot must not ask
to adopt it again; it opens that Robot position directly.

A previous **Нет** is not a permanent refusal. As long as the position remains
manual, a later explicit Autopilot press may ask again.

## 3. Robot-owned symbol awareness on every terminal navigation

Robot ownership must be visible whenever the terminal enters a symbol already
being traded by Robot, regardless of navigation source.

This applies to:
- market/watchlist navigation;
- symbol search;
- Scanner signal navigation;
- direct terminal symbol changes;
- open-position lists;
- Robot workspace navigation;
- history/back-forward/deep links where supported.

Every active-symbol change must resolve authoritative Robot ownership/state for
the new symbol.

If the symbol is Robot-owned, immediately show a prominent contextual message,
for example:

> 🤖 Эта монета уже торгуется роботом.
> Позиция: LONG/SHORT · средний вход … · размер …
> Состояние: сопровождение активно / PAUSED / требует внимания.

Provide a direct action to open/focus that Robot position.

The banner must be derived from authoritative Robot ownership/state, not merely
from the existence of an account position. A manual position and a Robot-owned
position are different states.

This should be implemented as one terminal-level **symbol context guard**, not
duplicated popup logic in individual screens.

## 4. Manual chart markup must be machine-readable

A generic visual Fibonacci drawing is insufficient because Robot cannot safely
infer:
- which points are A/B;
- intended direction;
- which levels define the Box;
- whether the drawing is analysis or a tradable setup;
- which timeframe/cutoff the owner intended.

The terminal should therefore provide a specialized pattern-aware drawing
surface, initially **Ikigai Box / Fibo**, backed by structured data.

Future reusable abstraction:

**Manual Pattern Draft**

Suggested immutable fields:
- source = MANUAL_CHART;
- pattern family;
- symbol / market / timeframe;
- direction;
- A/B and required structural anchors;
- source-time cutoff;
- owner-defined Box/Fibo levels;
- normalized instrument tick/quantity context;
- evidence/snapshot identity;
- creation/update version.

The visual drawing and the machine-readable draft are two projections of the
same object.

## 5. Pre-entry handoff

Flow:

Manual chart markup
→ Manual Pattern Draft
→ existing pattern adapter/planner
→ immutable candidate/plan
→ canonical admission
→ existing Robot execution/protection/recovery/reconcile lifecycle.

The human, Scanner and future Autopilot discovery are therefore different
**candidate sources**, not different trading engines:

- SCANNER
- AUTOPILOT
- MANUAL_CHART

After immutable candidate construction they converge on the same canonical
ownership/admission/execution boundaries.

For Ikigai Box, manual markup must not bypass existing grid/STOP/TAKE, tick,
RR or feasibility rules. An invalid manual setup fails closed instead of being
"trusted because the owner drew it."

## 6. Position Adoption Gate

An already-open manual PAPER position must never be silently inferred/adopted.

The explicit **Да** action starts a fail-closed ownership transfer.

Before Robot becomes owner, the system must prove at minimum:
- intended symbol and direction;
- current authoritative position quantity;
- authoritative average entry;
- current position/version identity;
- no conflicting Robot owner for the symbol/exposure;
- working orders are known and compatible or explicitly rejected;
- the referenced Manual Pattern Draft/candidate is still valid enough to build
  canonical management terms;
- immediate protection can be established under current strategy/risk rules;
- no ambiguity exists about what exact exposure Robot is adopting.

On success, persist durable Robot ownership/entry attestation before the UI
claims the position is managed by Robot.

On any failure:
- leave the position manual;
- do not partially adopt;
- explain the exact blocker;
- keep the owner in a safe terminal state.

This is an explicit exception to the current "manual positions stay manual"
default, not a weakening of it. Adoption is legal only through this dedicated
owner-confirmed gate.

## 7. Ownership conflict rules

If a symbol already has Robot-owned exposure:
- do not offer adoption of another ambiguous manual position on that symbol;
- show the existing Robot-owned status first;
- route the owner to that Robot position;
- any future support for multiple independent exposures on one symbol requires
  a separate ownership model decision.

No account-wide inference, auto-adoption, or "same symbol means same trade".

## 8. Robot workspace behavior

Robot/Autopilot workspace is the common destination.

It should contain:
- list of Robot-owned open positions;
- current focused position;
- lifecycle/protection status;
- relevant pattern/plan context;
- clear indication of source: Scanner / Autopilot / Manual Chart / Adopted Manual;
- navigation back to the symbol chart.

When a manual position is successfully adopted, the workspace opens focused on
that same position immediately.

## 9. Future extensibility

Do not hard-code this architecture only for Ikigai Box.

The first implementation may use Box because its Fibonacci/grid geometry is
well suited to direct owner markup, but the durable abstraction should support
future manual drafts for:
- Wedge;
- L-shape;
- other explicitly supported pattern families.

Pattern-specific geometry remains in pattern adapters; ownership/admission/
execution/protection/recovery remain shared.

## 10. Safety and implementation constraints

- PAPER first; LIVE remains separately prohibited until explicitly authorized.
- No second Robot, second order journal, second protection engine or second
  reconciliation stack.
- No silent position adoption.
- No inference of pattern intent from arbitrary chart drawings.
- No direct mutation from UI without canonical validation/admission.
- No adoption if Robot ownership is ambiguous.
- UI must never claim Robot ownership before durable ownership is committed.
- Existing manual positions remain manual unless explicit adoption succeeds.

## 11. Acceptance scenarios

Future implementation is not complete until at least these owner-facing cases
work:

1. Free symbol, no position → Autopilot opens Robot workspace.
2. Manual position on current symbol → prompt Да/Нет.
3. Нет → manual position unchanged; Robot workspace opens to Robot position list.
4. Да + valid adoption → ownership commits; workspace opens on the adopted trade.
5. Да + invalid/ambiguous adoption → no ownership change; clear blocker shown.
6. Current symbol already Robot-owned → immediate Robot-owned banner and direct
   open/focus; no adoption prompt.
7. Navigate from any free symbol to a Robot-owned symbol → the same banner/status
   appears immediately.
8. Manually drawn Box before entry → structured draft → canonical candidate →
   normal admission/execution lifecycle.
9. Generic/ambiguous drawing without required structure → cannot be handed to
   Robot as a candidate.
10. Restart/reconcile preserves adopted ownership and does not turn unrelated
    manual exposure into Robot exposure.

## 12. Scheduling

This epic is queued for future implementation.

Do not pre-empt:
1. active RVL-R6 Robot Stability acceptance;
2. Geometry Quality work and the owner-observed Box false-positive/missed-case
   fixes.

Implementation should begin only after explicit owner reprioritization or after
the current blocking quality gates are complete.
