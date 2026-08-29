---
name: proof-before-done
description: Require current, claim-matched evidence before declaring BybitScanner work fixed, complete, accepted, regression-safe, or production-ready; use before material completion claims.
---

# Proof Before Done

Use the existing verifier and project acceptance rules; this skill interprets evidence and does not replace either.

1. Define each material claim before checking it: for example, source compiles, a regression passes, the production bundle builds, UI behavior is manually accepted, or a money-sensitive invariant is preserved.
2. Map each claim to the minimum sufficient current evidence. Do not run checks that protect no intended claim.
3. Run `python -m tools.dev.verify` once with exact task/changed paths as required by root `AGENTS.md`. Report only the checks it actually ran; its PASS does not imply checks absent from its output.
4. Add broader evidence only when the risk or acceptance surface requires it. Stop when every intended claim has sufficient evidence.

| Claim | Minimum evidence |
| --- | --- |
| Syntax/import or routed source correctness | Applicable compile, type, lint, or exact-path verifier result |
| Critical deterministic behavior | Focused regression exercising the real invariant |
| Frontend production bundle is valid | Current `npm run build` PASS |
| Visual, touch, browser, or device behavior is correct | Current manual acceptance in the required real environment |
| Safe checkpoint | Current verifier PASS receipt plus the user-run checkpoint workflow |

Automated PASS is not visual correctness, live-data correctness, production-preview correctness, or browser/real-phone acceptance. Keep those states `NOT YET ACCEPTED` until the required environment supplies fresh evidence.

For Trading Workspace source changes under `terminal/frontend/src` that will be accepted through `vite preview`, preserve the authoritative sequence: targeted/source checks → `npm run build` PASS → reload the running preview → manual browser or real-phone acceptance. A stale build or acceptance performed before rebuild and reload is not evidence for the current source.

Evidence becomes stale after a material change to the relevant files, diff, runtime, or acceptance environment. The checkpoint workflow independently validates receipt branch, HEAD, path, and content freshness; do not bypass it.

If a required check fails, report the failure and partial successes without claiming completion. When the cause is unknown, use `systematic-debugging`. For execution, orders, risk, PnL, sizing, reconciliation, persistence, or robot control, expand verification as needed for confidence; token economy never lowers the safety bar.
