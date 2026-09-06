# Debugging Playbook

Status: ACTIVE engineering guidance

Purpose: preserve reusable methods for resolving non-trivial blockers without accumulating speculative patches.

## Case study: mobile LIMIT popup rendered transparent and behind the terminal bar

### Observed failure

On the production preview in the mobile/narrow layout, the LIMIT confirmation popup was visible but appeared semi-transparent, visually behind the lower terminal/LIMITS layer and effectively inaccessible.

The failure reproduced on a fresh production build, so stale `dist`, browser cache and an old preview process could no longer be treated as the primary explanation.

### First hypothesis

The popup looked like a z-index/stacking problem. The first patch raised the mobile `ModePanel` and popup/backdrop z-index values and allowed overflow.

That patch built successfully and passed the existing focused tests, but the real production-preview acceptance still failed: the popup remained behind the lower layer.

### Why the failed patch was useful

The failed z-index patch falsified the idea that the popup's own stacking order was the complete cause. This was not a reason to keep increasing z-index values. It was evidence that an ancestor was controlling compositing.

The diagnosis therefore moved one level upward: from the popup itself to its owning mobile/read-only container.

### Root cause

The mobile read-only styling applied:

```css
.paper-market-actions.is-read-only {
  opacity: 0.52;
}
```

to the whole parent container that also owned the LIMIT popup.

That single ancestor-level rule explained both major symptoms:

1. The popup was semi-transparent because child opacity is composited with the ancestor.
2. `opacity < 1` creates a stacking context, so a very large child `z-index` cannot escape that ancestor stacking context and outrank unrelated sibling layers outside it.

This is why `z-index: 2147483647` on the child still did not solve the real-device/browser result.

### Correct fix

The fix removed opacity from the container that owns the modal layer and moved the read-only dimming to the ordinary controls only. The popup/backdrop was kept fully opaque and outside the dimming effect.

This preserved the intended visual semantics — disabled/read-only controls remain dimmed — without coupling modal compositing to the disabled-state presentation of the panel.

### Verification

The acceptance sequence was:

- fresh production build;
- fresh `preview:phone` process and explicit served port;
- open the exact production preview URL;
- reproduce the same LIMIT popup interaction without authorizing or creating a LIVE order;
- user confirmation that the popup was no longer transparent/behind the lower layer.

The real production-preview check was essential. DOM/unit tests can validate that a dialog exists, events fire and submission remains single-attempt, but JSDOM-style tests do not faithfully exercise browser compositor and mobile stacking behavior.

## Universal blocker-resolution method

Use the following method when an apparently reasonable fix does not resolve a blocker.

### 1. Establish observable facts

Write down the exact failure and environment. Separate facts from explanations.

Prefer coupled observations over vague labels. For example, "transparent and behind" is more diagnostic than "popup broken".

### 2. Eliminate stale-artifact uncertainty

Before editing again, verify the identity of what is actually running:

- repository ref/commit or branch;
- fresh build result;
- runtime/process identity;
- served port/URL;
- production-equivalent target environment.

Once a fresh artifact reproduces the defect, stop blaming cache/build unless new evidence appears.

### 3. Trace the ownership chain

Map the failing object from leaf to governing boundaries.

Depending on the subsystem, inspect:

- React/component ownership;
- DOM ancestry;
- CSS stacking/compositing/clipping ancestry;
- state/store/provider ownership;
- process environment;
- request/controller lifecycle;
- account/session/authority fences;
- execution/reconciliation ownership.

### 4. Form one falsifiable hypothesis

State what mechanism should explain the failure and what result would disprove it.

Avoid broad claims such as "CSS issue" or "race condition". Prefer mechanisms such as "ancestor opacity creates a stacking context that child z-index cannot escape".

### 5. Apply the smallest discriminating change

The next patch should test the hypothesis, not merely improve appearance.

Do not mix unrelated cleanup with the diagnostic delta.

### 6. Treat failure as information

If the patch fails under the same acceptance condition, do not stack another similar patch blindly.

Move exactly one governing boundary upward and update the mental model.

Examples:

- child z-index failed -> inspect parent stacking context/compositing;
- handler retry guard failed -> inspect command ownership/lifecycle;
- frontend validation failed -> inspect server authority/risk contract;
- rebuild failed to change behavior -> inspect process/port/artifact identity;
- forced rerender failed -> inspect subscription/state ownership.

### 7. Prefer a root cause that explains multiple symptoms

A strong diagnosis compresses observations.

One mechanism explaining two independent-looking symptoms is usually more credible than two ad-hoc explanations.

This is the "symptom coupling" heuristic.

### 8. Fix the governing mechanism, not the symptom

Once evidence identifies the parent mechanism, repair it at that boundary while preserving unrelated behavior.

Examples:

- move opacity from modal-owning container to individual disabled controls;
- keep risk limits server-authoritative instead of silently clamping frontend values;
- move mutation ownership into one controller instead of adding more retry flags;
- repair process/environment configuration instead of repeatedly rebuilding identical artifacts.

### 9. Verify at two levels

Use both where applicable:

1. cheap focused automated proof for contracts that the test environment can model;
2. production-equivalent acceptance for behavior that depends on real browser layout, device interaction, transport timing, exchange semantics or runtime environment.

Passing unit tests never overrides a reproduced failure in the authoritative target environment.

### 10. Distill the lesson

After resolving a meaningful blocker:

- record the rejected hypothesis if it teaches a reusable boundary lesson;
- add or strengthen a regression test where feasible;
- update the relevant skill/playbook with the invariant;
- avoid memorializing incidental implementation details as architecture.

## Compact mnemonic

Use:

**FACTS -> ARTIFACT -> OWNERSHIP -> HYPOTHESIS -> DISCRIMINATING PATCH -> ACCEPTANCE -> DISTILL**

Or in one sentence:

> Verify what is actually failing, find the boundary that owns the behavior, test one mechanism, let failed fixes move the diagnosis upward, then fix the governing cause and verify it where the bug really exists.
