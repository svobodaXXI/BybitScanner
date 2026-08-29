---
name: systematic-debugging
description: Diagnose non-trivial BybitScanner defects with an unknown cause through evidence, one hypothesis at a time, and minimal experiments; skip for obvious local typos.
---

# Systematic Debugging

Follow project authority, dirty-tree safety, and the applicable governance gate first. For Trading Workspace, PAPER trading, or terminal diagnosis, also follow the roadmap and active ChangeRequest routing in root `AGENTS.md`.

1. **Reproduce:** state the exact observed failure and conditions. Separate observation from assumption.
2. **Localize:** narrow the failing boundary using logs, state, data flow, callers, and the smallest relevant code or configuration scope.
3. **Hypothesize:** write one falsifiable root-cause hypothesis at a time and name the evidence that would support or refute it.
4. **Experiment:** run the cheapest safe test that can distinguish the hypothesis. Do not make a production patch first unless the patch itself is a reversible diagnostic experiment.
5. **Fix the root cause:** make the smallest authorized correction that addresses the evidenced cause rather than its symptom.
6. **Verify:** run targeted verification, then cover the regression surface in proportion to risk. Use the exact-path verifier required by `AGENTS.md` after implementation.
7. **Escalate:** after roughly three consecutive failed fix attempts, stop patching and reassess architecture, assumptions, ownership, and subsystem boundaries before another change.

Keep failed hypotheses as brief working evidence, not permanent authority. Do not turn an obvious typo with a directly verified correction into unnecessary ceremony. Never use trial-and-error patch chains for execution, orders, risk, PnL, or other money-sensitive paths.
