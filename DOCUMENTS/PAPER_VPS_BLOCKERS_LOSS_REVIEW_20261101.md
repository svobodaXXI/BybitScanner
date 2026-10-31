# PAPER VPS — incident/blocker register and trading-loss analysis (2026-11-01)

**Status:** evidence-based review / pending runtime acceptance; documentation only.  
**Evidence timestamp:** 2026-11-01 00:00:33 MSK (Codex read-only snapshot supplied by owner).  
**Deployment at snapshot:** `d345411c95a079a2c8ac3cd02d9f875700ba8ca3`; target stable `a95a847fb57e5e742c4a4ce05e7b6264fe0b9768` (merged #730 and #731).  
**DB:** `/var/lib/bybitscanner/paper_runtime.sqlite3`; identity `e0cbafb1c172b65f2db3a2c7cef2636b4164a4b1a229bd183bd907e7984ff0ad`; integrity OK, backend/Telegram identities agree.  
**Evidence boundary:** snapshot is historical, NOT current VPS state, not proof of a close-all attempt, deployment, reconciliation, corrected PnL, or subsequent outcomes. The owner authorized closing all PAPER positions later, but **no execution response/evidence of that operation was received as of this document**. No assumption that VIRTUAL is still open or already closed.

## 1. Confirmed system state (snapshot)

| Area | Observation | Interpretation |
|---|---|---|
| Backend | active PID 500879; uptime since 2026-10-31 15:50:21 MSK; zero systemd restarts | running on old deployed release |
| Scanner | SCANNER_RUNNING; real child PID 569707, durable reason still child_pid=500911; progress 801/815, errors=0 | scanning works; authority/observability mismatch |
| Robot | ROBOT_RUNNING / RECONCILIATION_REQUIRED | fail-closed, cannot admit new entries |
| Autopilot | PAPER_AUTO, reason=owner | mode ON, actual admission blocked |
| Protection | healthy=true | coverage confirmed for the only observed open exposure |
| Telegram | active PID 500901, /health ready; same DB identity | functioning as observed |
| Gateway | unauthenticated direct /health HTTP 403 | standalone direct health not proven, not proof of failed Telegram transport |
| LIVE | mode=paper; paper_live_safe=true | no LIVE activity demonstrated |
| Active LIMIT / unfinished Market commands | 0 / 0 | no pending entry execution at snapshot |
| Obligations | 22 total: 21 RESOLVED, BUSDT 1 DISPATCHING | unresolved protective accounting/lifecycle |
| Projection anomalies | protection API ENTRY_PENDING for AUSDT and KMNOUSDT despite no active LIMIT | investigation needed, not proof of open exposure |

**Open exposure at snapshot:** VIRTUALUSDT, Rising Wedge 5m, SHORT 422 @ 0.5924, opened 2026-10-31 22:01:03 MSK; confirmed STOP 0.5954, TAKE 0.5618443175; one fill, no top-ups; snapshot midpoint 0.59105; unrealized gross +0.569700 USDT, minus paid entry fee 0.149995680 => net-to-date +0.419704320 USDT. Hypothetical gross loss to STOP 1.2660 USDT and gross reward to TAKE 12.894498 USDT (gross RR ~10.185); realized exit and future fees/slippage **unknown**. Do not treat net-to-date as realizable final net.

## 2. Blockers, incidents and required acceptance

### P0 — BUSDT: immutable STOP/TAKE finalization conflict

**FACT:** durable STOP obligation for BUSDT is DISPATCHING and winning_leg STOP. Its stable execution already exists: Sell 487 @ 0.1280451745, exit fee 0.0374148; projection Flat/0, no remaining BUSDT orders. Meanwhile immutable Robot trade was incorrectly finalized as TAKE. STOP finalizer repeatedly raises `ImmutableExecutionConflict: Robot trade already closed with different evidence`; Robot entered RECONCILIATION_REQUIRED; admission is false. Filtered owner-task/conflict/overflow log count exceeded 45,000 lines in current process — this is an event/log-line count, **not** distinct failures.

**PROVEN ROOT CAUSE:** competing terminal attribution: Box generic TAKE flat-finalizer ran after an executed STOP but before the STOP obligation finalizer. The store correctly rejects a conflicting second immutable close; reconciliation re-enters same conflict on old release. This is a lifecycle ownership bug, not an unexecuted BUSDT STOP.

**CODE STATUS:** #731 merged into stable `a95a847f`: prevents new Box TAKE finalizer from stealing a pending obligation, plus strictly conditioned recovery for a prior misclassified STOP. #730 merged earlier: AAVE frozen STOP and API3 same-event close. CI PASS is source/fixture evidence only. **Neither fix is VPS-proven.**

**ACCEPTANCE:** safe release transition; single canonical `POST /api/robot/reconcile` when permitted; BUSDT RESOLVED, corrected STOP attribution with identical execution/economics, Flat/0, no duplicate exec, no leftover obligations, consistent protected exposure and admission/recovery state. Any mismatch remains fail-closed. **No manual SQLite rewrites** and no repeated market exit.

### P0 — operator Close-All deadlock under already-unresolved STOP

**REPOSITORY FACT (old/new path examined):** `POST /api/close-all` goes to `coordinated_paper_close_all` and processes every unresolved STOP obligation **before** flattening Robot positions. When BUSDT's old-release finalizer cannot resolve DISPATCHING, it rejects `operator_close_triggered_stop_unconfirmed`, so it never reaches the protected VIRTUAL Market close. The Robot-only `/api/robot/close-all-now` route accepts READY/PAUSED, not RECONCILIATION_REQUIRED. A generic `/api/full-close` is not a substitute: it does not prove Robot trade ownership/close ledger or the comprehensive close-all contract. Also note coordinated Close-All can set Autopilot OFF before rejecting; a failed command must not be assumed side-effect-free.

**BOUNDARY:** the owner subsequently commanded to close all PAPER positions, but only an operator instruction was handed to Codex. **No Codex execution receipt after that command is available.** Thus the blocker is a repository-code-derived predicted refusal, **not** a proven failed production Close-All attempt. Do not guess current VIRTUAL status.

**REQUIRED REMEDY:** after verifying the latest VPS state, recover the proven BUSDT terminal obligation using a legitimate supported runtime release/entrypoint, or create a separately authorized *exit-only* safe recovery path that preserves obligation identities, no second Market, Robot ownership and protection until FLAT. Do **not** defeat the protective gate, call generic full-close directly, restart services under exposure or edit DB. Acceptance: owner-requested account-wide FLAT/0, 0 active LIMIT/commands, 0 unprotected residual exposure, durable trade/fees PnL, and independently reconciled BUSDT. Requires explicit authority if changing runtime/deployment.

### P0 — deployment safety deadlock / older release

**FACT:** VPS is deployed as an immutable file release without `.git`. At snapshot it had an open VIRTUAL protected solely by the live backend, while the fixed code was 10 commits newer. A direct `git pull` is inapplicable; `systemctl restart/stop` or SIGTERM of backend would interrupt PAPER STOP/TAKE protection. Guarded deployment was correctly BLOCKED while protected exposure existed, leaving BUSDT recovery and Robot admission unresolved. Do not infer that a GitHub merge updated the deployed release.

**FOLLOW-UP:** once account FLAT is proven, install via the supported release transport with DB identity/secret/config preservation, guarded file integrity and rollback plan (no forced Git/reset/clean); reconcile once, confirm startup control and Telegram. If not FLAT, a different approved, *proven-continuous-protection* technique is necessary; none has been demonstrated. No LIVE and no owner-thread bypass.

### P1 — protection execution defects: API3 and AAVE

- **API3 IKIGAI_BOX SHORT:** STOP first latched at 0.2417 but actual exit fill at 0.2425895609 after 3,371,801 ms (~56m 12s). Adverse difference vs trigger estimated in read-only report as 0.46186 USDT. This is a proven abnormal delay; separating matching/slippage effects from delay requires exact event timeline. #730's same-event dispatch is CI-tested but runtime unverified.
- **AAVE IKIGAI_BOX SHORT:** frozen first-fill STOP 135.44 (basis FROZEN_FIRST_FILL) was changed on top-ups to 135.36; actual exit 135.36. This contradicts the frozen-stop attempt policy. #730 makes armed STOP immutable, CI-tested; deployed code still old at snapshot. Do **not** assert every resulting AAVE loss was caused by the reprice without counterfactual executable quotes.

### P1 — ingress, ownership and state observation

- Scanner actual worker PID 569707 vs stale durable reason child_pid=500911. Worker progressed, but single-authority proof and later stop control require reconciliation of actual process lineage. Do not kill either PID merely to make metadata match.
- Protection ingress capacity 64, observed high watermark 64, maximum queue latency 3194 ms and max processing 1676 ms; recorded overflow **none**. Saturation is a reliability warning, not evidence that events were lost.
- Projection `ENTRY_PENDING` for AUSDT/KMNOUSDT without LIMIT: confirm source/ownership to distinguish stale flags from expected durable reservations, before treating it as an admission defect.
- Direct Gateway `/health` HTTP 403 with Telegram worker ready: classify as authorization/observability unknown, not transport outage. Do not print secrets.

### P1 — STOP reentry acceptance incomplete

99 first durable attempts; attempt_index=2 only for AAOIUSDT and ATUSDT, both INVALIDATED without fill; attempt_index=3 absent. Reentry lifecycle has **not** been validated by a filled, protected repeat, but missing fresh formation, risk caps, candidate staleness or reentry thesis can legitimately suppress entry. Do not weaken Admission or force a trade for acceptance.

## 3. Financial accounting (26 closed position cycles, 128 execution rows)

Financial figures are taken from the owner's read-only execution-based reconciliation report. One cycle groups all partial fills; execution-only historical 1000RATSUSDT and ARKUSDT cycles are included but intentionally unattributed. No exit fees for VIRTUAL are invented.

| Measure | Whole DB | Last 24 hours |
|---|---:|---:|
| Closed cycles | 26 | 22 |
| Wins / losses | 2 / 24 | 2 / 20 |
| Win rate | 7.69% | 9.09% |
| Realized gross PnL | -13.910655 | -10.978950 |
| Actual fees on closed cycles | 5.672365335 | 4.946503150 |
| Realized net PnL | **-19.583020335** | **-15.925453150** |
| Profit factor | 0.0587 | 0.0712 |
| Avg positive net cycle | +0.610498 | +0.610498 |
| Avg negative net cycle | -0.866834 | -0.857322 |

Initial PAPER deposit 5000.000000 USDT. VIRTUAL paid entry fee 0.149995680. Total incurred fees including open entry 5.822361015. Calculated cash balance after realized cycles/open entry fee 4980.266983985; marked equity at snapshot 4980.836683985, including unrealized gross +0.569700; combined mark-to-market result -19.163316015 USDT (-0.38327%). Historical close-to-close maximum drawdown 19.635641 USDT (0.39271%); intratrade mark-to-market drawdown cannot be proven.

**Important:** `paper_accounts.equity_usdt=5000` is a fixed reference, **not** a continually updated account equity. Use reconstructed fills and fees for performance analysis; do not write these computed balances back to DB. BUSDT's trade reason is wrong at snapshot; numbers reflect journal-derived results, not endorsement of TAKE labeling.

### Results by strategy — whole DB, realized net USDT

| Strategy | Closed cycles | Wins/losses | Gross | Fees | Net |
|---|---:|---:|---:|---:|---:|
| MIRROR | 8 | 1 / 7 | -3.5282 | 1.5422 | **-5.0704** |
| IKIGAI_BOX | 7 | 1 / 6 | -1.3805 | 1.4247 | **-2.8052** |
| Falling Wedge | 4 | 0 / 4 | -4.4543 | 1.1197 | **-5.5740** |
| Rising Wedge | 4 | 0 / 4 | -2.8108 | 0.9272 | **-3.7379** |
| L-shape | 1 | 0 / 1 | -1.1022 | 0.2981 | **-1.4003** |
| Old execution-only (unattributed) | 2 | 0 / 2 | -0.6347 | 0.3604 | **-0.9951** |

Combined WEDGE = 8 closed, 0 wins, net -9.3119 USDT. WEDGE accounts for ~47.6% of realized net loss magnitude; this is **contribution in this small sample**, not population strategy expectancy. MIRROR 8/1, Box 7/1 likewise inadequate for a statistical verdict.

## 4. Why trading lost money — evidence vs hypotheses

### Proven accounting causes

1. **Unfavorable realized outcomes before fees:** realized gross -13.910655 USDT. Fees alone cannot explain losses. For every +1 USDT of realized gross profit there were about 17 USDT of realized gross losses (profit factor ~0.059 for net-cycle reporting). Actual net outcomes are 2 wins / 24 losses; mean net loss ~0.8668 exceeds mean net win ~0.6105.
2. **Material friction:** 5.672365335 USDT paid fees on closed cycles. That adds ~40.8% to the absolute gross realized loss (5.6724/13.9107), not 40.8% of *total* loss; approximately 29.0% of the total absolute net loss is fees. Most strategy groups show gross losses even before fees. Some positive-gross emergency closes became negative-net (e.g. HANA +0.2238 gross, -0.0765 net; NIGHT +0.0121 gross, -0.2880 net; 1INCH +0.0309 gross, -0.1942 net).
3. **Emergency exits heavily represented:** 9 of the last 20 closed cycles are labeled EMERGENCY (HOLO, CRCL, CHIP, HANA, 1INCH, RAYDIUM, KERNEL, ALCH, NIGHT). They materially alter payoff distribution; this is **not** evidence they were wrong (they may be necessary safety closes), nor proof that any particular underlying signal is poor. Separate emergency reason, operator action, execution timings and net outcome before judging strategy.
4. **Known technical execution/outcome misattribution:** delayed API3 STOP, repriced AAVE STOP and falsely labeled BUSDT TAKE are proven. They compromise execution-quality measurement, the legitimacy of some exit classifications and availability/admission, without by themselves explaining all -19.58 USDT.
5. **No observed successful STOP reentries:** no evidence that post-STOP campaigns recover part of their losses via successful subsequent fills. This is a *missing demonstrated benefit*, not evidence that profitable reentries would have existed.

### Plausible but NOT proven strategic drivers

- **Entry selectivity / signal geometry:** WEDGE 0/8 wins and MIRROR 1/8 warrant candle-by-candle provenance audit of pattern, boundary, confirmed candle, timing, mirror invalidation on later wick and MARKET/LIMIT attribution; cannot conclude false signals from cycle PnL alone.
- **Exit distribution / payoff asymmetry:** frozen plans can advertise high target RR (VIRTUAL gross ~10.2), but realized outcomes may be dominated by frequent STOP/EMERGENCY and partial fills. Need cohort-level *realized* R-multiples, planned vs achieved RR, actual entry/exit fees, MAE/MFE and holding intervals. A high theoretical RR is not evidence of profitable execution.
- **Stale/admitted entries and portfolio gates:** observed `CANDIDATE_STALE`, `PORTFOLIO_AGGREGATE_CAP`, `ROBOT_NOT_READY`, `SYMBOL_OWNED`, `CANDIDATE_FRESHNESS_UNKNOWN`, `REENTRY_THESIS_UNPROVEN` and `DAILY_EQUITY_UNAVAILABLE`. Rejected candidates do not establish missed profitable opportunities. Audit only proven incorrect decisions; do not bypass risk limits.
- **Sample/selection effects:** 26 cycles on a recently modified runtime are a small, nonstationary sample (different code revisions, incident/rollback/emergency conditions). A 7.69% realized win rate is a serious observed loss signal **for this deployed cohort**, not proof of invariant negative expectancy under a repaired runtime.

### Audit order to distinguish the causes (no strategy mutation yet)

A. **Trade ledger validity**: one durable cycle per actual position, corrections for BUSDT exit classification, actual gross/fees/net (no doubles), and separate emergency versus STOP/TAKE/operator outcomes.  
B. **Execution-quality cohort**: for each trade match source signal→frozen plan→entry fill(s)→STOP/TAKE updates→winning leg→exit execution; calculate execution delay, price deviations, fee burden and actual R; explicitly flag API3/AAVE/BUSDT and affected version.  
C. **Signal-quality cohort**: within verified, non-emergency, correctly protected closes, compare WEDGE (rising/falling separately), MIRROR, BOX and L-shape; only then classify invalid pattern/entry vs legitimate loss. Preserve actual timestamps and avoid look-ahead.  
D. **Prospective PAPER acceptance**: after safe recovery, verify a contiguous protected entry→fill→STOP/TAKE→fees→closed trade and guarded reentry if naturally formed. No forced live trades; LIVE prohibited.

## 5. Priority queue / next decision boundaries

| Priority | Goal and minimal proven boundary | Exit criterion |
|---|---|---|
| P0 | Owner-ordered PAPER Close-All, presently unverified; known BUSDT conflict potentially prevents global endpoint | Fresh VPS proof of account-wide Flat/0, no active orders, accounted executions/fees, no unprotected residue; if endpoint refuses, do NOT use uncoordinated Market/SQL |
| P0 | Safe old-release→stable deployment and BUSDT reconciliation (conditional on safe exposure state or independently proven continuity) | Stable release SHA and DB identity verified; BUSDT STOP RESOLVED no duplicate execution; Robot recovery/admission honest |
| P1 | Protection and close-path integrity (AAVE, API3, BUSDT), ingress and ownership | Required replay/tests AND VPS observations on fixed SHA; no invented PASS |
| P1 | Loss root-cause audit: entry quality versus execution, fee and emergency | Per-trade causal ledger with verified source/plan/filled prices and R, strategy split not driven by EMERGENCY contamination |
| P1 | Reentry proof and scanner/runtime identity | Filled protected reentry only on a natural qualifying event; accurate PID/ownership |

**Non-negotiable:** PAPER-only; no blind backfill or manual SQLite modification; no forced backend stop/restart with protected exposure; no duplicate market exit; no financial "correction" of evidence. Owner permission for a trade close is not blanket permission for risky deployment or overriding safety gates. Existing earlier MIRROR/Telegram/viewport queue is preserved in BACKLOG without reprioritizing unrelated items.

## Source / provenance

Owner-supplied Codex **"Полное READ-ONLY ревью PAPER VPS"**, 2026-11-01 00:00:33 MSK: 290 lines, sections A–H, DB-derived 128 executions/26 cycles, protection and infrastructure metrics. Owner-supplied preceding BUSDT forensic report and blocked deploy preflight, plus repository inspection of `terminal/runtime/paper_runtime.py` (`coordinated_paper_close_all`, `_finalize_paper_protection_obligation`), `terminal/application/robot_control.py`, and `terminal/runtime/paper_http_server.py`. Later Codex Close-All execution result not supplied. No external market backtest has been performed.
