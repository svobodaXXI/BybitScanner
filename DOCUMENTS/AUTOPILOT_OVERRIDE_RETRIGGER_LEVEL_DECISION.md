# AUTOPILOT Override Retrigger Level Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

If a new STOP-protection trigger occurs while emergency override is active, the override ends and protection resumes from the current internal recovery level.

The system does not restart from the first 50% restriction level and does not force an immediate drop to 12.5% merely because the retrigger happened during override.

Example:
- internal recovery level before override: 25%
- emergency override temporarily permits ordinary 100% sizing and removes the pause
- a new qualifying protection trigger occurs
- emergency override terminates
- the active restriction returns to the current internal 25% recovery level
- subsequent deterioration/recovery follows the ordinary accepted ladder rules

This preserves the internal risk state across override and keeps emergency override as a temporary bypass rather than a state reset.
