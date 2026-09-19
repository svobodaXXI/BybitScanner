# AUTOPILOT Robot v0.1 — Telegram feed, position navigation, and short wedges

Status: DESIGN DECISION
Date: 2026-09-08
Implementation authorization: GRANTED 2026-09-18: /positions list, position card with chart, closed-trade post, emoji labels

## Main Robot surface

The main Telegram `Робот` tab is a feed of event/state posts, not an interactive chart screen.

Each important lifecycle transition creates a separate post:
- signal accepted for robot observation;
- trade opened;
- trade closed;
- explicit current-state post requested by selecting a position from `Все позиции`.

## Static chart snapshots

Charts in Robot v0.1 are static generated images, not interactive charts.

A current-state position post must include a fresh chart image with the currently authoritative trade state rendered on it, including where applicable:
- scanner pattern geometry and wedge lines;
- signal timeframe;
- current/average entry price line;
- STOP line;
- TAKE line;
- executed-trade markers (triangles) for actual entries/exits;
- ещё не исполненная лимитка рисуется пустым треугольником (контур без заливки);
- current relevant price context.

The renderer must consume the stored/versioned signal/trade snapshot plus authoritative execution state. It must not create a second source of trading state or recompute scanner geometry independently.

The two concrete card types this applies to -- the pre-entry candidate view and the post-entry position view -- are specified in full below (Candidate Monitoring card / Open Position Details card).

## Candidate Monitoring card

Shown for an approved Robot candidate that has not yet opened a position (this is what `Под наблюдением` below lists and opens). Backs the `/monitoring` command and the `monitor:candidate:*` callback.

**Candidate Monitoring is zero-exposure / pre-fill only.** It exists exclusively to describe a candidate for which authoritative filled quantity is still zero. It is never a partial-exposure view.

Explicit status, one of exactly:
- `Ожидание пробоя` -- state machine phase `WAITING_BREAKOUT`;
- `Ожидание ретеста` -- phase `WAITING_RETEST`;
- `Ретест обнаружен` -- phase `RETEST_DETECTED`, no working LIMIT submitted yet (`execution.limit_order_id` absent);
- `Лимитный ордер выставлен` -- a Robot LIMIT exists for this candidate (`execution.limit_order_id` present) with authoritative filled quantity still zero;
- `Истёк / отменён` -- phase `EXPIRED_AT_APEX`, or candidate status `INVALIDATED`/`EXPIRED`.

Chart contents:
- the frozen pattern geometry exactly as originally handed from Scanner to Robot (wedge lines, apex) -- read from the candidate's stored signal snapshot, never recomputed from current market data;
- the pending Robot LIMIT order (price/quantity) if one currently exists for this candidate, while its authoritative filled quantity is still zero.

Partial/full fill markers never appear on this card. The instant authoritative filled quantity for this candidate's LIMIT becomes greater than zero -- even if `robot_trades` has not finished being persisted for it yet -- candidate-only monitoring must stop immediately; that candidate is presented through the Open Position Details card instead (see UX routing below). This is a fail-closed rule: real, non-zero exposure is never described by the zero-exposure card while a downstream record catches up.

Explicit exclusions (fail closed toward showing nothing rather than showing an unproven value):
- no average-entry line/value -- a zero-exposure candidate has no entry to average; average entry is a position-only concept;
- no STOP/TAKE line -- a zero-exposure candidate never has a legitimate STOP/TAKE of its own to display.

## Open Position Details card

Shown once authoritative filled quantity exists for a candidate's entry -- i.e. real, non-zero exposure exists -- whether or not `robot_trades` has finished persisting for it yet, and continues to be shown once the position is closed. This card, not the Candidate Monitoring card, is the fail-closed default representation for any candidate with real exposure. Replaces the Candidate Monitoring card for that candidate/symbol from that point on (see UX routing below).

Fields:
- ticker (symbol);
- direction, `LONG`/`SHORT`;
- position status (open / closed, plus close reason once closed);
- current position size;
- average entry price;
- current PnL;
- STOP (current authoritative value);
- TAKE (current authoritative value);
- entry rationale/pattern (the frozen wedge pattern and direction that produced this entry).

Chart contents, all read from the same frozen signal snapshot that caused this entry (never re-derived from current market data after entry):
- pattern lines (the frozen wedge geometry);
- executed entry marker(s) (triangles) for the actual fill(s) that opened the position;
- average-entry line;
- STOP line;
- TAKE line;
- once closed: exit marker(s) and the close reason, added on top of the same frozen setup.

## Data contract

These constraints govern both cards above and any future consumer of the same monitoring data (including a future `/positions` list):

- **Durable candidate -> trade linkage**: once persisted, `robot_trades.candidate_id` is the durable link back to the originating Robot candidate and its frozen signal snapshot (the existing `robot_trades.candidate_id` -> `robot_candidates` relationship). Monitoring must always resolve a position back through this link once it exists, never through a separate/duplicate copy of the signal. `robot_trades` existence is not, by itself, the sole detector of real exposure -- see the next point.
- **Exposure detection is authoritative-fill-based, not persistence-based**: whether a candidate has moved from zero-exposure to real exposure must be judged from authoritative filled quantity (the order/position record), never from whether `robot_trades` has finished being written yet -- a real fill can exist for one or more passes before `robot_trades` catches up (e.g. a finalize retry). The UX must never keep presenting the Candidate Monitoring card, and must never keep withholding STOP/TAKE/average-entry as merely "not opened yet," for a candidate that already has real, non-zero exposure. When exposure is proven but `robot_trades` is not yet available, fail closed to the Open Position Details representation using whatever authoritative fill/position data already exists, rather than continuing to render Candidate Monitoring.
- **No geometry reconstruction after entry**: pattern lines/apex rendered on any chart, pre- or post-entry, must always be read from the frozen signal snapshot recorded at candidate admission. Recomputing or re-fitting geometry from live market data after entry is prohibited -- the whole point of freezing it is that it must not drift.
- **Authoritative overlay only**: order, execution, protection and trade data drawn on a chart or shown as a field must come from the authoritative persisted records (`paper_limit_orders`, `robot_trades`, current STOP/TAKE, protection obligations) overlaid on top of the frozen setup -- never invented, estimated, or interpolated by the presentation layer itself.
- **Read-only monitoring**: every monitoring view (Candidate Monitoring card, Open Position Details card, `Под наблюдением`, `Все позиции`, `/positions`) is read-only. None of them may create, cancel, or amend an order, or write to candidate/trade state. Trading-state mutation stays exclusively on the existing Robot control surface (`start_robot`/`pause_robot`/`resume_robot`/`close_all_now`/`stop_robot`).

## UX routing

- An active (non-terminal) candidate with authoritative filled quantity still zero opens the Candidate Monitoring card.
- The instant authoritative filled quantity for a candidate's entry becomes greater than zero -- whether or not `robot_trades` has finished persisting for it yet -- monitoring must route to/open the Open Position Details card instead, never continuing to show Candidate Monitoring. This is a fail-closed rule: real exposure is real exposure regardless of which downstream record has caught up. The system must not keep presenting a candidate-only view once real exposure or trade history exists for it.
- `/positions` is intended to eventually list open positions and open this same Open Position Details card/chart for a selected one, reusing this one rendering path rather than a separate implementation (see also the existing `Все позиции` ranking policy above, which this should converge with rather than duplicate).

## `Все позиции`

`Все позиции` is a separate screen.

It uses the previously accepted ranking policy:
1. the currently selected/displayed position first;
2. then larger and more promising positions;
3. remaining positions below.

Selecting a position from this screen returns to / updates the main `Робот` feed by publishing a new current-state post for that position with full information and a fresh chart snapshot.

## `Под наблюдением`

The Robot menu includes a separate `Под наблюдением` action/screen.

It shows approved robot candidates that have been handed to the robot but have not yet opened a position, including their current lifecycle state such as `WAITING_BREAKOUT` and remaining validity where available. Selecting a candidate opens the Candidate Monitoring card specified below.

## Direction support in v0.1

Robot v0.1 trades both wedge directions:

- Falling Wedge -> LONG
- Rising Wedge -> SHORT

The short side is the mirror of the already accepted long policy:
- wait for the first closed 1m candle below the frozen lower Rising Wedge boundary;
- enter PAPER short automatically with the already accepted fixed `1 WV` intent;
- preferred STOP is above the breakout candle high by the technical buffer, subject to the same 2% maximum structural-stop distance rule; if the preferred structural STOP would exceed 2% from actual entry, use the fixed 2% fallback above actual entry;
- TAKE uses the existing scanner `potential_percent`, applying 90% of that potential from the actual entry price downward;
- no second user confirmation is requested before entry.

## Approval semantics

The only user approval is pressing `Робот` next to the scanner signal.

After successful handoff:
`APPROVED -> WAITING_BREAKOUT -> automatic PAPER entry -> OPEN -> managed exit -> CLOSED`.

No additional `WAITING_CONFIRMATION` state or pre-entry confirmation button exists in Robot v0.1.

## Reuse rule

Telegram presentation, position navigation, chart generation, robot lifecycle and PAPER execution must reuse authoritative project capabilities. No duplicate position store, accounting source, scanner geometry engine, potential calculator or execution lifecycle is introduced for this UI.
