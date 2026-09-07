# BybitScanner — AUTOPILOT / PAPER Robot Design Research Workflow

Version: 1.0
Date: 2026-09-07
Status: ACTIVE / DESIGN-WORKFLOW
Implementation authorization: NONE

Purpose: define the temporary working method for near-term design of the PAPER robot and AUTOPILOT. This workflow governs design/research decisions only and does not authorize runtime implementation.

---

# 1. ONE SHORT DESIGN STEP AT A TIME

Work on one short, coherent design question at a time.

Do not expand into a broad architecture rewrite when the current question can be isolated. Closely related sub-decisions may be grouped when they share one theme and can be answered together without hiding dependencies.

---

# 2. REQUIRED ORDER FOR EACH DESIGN STEP

Before presenting options to the user:

1. inspect current authoritative/relevant BybitScanner GitHub documents and previously accepted decisions;
2. identify what is already planned, what remains open, and what must not be contradicted;
3. research how mature/open-source trading projects and frameworks solve the same or adjacent problem;
4. also inspect useful adjacent questions or safeguards not yet explicitly planned in BybitScanner when external implementations reveal them;
5. extract reusable design ideas rather than blindly copying another project's architecture or parameters;
6. present a short interactive multiple-choice test to the user.

External examples are evidence/input, not authority. Accepted BybitScanner architecture and user decisions remain project authority.

---

# 3. INTERACTIVE TEST FORMAT

Each design step should normally end with one concise choice block.

Preferred format:

- one concrete question;
- 2–5 materially different options (`A`, `B`, `C`, ...);
- a short implication/trade-off for each option;
- mark the assistant's recommended option when there is enough evidence;
- allow the user to choose one option, combine options, or modify an option.

Avoid long questionnaires. Finish one topic before moving to the next dependent topic.

---

# 4. DOCUMENTATION AFTER USER DECISION

After the user accepts or modifies one or more choices:

- document the accepted decision(s) on GitHub;
- group multiple accepted choices into one documentation update when they belong to the same theme;
- otherwise keep unrelated decisions separate;
- preserve `NEEDS VALIDATION` for unproven numeric thresholds or statistical assumptions;
- distinguish accepted architecture/risk invariants from research hypotheses;
- do not create runtime/code changes merely because a design decision was documented.

When safe targeted editing of a large existing document is unavailable, prefer a small authoritative design-note/addendum rather than risky full-file replacement; consolidate later when a safe patch path exists.

---

# 5. RESEARCH SOURCES / COMPARISON TARGETS

Research may include, depending on the question:

- QuantConnect LEAN;
- Freqtrade;
- Hummingbot;
- other credible open-source trading/risk/execution engines;
- exchange/API documentation where execution semantics matter;
- academic/industry portfolio-risk methods where appropriate.

For every borrowed idea, evaluate compatibility with BybitScanner constraints, including:

- USDT perpetuals;
- WV/РО model;
- PAPER-to-LIVE parity;
- fail-closed account/session/reconciliation semantics;
- no blind retry for mutations;
- account-neutral strategy logic;
- future multi-symbol and multi-account extensibility without forcing premature complexity.

---

# 6. NEAR-TERM SCOPE

This workflow is the default design method for PAPER robot and AUTOPILOT work for the near-term design phase until explicitly superseded.

It applies especially to:

- portfolio/risk admission;
- scanner-to-autopilot candidate lifecycle;
- prioritization and time-to-realization;
- position sizing and exposure;
- entry/retest/management/exit mechanics;
- failure/degraded-data behavior;
- diary/research telemetry;
- PAPER/LIVE execution parity;
- operational safeguards and state machines.

# END_OF_DOCUMENT
