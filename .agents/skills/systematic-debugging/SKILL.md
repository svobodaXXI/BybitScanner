---
name: systematic-debugging
description: Diagnose a non-trivial BybitScanner defect whose cause is unknown; use hypothesis-driven experiments, not for obvious local fixes, change review, or strategy research.
---

# Systematic Debugging

1. **Reproduce:** state the observed failure and conditions; separate observations from assumptions.
2. **Localize:** identify the smallest failing boundary from logs, state, data flow and callers.
3. **Hypothesize:** name one falsifiable cause and the evidence that would support or refute it.
4. **Experiment:** use the cheapest safe discriminating test before a production patch; an authorized, reversible diagnostic patch is acceptable.
5. **Correct:** fix the evidenced cause with the smallest authorized change, exercise the failure class in the cheap focused loop under protocol §7.2, then use its final gate after the patch settles.

Apply `ASSISTANT_PROTOCOL.md` §8.3 immediately when its systemic-regression conditions arise; do not wait for
multiple failed fixes. Otherwise, roughly three failed attempts require stopping the patch loop and reassessing
architecture, assumptions and subsystem boundaries.

Keep rejected hypotheses as brief working evidence, not permanent authority. Never use trial-and-error patch
chains for execution, orders, risk, PnL or other money-sensitive paths. An obvious, proven local typo needs no
diagnostic ceremony. Central repository authority owns recovery, authorization and task completion.
