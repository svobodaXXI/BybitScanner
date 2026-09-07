# AUTOPILOT Stop-Series Cooldown Bars Decision

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

After the stop-series protection triggers, the cooldown duration is measured in candles of the strategy's working timeframe rather than a fixed wall-clock duration.

Concept:

`STOP-SERIES TRIGGER -> COOLDOWN FOR N WORKING-TIMEFRAME BARS -> RECOVERY MODE AT 50% SIZE`

The exact number of candles `N` is intentionally not fixed yet and remains `NEEDS VALIDATION` using PAPER data.

This decision belongs to the previously accepted two-stage protection flow:

`stop-series / elevated stop frequency -> cooldown -> 50% reduced size -> recovery-score process -> normal size`

Only actual protective STOP exits with negative final result contribute to the stop-series counter. Stop-series triggering is combined: either consecutive STOPs or elevated STOP frequency inside a bounded window. Exact trigger counts/windows also remain `NEEDS VALIDATION`.
