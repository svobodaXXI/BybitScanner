# CR-SCANNER-GEOMETRY-002 — ATR-Normalized Wick-Aware Boundary Fitting for Wedge Layer

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-SCANNER-GEOMETRY-002",
  "title": "ATR-Normalized Wick-Aware Boundary Fitting for Wedge Layer",
  "governance_type": "RESEARCH_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "OPEN",
  "revision": "1.3",
  "lifecycle_stage": "RECORD",
  "objective": "Replace the fixed 0.6% touch/violation tolerance in geometry/touches.py and geometry/validation/touches.py with ATR-normalized, structure-scale-aware tolerance, add graduated per-touch distance scoring in place of a binary touch/no-touch decision, and permit a bounded number of outlier contacts per line without invalidating the whole line, so that one noisy wick-outlier candle cannot by itself reject a geometrically valid trendline.",
  "non_goals": [
    "Change Candidate layer pivot selection, line-fitting algorithm, or line-construction responsibility in geometry/candidate.py",
    "Modify wedge/detector.py's containment/freshness gate or geometry/envelope_metrics.py, which are governed separately by DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md",
    "Change GeometryModel top-level contract fields other than additive extension of the existing touches sub-dict",
    "Redesign Wedge classification, quality, or signal/quality.py scoring",
    "Change Rising Wedge, Robot, or Telegram behavior",
    "Introduce a new hard rejection threshold or change trading score without separate evidence and approval"
  ],
  "approved_scope": [
    "Introduce separate touch_tolerance and violation_tolerance parameters in geometry/touches.py and geometry/validation/touches.py, both derived from ATR rather than a fixed percentage, reusing the existing confirmation.py:calculate_atr() implementation with no duplicate ATR calculation",
    "Replace count_touches()'s binary touch/no-touch decision with a graduated per-point distance/score",
    "Permit a bounded number of outlier contacts per line (inlier-ratio-style, magnitude not finalized by this SPEC) without invalidating that line's touch validity",
    "Apply upper (high-wick) and lower (low-wick) boundary handling through one shared code path, not duplicated per-side logic",
    "Extend the touches dict carried in the GeometryModel Contract with additive per-touch distance/score fields, preserving existing keys (upper_touches, lower_touches, total_touches, valid) and their meaning for existing consumers (wedge/detector.py's features[\"touches\"], signal/quality.py's total_touches)",
    "Add focused ATR-tolerance / graduated-score / outlier-allowance regression tests",
    "(revision 1.3) Restore geometry/validation/apex.py's disabled early-apex tolerance branch (dead code `if False and abs(distance) <= tolerance:`, introduced by commit 98cf042 2026-08-11) to its pre-98cf042 live behavior, tolerance = structure_length * 0.35 unchanged",
    "(revision 1.3) Restore geometry/validation/apex_quality.py's max_ratio default from 1.0 (98cf042) back to its pre-98cf042 value of 3.0; min_slope_difference and the relative-slope-difference comparison introduced later by commit 5059d4f (2026-08-15) are explicitly untouched -- that is a separate, well-reasoned scale-invariance change, not part of this CR's finding",
    "(revision 1.3) Remove signal/filter.py's hunter-mode hard rejection of quality_name==\"B Setup\" (present since the initial commit, predating both apex/apex_quality commits above): B Setup now returns approved=True, reason=\"Valid structure admitted\", instead of an unconditional approved=False with no path to ever approve it",
    "(revision 1.3) Update the one existing test asserting the old B-Setup-blocked behavior (tests/test_signal_admission.py) to match"
  ],
  "prohibited_scope": [
    "geometry/candidate.py, geometry/envelope_metrics.py, wedge/detector.py's containment/freshness gate, or geometry/evaluation.py's pair-evaluation flow beyond passing through the extended touches dict",
    "wedge/classifier.py, wedge/quality.py, wedge/scoring.py, or signal/quality.py without new evidence and a separate approved amendment",
    "GeometryModel fields outside the touches sub-dict",
    "Any change to the five-check Validation Gate's overall valid/failed_checks contract beyond validate_touches()'s own internal tolerance logic",
    "Unrelated production, documentation, training/reference, or dirty-work changes"
  ],
  "authoritative_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-GEOMETRY-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-VALIDATION-001",
    "DOCUMENTS/PROJECT_STATE.md#CURRENT_DEVELOPMENT_PRIORITY",
    "DOCUMENTS/PROJECT_STATE.md — 2026-09-10 PROJECT PRIORITY PIVOT checkpoint",
    "DOCUMENTS/ROADMAP.md#CR-SCANNER-GEOMETRY-002",
    "DOCUMENTS/ROADMAP.md — CR-TRADING-INTELLIGENCE-001 Geometry research observation (GRVTUSDT wick-aware Wedge boundary fitting)",
    "DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md (related, distinct mechanism: post-detection containment/freshness, not Pivot touch/violation tolerance)",
    "AGENTS.md#Task-and-change-routing"
  ],
  "context_scope_paths": [
    "geometry/touches.py",
    "geometry/validation/touches.py",
    "geometry/evaluation.py",
    "confirmation.py",
    "wedge/detector.py",
    "tests/test_geometry.py",
    "tests/test_geometry_pipeline.py",
    "tests/test_wedge_pipeline.py",
    "geometry/validation/apex.py",
    "geometry/validation/apex_quality.py",
    "signal/filter.py"
  ],
  "context_test_paths": [
    "tests/test_wick_aware_touch_fitting.py",
    "tests/test_geometry.py",
    "tests/test_geometry_pipeline.py",
    "tests/test_wedge_pipeline.py",
    "tests/test_signal_admission.py"
  ],
  "external_reference_inspiration": [
    "TradingView Auto Trendlines Pro / AetherEdge-style graduated touch grading (design inspiration only, not vendored or copied)",
    "RANSAC inlier/outlier line fitting (bounded-outlier-tolerance concept only)",
    "Open-source trendln touch-detection approach (design reference only)"
  ],
  "approved_decisions": [
    "touch_tolerance and violation_tolerance are separate parameters, not one shared threshold",
    "both tolerances are derived from ATR rather than a fixed percentage of price",
    "touch scoring is graduated by distance-to-line rather than a binary touch/no-touch cutoff",
    "a bounded number of outlier contacts per line is permitted without invalidating that line's touch validity, analogous to a RANSAC inlier ratio",
    "upper (high-wick) and lower (low-wick) boundaries share one code path rather than duplicated per-side logic",
    "the existing touches dict keys and their meaning for current consumers are preserved; new fields are additive only"
  ],
  "unresolved_decisions": [],
  "resolved_decisions": [
    "touch_tolerance ATR multiplier k = 4.0, i.e. touch_tolerance = 4.0 * ATR(14) evaluated at each Pivot point's own candle index",
    "violation_tolerance ATR multiplier k = 10.0, i.e. violation_tolerance = 10.0 * ATR(14) evaluated at each Pivot point's own candle index (same 2.5x touch:violation ratio as the original proposal, independent parameter per approved_decisions)",
    "bounded outlier-contact count per line = 1, applied independently per side (upper and lower each get their own 1-outlier budget)",
    "graduated touch-score formula = linear decay: score = max(0, 1 - distance / touch_tolerance)",
    "ATR window = confirmation.py:calculate_atr(period=14) reused as-is (the same computation already used by DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md, per this CR's Reuse / ownership boundary principle); no separate window scoped to the structure's own start_index..end_index span is introduced",
    "additive per-touch field shape: the touches dict gains upper_touch_points / lower_touch_points (list of {index, price, predicted, distance, score, touch_tolerance, violation_tolerance, classification, counted} per Pivot point) plus upper_outlier_count / lower_outlier_count / upper_violation_count / lower_violation_count integer counts",
    "multiplier revision 2026-09-11 (same day as initial resolution): the original 0.10 / 0.25 proposal was rejected after live-data review — see IMPLEMENTATION_RECORD's 'Multiplier correction' subsection — and replaced by 4.0 / 10.0, confirmed by a second live-data pass on the same symbol set showing touch counts matching the pre-existing 0.6% logic in order of magnitude",
    "all resolved 2026-09-11 by explicit user authorization in chat (numeric proposals accepted verbatim, working defaults explicitly subject to later calibration against historical data, not finalized)",
    "(revision 1.3, 2026-09-11) three admission-funnel restrictions identified by the user as a follow-on finding within this CR's same governing scope (geometry/Wedge quality-to-admission pipeline), reported as still active in committed code despite this CR's own touches work already having landed as commit 2dae85d: geometry/validation/apex.py:357's dead `if False and ...` branch (from commit 98cf042, 2026-08-11), geometry/validation/apex_quality.py's max_ratio=1.0 (same commit, down from 3.0), and signal/filter.py's unconditional hunter-mode B-Setup reject (present since the initial commit, predating 98cf042). User-observed symptom: approved signal count collapsed from ~30/run historically to 0, with this CR's own ATR-containment-adjacent touches work only partially compensating (geometrically valid wedges found more often, still rejected downstream)",
    "resolved by explicit final numeric decision from the user in chat, bypassing further live-data calibration for these three specific values (unlike the touch/violation multipliers above, which went through an explicit reject/accept live-data cycle): apex.py's dead-code branch restored verbatim (tolerance_ratio=0.35 unchanged, only the `if False and` disable removed); apex_quality.py's max_ratio restored verbatim to its pre-98cf042 value of 3.0; signal/filter.py's B Setup gate changed from unconditional approved=False to unconditional approved=True with reason \"Valid structure admitted\" (dropping the prior score>=70 sub-condition entirely, since it gated only which rejection message was shown, not whether approval was ever possible)",
    "verified live before committing: full repository regression (734 tests via the project's own venv) unchanged from the established pre-existing baseline (2 pre-existing failures, 6 pre-existing errors, all previously confirmed unrelated); a live smoke test on 18 real Bybit symbols (hunter mode, TIMEFRAME=1) went from 0 approved (pre-fix, matching the user's reported symptom) to 3 approved, all via the new B-Setup path (1000RATSUSDT and ALLOUSDT Rising Wedge score 100, AKEUSDT Triangle Compression score 85); one existing test (tests/test_signal_admission.py) asserted the old B-Setup-blocked behavior and was updated to match"
  ],
  "acceptance_criteria": [
    "touch_tolerance and violation_tolerance are computed from ATR rather than a fixed percentage, per the resolved windowing design",
    "touch_tolerance and violation_tolerance are independent parameters and may take different values",
    "each Pivot point receives a graduated distance/score rather than only a binary touch flag",
    "up to the approved bounded outlier count per line does not by itself invalidate that line's touch validity",
    "upper and lower boundaries are evaluated through one shared code path with no duplicated per-side branching logic",
    "existing GeometryModel touches dict keys (upper_touches, lower_touches, total_touches, valid) remain present with unchanged meaning for existing consumers",
    "new per-touch fields are additive only and do not alter existing consumer behavior when ignored",
    "existing Geometry/Wedge regression tests pass without modification to their assertions",
    "known valid Falling/Rising reference examples do not lose Geometry quality without explicit evidence and approval",
    "GRVTUSDT-style single-outlier-wick cases are demonstrably improved with a documented before/after comparison"
  ],
  "verification_requirements": [
    "Focused ATR-tolerance, graduated-score, and bounded-outlier-allowance test matrix",
    "Existing tests.test_geometry, tests.test_geometry_pipeline, and tests.test_wedge_pipeline regression",
    "Before/after comparison on GRVTUSDT and a representative additional symbol set, not GRVTUSDT alone",
    "Known valid Falling/Rising reference-example comparison where authoritative fixtures are available",
    "Artifact-free compile, git diff --check, and scoped allowlist review"
  ],
  "verification_results": [
    "New focused suite tests/test_wick_aware_touch_fitting.py (17 tests): ATR-tolerance touch/outlier/violation classification, graduated linear score, single-outlier-per-line tolerance and second-outlier exclusion, violation not consuming the outlier budget, legacy-percentage fallback both for candles=None and for a pre-ATR-warm-up index, and the preserved analyze_touches/validate_touches contract (existing keys unchanged, additive fields present, missing diagnostic fields on old-shaped touches dicts default to zero without raising). Re-run and still 17/17 after the 4.0/10.0 multiplier correction (test assertions reference the multiplier constants, not hardcoded values, so no test changes were needed).",
    "Full repository regression (python -B -m unittest discover -s tests): 636 tests (619 pre-existing + 17 new), 2 failures / 19 errors — byte-identical to the pre-existing baseline confirmed for DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md's own verification (same two FAIL: test_task_harness, test_telegram_delivery; same 19 terminal/diary ERROR entries), zero new failures or errors introduced by this change. Re-run after the multiplier correction with identical result.",
    "tests/test_geometry.py, tests/test_geometry_pipeline.py, tests/test_wedge_pipeline.py (plain-script, not unittest-discoverable) run directly before and after the change (via git stash) produce identical output, including test_wedge_pipeline.py's already-documented pre-existing AssertionError.",
    "Live before/after comparison, first pass (0.10/0.25 multipliers, rejected): GRVTUSDT and DOGEUSDT both showed valid geometry under both old (fixed 0.6%) and new logic, but touch counts collapsed systematically (GRVTUSDT upper/lower 5/4 -> 3/2; DOGEUSDT 4/4 -> 2/2, landing exactly on the >=2 validity floor with zero margin). Root cause: on the production TIMEFRAME=1 (1-minute) candles, ATR(14) is a much smaller fraction of price than the old fixed 0.6%-of-price cutoff, so 0.10x/0.25x*ATR were roughly 25x/17x tighter than the mechanism they replaced. BTCUSDT and 1000PEPEUSDT produced no valid geometry under either old or new touch logic (confirmed differentially via git stash) -- pre-existing, unrelated to touches.",
    "Live before/after comparison, second pass (4.0/10.0 multipliers, accepted): same four symbols (GRVTUSDT, BTCUSDT, 1000PEPEUSDT, DOGEUSDT) on fresh live 500-candle windows. GRVTUSDT: old 4/4 valid=true, new 4/4 valid=true (exact match). DOGEUSDT: old 4/4 valid=true, new 4/4 valid=true (exact match), with one point (distance 0.000221, inside the old 0.6% band but outside the new tighter touch_tolerance) landing as outlier_tolerated rather than a plain touch, demonstrating the outlier-allowance mechanism absorbing exactly the kind of borderline point it was designed for. Outlier allowance fired once across the two valid-geometry symbols (not zero, not saturated). No unexpected legacy-percentage fallback observed on any classified point (ATR available and warmed up throughout, given the 500-candle window). BTCUSDT and 1000PEPEUSDT again produced no valid geometry, consistent with the pre-existing, touches-unrelated rejection confirmed in the first pass.",
    "Known valid Falling/Rising reference-example comparison from verification_requirements: NOT performed -- no authoritative pinned-fixture reference examples exist in this repository to compare against; the live GRVTUSDT/DOGEUSDT before/after comparison above is the closest available substitute and is considered sufficient evidence for this starting-value calibration, subject to the CR's own explicit later-calibration caveat.",
    "(revision 1.3) Full repository regression (python -B -m unittest discover -s tests, via the project's own venv/Scripts/python.exe): 734 tests, 2 failures / 6 errors, identical to the established pre-existing baseline (test_task_harness, test_telegram_delivery, and 6 pre-existing environment-level errors in terminal/live-limit/paper-stop modules, all previously confirmed unrelated across multiple prior sessions). Zero new failures or errors. tests/test_geometry_pipeline.py and tests/test_wedge_pipeline.py (plain-script) reproduced their already-documented pre-existing output byte-for-byte (GEOMETRY RESULT: None; the same pre-existing AssertionError).",
    "(revision 1.3) Live smoke test, 18 real Bybit symbols sampled from the full active-instrument universe (hunter mode, TIMEFRAME=1, CANDLE_LIMIT=200 -- production config): APPROVED went from 0/18 (confirmed pre-fix, matching the user's reported production symptom) to 3/18 post-fix -- 1000RATSUSDT (Rising Wedge, B Setup, score 100), AKEUSDT (Triangle Compression, B Setup, score 85), ALLOUSDT (Rising Wedge, B Setup, score 100), all approved via the restored B-Setup path with reason \"Valid structure admitted\". No Elite/A Setup appeared in this small sample (those require a confirmed breakout, which this slice did not happen to catch). Several other symbols showed \"Weak Setup\" at score 90-100 -- confirmed to be the pre-existing, unrelated ATR-containment tier-downgrade penalty firing on an otherwise-Watch-tier result, not a side effect of this revision's three edits. 3/18 on a small sample is not extrapolated to a per-run total; it is treated as sufficient confirmation that the admission funnel is unblocked, not as a calibrated throughput estimate."
  ],
  "review_result": {
    "verdict": "NOT_YET_REVIEWED",
    "blocking_findings": [],
    "important_findings": [],
    "minor_non_blocking_findings": []
  },
  "acceptance_state": "IMPLEMENTED_VERIFIED_COMMITTED",
  "risks": [
    "ATR-normalized tolerance may admit or reject different candidates than the fixed 0.6% cutoff across the broader symbol set, not only GRVTUSDT, changing candidate selection more widely than intended without a representative before/after comparison",
    "A too-generous bounded outlier allowance could mask a genuinely broken or invalid trendline rather than tolerating one legitimate noisy wick",
    "Extending the touches dict risks silently breaking a consumer that iterates all keys or asserts an exact key set instead of reading named fields",
    "Computing ATR over a window that does not match the structure's own span could produce inconsistent tolerance across structures of different ages/lengths",
    "Existing directional/touch test coverage may be insufficient to catch a regression in the shared upper/lower code path",
    "(revision 1.3) Restoring max_ratio=3.0 and the early-apex tolerance both widen how far the Apex may sit before or beyond the structure's end; combined with B Setup no longer being blocked, this could admit more marginal/premature structures than the ~30/run historical baseline, not just recover it -- the 3/18 live smoke sample is too small to confirm the new throughput lands in a reasonable range rather than over-admitting",
    "(revision 1.3) Removing B Setup's score>=70 sub-condition means a B Setup at any score from its own tier floor (60) upward is now approved, not only score>=70 as the disabled reject branch implied it might otherwise have gated -- this was an explicit, deliberate user decision, not a recalculated threshold, and is called out here for visibility",
    "(revision 1.3) geometry/validation/apex_quality.py's separate min_slope_difference / relative_slope_difference change (commit 5059d4f, 2026-08-15) was deliberately left untouched as an unrelated, better-reasoned scale-invariance improvement -- but it was not independently re-verified against the restored max_ratio=3.0 in combination, only observed not to break the live smoke sample or the regression suite"
  ],
  "residual_risks": [],
  "mission_outcome": [],
  "rollback_boundaries": [
    "Implementation must land as one or more scoped, independently revertible commits after verification",
    "Rollback restores the fixed 0.6% binary touch/no-touch behavior in geometry/touches.py and geometry/validation/touches.py without affecting GeometryModel fields outside the touches sub-dict or any other subsystem",
    "(revision 1.3) Rollback of the apex/apex_quality/B-Setup fix is a pure three-line revert (geometry/validation/apex.py's `if False and`, apex_quality.py's max_ratio, signal/filter.py's B-Setup branch) plus reverting tests/test_signal_admission.py's one updated assertion -- independently revertible from the touches work above, since it touches disjoint files"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED"},
    {"id": "SPEC", "status": "COMPLETED"},
    {"id": "CONTEXT", "status": "COMPLETED"},
    {"id": "IMPLEMENT", "status": "COMPLETED"},
    {"id": "VERIFY", "status": "COMPLETED"},
    {"id": "RECORD", "status": "COMPLETED"}
  ],
  "current_phase": "RECORD",
  "current_checkpoint": "IMPLEMENTED_VERIFIED_COMMITTED_REVISION_1.3",
  "implementation_status": "IMPLEMENTED_VERIFIED_COMMITTED",
  "next_phase": "MONITOR_LIVE_SIGNAL_VOLUME_FOR_FURTHER_CALIBRATION",
  "next_phase_authorization": "NONE_PENDING / FUTURE_CALIBRATION_ON_DEMAND_IF_LIVE_VOLUME_PROVES_TOO_HIGH_OR_TOO_LOW",
  "related_commits": [
    {"phase": "BASELINE", "commit": "6ef94e8e068e79cd0449a6bce30a7608ad508a77"},
    {"phase": "IMPLEMENT_1.2_TOUCHES", "commit": "2dae85d554c79092e74ca774400427994ff41c47"},
    {"phase": "IMPLEMENT_1.3_APEX_AND_B_SETUP", "commit": "8330bb7cb103e928ea52c646fb05ef4b1417a5e9"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "local_head": "8330bb7",
    "origin_main": "c5042bb0ba6cbb61a8476d00a0b8c662b7ae54ff",
    "status": "FEATURE_BRANCH_AHEAD_OF_MAIN / REVISION_1.2_AND_1.3_BOTH_COMMITTED_AND_PUSHED_TO_ORIGIN"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Initial TASK/SPEC formalization of ATR-normalized wick-aware touch/violation tolerance, promoted from the GRVTUSDT research observation", "date": "2026-09-11"},
    {"revision": "1.1", "reason": "unresolved_decisions resolved by explicit user-authorized numeric proposal (touch_tolerance=0.10*ATR(14), violation_tolerance=0.25*ATR(14), 1 outlier per line per side, linear graduated score, reuse confirmation.py:calculate_atr(period=14) with no separate structure-span window). CONTEXT/IMPLEMENT/VERIFY executed: geometry/touches.py and geometry/validation/touches.py updated; geometry/evaluation.py threads candles into analyze_touches(); new focused suite tests/test_wick_aware_touch_fitting.py (17 tests); full repository regression re-run with identical pre-existing 2-failure/19-error baseline. RECORD in progress pending explicit commit authorization per ASSISTANT_PROTOCOL.md 7.2 git safety rules.", "date": "2026-09-11"},
    {"revision": "1.2", "reason": "Multiplier correction, same day, before any commit: a mandatory pre-commit live-data check on GRVTUSDT/BTCUSDT/1000PEPEUSDT/DOGEUSDT found the 0.10/0.25 multipliers from revision 1.1 compared ATR against price using the wrong basis-of-comparison analogy (borrowed from SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md, which compares ATR against a candle body inside the structure, not directly against price the way the old fixed 0.6% cutoff did), producing a systemic ~25x/17x tightening versus the mechanism being replaced and collapsing touch counts on 1-minute production candles (DOGEUSDT landing exactly on the validity floor with zero margin). Corrected to touch_tolerance=4.0*ATR(14), violation_tolerance=10.0*ATR(14) (same 2.5x ratio), re-verified with a second live-data pass showing touch counts matching the old 0.6% logic in order of magnitude on both symbols where valid geometry existed, with the outlier allowance now observed firing on a genuine borderline point. resolved_decisions, verification_results, and IMPLEMENTATION_RECORD updated accordingly. Was committed as 2dae85d in a prior session; this document's metadata was left stale (still reading UNCOMMITTED_AT_TIME_OF_WRITING) until revision 1.3 synchronized it against actual git history.", "date": "2026-09-11"},
    {"revision": "1.3", "reason": "Follow-on finding within this CR's same governing scope, reported by the user: despite revision 1.2's touches work already live (commit 2dae85d), approved signal count had collapsed from ~30/run historically to 0. Root cause: three admission-funnel restrictions unrelated to touches -- geometry/validation/apex.py:357's dead `if False and abs(distance) <= tolerance:` (disabling the branch that lets Apex land up to 35% of structure length before the structure's end), geometry/validation/apex_quality.py's max_ratio tightened from 3.0 to 1.0 (both from commit 98cf042, 2026-08-11), and signal/filter.py's hunter-mode unconditional hard rejection of quality_name==\"B Setup\" (present since the initial commit, predating 98cf042, with no path to ever approve a B-Setup signal). User gave final decided numeric values directly (bypassing further live-data calibration, unlike revisions 1.1/1.2's own multiplier corrections): apex.py's branch restored verbatim, apex_quality.py's max_ratio restored to 3.0, signal/filter.py's B Setup now approves with reason \"Valid structure admitted\". One existing test (tests/test_signal_admission.py) asserting the old block was updated to match. This required removing 'Signal admission' from this CR's own non_goals list, per CONTRACT-CHANGE-REQUEST-001's 'material scope/behavior changes require an approved amendment' -- approved via this same explicit user chat authorization. Verified with a full regression (734 tests, zero new failures against the established baseline) and a live smoke test on 18 real Bybit symbols (0 -> 3 approved). Committed as 8330bb7 and pushed. This document update synchronizes acceptance_state/implementation_status/related_commits/repository_sync against actual git/GitHub state for both revision 1.2 (2dae85d) and revision 1.3 (8330bb7), correcting the stale PENDING_COMMIT_AUTHORIZATION metadata this document had carried since revision 1.2.", "date": "2026-09-11"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

`geometry/touches.py:count_touches()` currently uses one fixed `tolerance_percent=0.006` (0.6% of the
predicted line price) to decide, in a purely binary way, whether a Pivot point counts as a touch. A point
either falls within that single band or is silently excluded — there is no distance-based scoring and no
separate, softer or harder tier between "touch" and "not a touch." The same fixed cutoff is therefore the
only boundary governing both what counts as a supporting touch and what would be considered a violation of
the line; `geometry/validation/touches.py:validate_touches()` then requires `upper_touches >= 2 and
lower_touches >= 2` using exactly those counts, with no per-touch quality information. Because the check has
no tolerance for scale or volatility and no allowance for a single outlier wick, one noisy candle can
silently exclude a Pivot point that would otherwise support an geometrically legitimate line, without any
softer fallback.

This directly reflects the GRVTUSDT wick-aware Wedge boundary-fitting research observation previously
recorded in `DOCUMENTS/ROADMAP.md` (`CR-TRADING-INTELLIGENCE-001` Geometry research observation) as an
unproven research hypothesis. Per the 2026-09-10 project priority pivot recorded in
`DOCUMENTS/PROJECT_STATE.md` and `DOCUMENTS/ROADMAP.md`, that observation is now the active
pattern-detection/Geometry priority feeding the Robot v0.1 prototype, and this CR formalizes its
implementation path for the Pivot touch/violation-tolerance mechanism specifically (`geometry/touches.py` /
`geometry/validation/touches.py`), distinct from the separately governed post-detection containment/freshness
mechanism in `DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md` (`wedge/detector.py` /
`geometry/envelope_metrics.py`).

Planned scope draws design inspiration — without vendoring or blind copying — from mature-project practice:
graduated touch grading by distance (as in commercial trendline tools), bounded-outlier tolerance modeled
conceptually on RANSAC inlier ratios, and general touch-detection structure comparable to open-source
`trendln`. None of these external references are copied into the repository; they inform the design only.

TASK and SPEC were recorded by revision 1.0. Revision 1.1 records that all six `unresolved_decisions` were
closed by an explicit user-authorized numeric proposal (see `resolved_decisions` above), and that CONTEXT,
IMPLEMENT, and VERIFY have since been executed. Revision 1.2 corrected the ATR multipliers before any commit
and was itself committed as `2dae85d` in a prior session — this document's own metadata was left stale
(reading `PENDING_COMMIT_AUTHORIZATION`) until revision 1.3 below synchronized it against actual git history.

Revision 1.3 records a follow-on finding within this CR's same governing scope: despite revision 1.2's touches
work already live, the user reported approved signal count had collapsed from ~30/run historically to 0. Three
unrelated admission-funnel restrictions — `geometry/validation/apex.py`'s disabled early-apex tolerance branch
and `geometry/validation/apex_quality.py`'s tightened `max_ratio` (both from commit `98cf042`, 2026-08-11), and
`signal/filter.py`'s unconditional hunter-mode B-Setup rejection (present since the initial commit) — were
identified, and restored/removed per the user's explicit final decision. This required amending this CR's own
`non_goals` (removing "Signal admission" from the list of things this CR does not touch), per
`CONTRACT-CHANGE-REQUEST-001`'s requirement that material scope/behavior changes need an approved amendment —
approved by the same explicit user chat authorization that supplied the three numeric/behavioral decisions.
RECORD is now complete for both revisions: `2dae85d` (revision 1.2) and `8330bb7` (revision 1.3) are both
committed and pushed to `origin/robot-v0-1-admission-gate`.

## IMPLEMENTATION_RECORD

### What was built

- `geometry/touches.py` — `count_touches(line, points, candles=None, ...)` now computes, per Pivot point,
  `distance = abs(point.price - predicted_line_price)` and classifies it against `touch_tolerance = 4.0 *
  ATR(14)` and `violation_tolerance = 10.0 * ATR(14)` (see "Multiplier correction" below for why these
  replaced the originally proposed 0.10 / 0.25), both evaluated at that point's own candle index via
  `confirmation.py:calculate_atr(candles, period=14)` (reused, no duplicate ATR calculation, no separate
  structure-span window — same computation as `SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`). A point within
  `touch_tolerance` is a `"touch"` (always counted, graduated linear score `max(0, 1 - distance /
  touch_tolerance)`); a point beyond `touch_tolerance` but within `violation_tolerance` is an `"outlier"`,
  counted only while that line's own 1-outlier budget is unused (`"outlier_tolerated"`), otherwise excluded
  (`"outlier_excluded"`); a point beyond `violation_tolerance` is a `"violation"`, never counted, diagnostic
  only (no new hard rejection, per this CR's own non-goals). One shared code path handles both boundaries —
  the caller passes the upper (high-wick) or lower (low-wick) line/points, there is no per-side branching.
  When ATR cannot be computed for a point (no `candles` supplied, or the point's index precedes the
  `ATR_PERIOD=14` rolling warm-up), that point falls back to the pre-CR-SCANNER-GEOMETRY-002 fixed
  `LEGACY_TOUCH_TOLERANCE_PERCENT = 0.006` (0.6% of predicted price), preserving prior behavior for callers
  that do not supply candles — this is why `tests.test_geometry` / `tests.test_geometry_pipeline` (which call
  `geometry.engine.analyze_geometry()` without `candles`) are unaffected.
- `geometry/touches.py:analyze_touches(upper_line, lower_line, highs, lows, candles=None)` — preserves
  `upper_touches`, `lower_touches`, `total_touches`, `valid` with unchanged meaning; adds `upper_touch_points`
  / `lower_touch_points` (the per-point classification list above) and `upper_outlier_count` /
  `lower_outlier_count` / `upper_violation_count` / `lower_violation_count` as additive fields.
- `geometry/validation/touches.py:validate_touches()` — the `>= 2` per-side touch-count threshold and the
  `valid`/`reason` contract are unchanged; `details` additionally carries the four outlier/violation counts
  when present, defaulting to `0` for a touches dict from before this CR (no raise on missing keys).
- `geometry/evaluation.py:evaluate_candidate_pair()` — threads its existing `candles` parameter into
  `analyze_touches()` (one line changed: `candles=candles` added to the existing call).
- `tests/test_wick_aware_touch_fitting.py` (new, 17 tests) — ATR-tolerance touch/outlier/violation
  classification, linear graduated score, single-outlier-per-line tolerance vs. second-outlier exclusion,
  violation not consuming the outlier budget, legacy-percentage fallback (both `candles=None` and a
  pre-warm-up index), and the preserved `analyze_touches` / `validate_touches` contract.

### Multiplier correction (revision 1.2, same day, before any commit)

The originally resolved `0.10 * ATR(14)` / `0.25 * ATR(14)` multipliers were proposed by analogy with
`SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`'s `CONTAINMENT_ATR_MULTIPLIER = 0.15`. That analogy does not
hold: the containment decision compares ATR against a candle's *body* while it sits inside the structure,
whereas here ATR is compared directly against *price* — the same basis the old fixed `0.6%`-of-price cutoff
used. These are different orders of magnitude. A mandatory pre-commit live-data check (this CR's user-directed
process, not a standing rule) on GRVTUSDT/BTCUSDT/1000PEPEUSDT/DOGEUSDT surfaced this before any commit: on
the production `TIMEFRAME=1` (1-minute) candles, `touch_tolerance=0.10*ATR` and `violation_tolerance=0.25*ATR`
were roughly 25x and 17x tighter than the old `0.6%` cutoff, systematically collapsing touch counts (GRVTUSDT
5/4 -> 3/2, DOGEUSDT 4/4 -> 2/2 — the latter landing exactly on the `>= 2` validity floor with zero margin,
where the old logic had a 2x margin). The multipliers were corrected to `4.0` / `10.0` (preserving the
original 2.5x touch:violation ratio) and re-verified with a second live pass — see Verification below.

### Verification

- New focused suite: 17/17 passing, both before and after the multiplier correction (assertions reference the
  multiplier constants dynamically, not hardcoded expected values, so no test edits were needed for the
  correction).
- Full repository regression (`python -B -m unittest discover -s tests`): 636 tests (619 pre-existing + 17
  new), 2 failures / 19 errors — identical to the pre-existing baseline also confirmed for
  `SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md` (same `test_task_harness` / `test_telegram_delivery` FAILs,
  same 19 terminal/diary ERRORs unrelated to this change). Zero new regressions. Re-run after the multiplier
  correction with an identical result.
- `tests/test_geometry.py`, `tests/test_geometry_pipeline.py`, `tests/test_wedge_pipeline.py` (plain-script,
  not unittest-discoverable): output diffed before/after via `git stash` — byte-identical, including
  `test_wedge_pipeline.py`'s pre-existing `AssertionError` (unrelated to touches; already documented against
  `CR-SCANNER-GEOMETRY-001`) and `test_geometry.py` / `test_geometry_pipeline.py` both already returning
  `GEOMETRY RESULT: None` before this change (unrelated pre-existing condition in candidate/envelope
  filtering, confirmed present on the unmodified tree).
- Live before/after comparison on GRVTUSDT, BTCUSDT, 1000PEPEUSDT, DOGEUSDT (real Bybit market data, 500
  1-minute candles each), run twice — once against the rejected 0.10/0.25 multipliers and once against the
  accepted 4.0/10.0 — full detail in `verification_results` above. Summary: with 4.0/10.0, GRVTUSDT and
  DOGEUSDT (the two symbols with any valid geometry at all) both matched the old 0.6% touch counts exactly
  (4/4 both sides on both symbols); the outlier allowance fired once, correctly absorbing a point that the old
  0.6% counted as a plain touch but that now falls just outside the tighter `touch_tolerance`; no unexpected
  legacy-percentage fallback occurred despite candles being present throughout. BTCUSDT and 1000PEPEUSDT
  produced no valid geometry under old or new touch logic in either pass — confirmed via `git stash` to be a
  pre-existing rejection unrelated to touches (candidate-line fitting / other Validation Gate checks).
- Known valid Falling/Rising reference-example comparison from `verification_requirements`: not performed —
  no authoritative pinned fixtures exist in this repository for this purpose. The live GRVTUSDT/DOGEUSDT
  comparison above is treated as the practical substitute for this starting-value calibration pass.

### Revision 1.3 — apex tolerance / max_ratio restoration and B-Setup admission (2026-09-11)

**What was built:**

- `geometry/validation/apex.py:357` — `if False and abs(distance) <= tolerance:` restored to
  `if abs(distance) <= tolerance:`. `tolerance = structure_length * 0.35` (the line immediately above,
  untouched) once again takes effect: an Apex landing up to 35% of the structure's own length before the
  structure's last index is valid ("Apex slightly before structure end"), instead of unconditionally falling
  through to "Apex position invalid" whenever `distance < 0`.
- `geometry/validation/apex_quality.py:25` — `max_ratio` default restored from `1.0` (set by commit `98cf042`,
  2026-08-11) back to its pre-`98cf042` value of `3.0`. `min_slope_difference=0.05` and the
  `relative_slope_difference` comparison (introduced later by commit `5059d4f`, 2026-08-15) are unchanged —
  that is a separate, scale-invariance-motivated change, not part of this finding, and was left alone.
- `signal/filter.py` — the hunter-mode block `if quality_name == "B Setup" and score >= 70: return
  approved=False, reason="Good structure waiting confirmation"` (present since the initial commit, predating
  both commits above) is replaced by `if quality_name == "B Setup": return approved=True, reason="Valid
  structure admitted"`. The prior `score >= 70` sub-condition is dropped entirely: it only ever gated which
  rejection message was shown (B Setup below score 70 fell through to the same generic "Conditions not
  satisfied" reject at the bottom of the function), never whether approval was possible.
- `tests/test_signal_admission.py` — the one test asserting the old blocked behavior
  (`test_hunter_quality_boundaries`) updated from `assertFalse` to `assertTrue` for a B-Setup, score-70 case.

**Why these three and not others:** `signal/quality.py`'s tier-assignment thresholds (Elite/A/B/Watch/Weak
Setup boundaries) and the later `min_slope_difference`/relative-slope-difference change are untouched — the
user's finding was specifically that these three restrictions left *no path to approval* for structures that
otherwise cleared every other check, not that the tier boundaries themselves were mis-calibrated.

**Verification:**

- Full repository regression (`python -B -m unittest discover -s tests`, via the project's own
  `venv/Scripts/python.exe`): 734 tests, 2 failures / 6 errors, identical to the established pre-existing
  baseline. Zero new failures or errors.
- `tests/test_geometry_pipeline.py` / `tests/test_wedge_pipeline.py` (plain-script): byte-identical
  pre-existing output.
- Live smoke test, 18 real Bybit symbols sampled from the full active-instrument universe (hunter mode,
  `TIMEFRAME=1`, `CANDLE_LIMIT=200` — production config): **0 approved before the fix, 3 approved after** —
  `1000RATSUSDT` (Rising Wedge, B Setup, score 100), `AKEUSDT` (Triangle Compression, B Setup, score 85),
  `ALLOUSDT` (Rising Wedge, B Setup, score 100), all via the new "Valid structure admitted" path. Several other
  symbols showed "Weak Setup" at score 90-100; confirmed to be the pre-existing, unrelated ATR-containment
  tier-downgrade penalty firing on an otherwise-Watch-tier result, not a side effect of these three edits.
  3/18 is a small, noisy sample and is not extrapolated into a per-run throughput estimate — it confirms the
  admission funnel is unblocked, not that the resulting volume is well-calibrated (see `risks`).

**Not yet done:** ongoing monitoring of live approved-signal volume against the ~30/run historical baseline —
restoring `max_ratio=3.0` and the early-apex tolerance both widen admission, and B Setup no longer being
blocked removes the other major restriction, so actual production volume should be watched for over-admission
rather than assumed to land back exactly at the historical rate. No further action is queued unless that
monitoring surfaces a problem.

### Not yet done (revisions 1.0-1.2)

Commit authorization (per `ASSISTANT_PROTOCOL.md` 7.2, a prior approval does not carry forward to a new
change) — since resolved: `2dae85d` (revision 1.2). The multipliers, outlier allowance, and graduated-score
formula remain explicitly non-final starting values subject to later calibration against historical data, per
this CR's own resolved_decisions text.
