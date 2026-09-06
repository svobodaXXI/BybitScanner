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

## Blocker escalation method

When a defect survives an apparently reasonable first fix, do not immediately stack another workaround on top. Treat the failed fix as new evidence and widen the diagnosis by exactly one architectural level.

Use this sequence:

1. **Freeze the observed facts.** Record what is visibly wrong and what is simultaneously true. Multi-symptom defects are especially valuable because one mechanism may explain all symptoms.
2. **Eliminate stale-artifact explanations early.** Verify source ref, fresh build, served port/runtime and target environment before changing more code. Do not spend patch iterations on cache/build speculation once a fresh artifact has reproduced the bug.
3. **Map the ownership chain.** Trace the failing element through component ownership, DOM ancestry, CSS/layout/compositing ancestry, state ownership and execution/runtime boundaries as applicable.
4. **Look for an ancestor-level mechanism.** If a child-local fix should have worked but did not, inspect the nearest parent boundary that can dominate the child. Examples include CSS stacking contexts, opacity/transform/overflow, disabled/read-only wrappers, provider/context ownership, transaction/session fencing, task cancellation, container clipping and process environment.
5. **Prefer a cause that explains every major symptom at once.** A stronger hypothesis explains two or more observations with one mechanism. In the mobile popup incident, ancestor `opacity` explained both transparency and the inability of a huge child `z-index` to escape the parent stacking context.
6. **Run a discriminating patch, not a cosmetic patch.** Change the suspected governing mechanism with the smallest scope possible. Preserve behavior outside the failing boundary.
7. **Use failed patches as evidence.** A failed child-level patch proves that the problem is not fully controlled at that level; update the model before editing again.
8. **Verify in the environment that exhibited the bug.** Unit/DOM tests may prove event and rendering contracts but cannot prove browser compositor behavior, network timing, exchange semantics or device-specific layout. Keep a production-equivalent acceptance gate for those classes.
9. **Convert the lesson into a reusable guard.** Add a focused regression test where the mechanism is testable, and add the invariant/playbook entry when the final gate depends on a class of behavior the automated test environment cannot faithfully model.

### Diagnostic heuristic: symptom coupling

When two symptoms appear together, actively search for one shared upstream cause before treating them independently.

Examples:
- transparent **and** behind other UI → inspect ancestor opacity/compositing/stacking context before raising child z-index;
- correct request id **and** duplicate execution → inspect retry/ownership boundary before endpoint code;
- fresh code **and** stale behavior → inspect served process/port/artifact identity before rebuilding again;
- UI says permitted **and** backend rejects → inspect authority/risk/preflight contract before weakening backend checks;
- state updates **and** view remains stale → inspect memoization/subscription/ownership boundary before forcing re-render.

### Stop condition

Do not continue local patch stacking when a hypothesis has been falsified. Re-localize first. One failed well-chosen patch is often enough to justify moving one boundary upward; roughly three failed attempts still require a full architectural reassessment.

Apply `ASSISTANT_PROTOCOL.md` §8.3 immediately when its systemic-regression conditions arise; do not wait for
multiple failed fixes. Otherwise, roughly three failed attempts require stopping the patch loop and reassessing
architecture, assumptions and subsystem boundaries.

Keep rejected hypotheses as brief working evidence, not permanent authority. Never use trial-and-error patch
chains for execution, orders, risk, PnL or other money-sensitive paths. An obvious, proven local typo needs no
diagnostic ceremony. Central repository authority owns recovery, authorization and task completion.
