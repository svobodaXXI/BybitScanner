# AUTOPILOT Primary Position Selection Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted behavior

When AUTOPILOT has multiple open positions, the main AUTOPILOT chart shows exactly one selected position.

Rules:
- opening a new AUTOPILOT position does not automatically steal focus from the position currently shown on the main chart;
- while the currently shown position remains open, it stays selected unless the user explicitly chooses another open position;
- if the currently shown position closes, AUTOPILOT automatically selects the next highest-ranked open position from `All open trades`;
- when the user manually selects another position from `All open trades`, that manual selection persists until that position closes or the user explicitly selects another one;
- critical events on another position may generate a prominent notification, but they must not automatically switch the main chart away from the user-selected/current position;
- `Trade details` and `Take control of current trade` always apply to the position currently selected on the main chart;
- in `All open trades`, the position currently shown on the main chart remains pinned at rank/row #1, while all other positions are ranked below it using the accepted significance/prospects ranking logic.

## Rationale

The main AUTOPILOT screen must remain visually stable during live monitoring. Automatic focus changes caused by newly opened positions or unrelated events would make the chart jump unexpectedly and reduce operator situational awareness. Notifications can surface important events without changing the selected trading context.
