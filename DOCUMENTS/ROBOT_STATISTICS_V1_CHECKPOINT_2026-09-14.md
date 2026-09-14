# Robot Statistics v1 — implementation checkpoint

Date: 2026-09-14
Status: PAUSED AFTER COMPLETED MILESTONES
Owner line: Robot Statistics
Authoritative design contract: `DOCUMENTS/AUTOPILOT_TRADING_DIARY_ANALYTICS_FILTERS_DECISION.md`

## Purpose

This checkpoint records the completed Robot Statistics v1 work before pausing the `feat/robot-statistics` line. It is intended as the restart/handoff reference for the next chat or development session.

## Repository checkpoint

The Statistics branch was synchronized with `main` after PR #99.

Authoritative merged HEAD before this documentation checkpoint:

- `575aefa2407c8e7f4bdac50f8ab6b4c168fca132` — merge of PR #99.

The implementation branch `feat/robot-statistics` and `main` were identical at that SHA before this documentation-only commit.

A pre-existing unrelated local modification to `DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-SAFETY-P0-001.md` was present in `C:\BybitScanner-Stats`. It belongs to the Robot Safety line and was intentionally not modified, staged, reset, restored, or included in any Statistics commit.

## Completed Statistics milestones

### 1. Specification / semantics

PR #93 established the Robot Statistics v1 contract and data semantics.

Key accepted boundaries:

- statistics are read-only and account-scoped;
- durable source is existing `robot_trades` joined to `robot_candidates`;
- no persistence schema migration for Statistics v1;
- Robot history is not merged with the general Trading Diary merely for convenience;
- authoritative monetary calculations use `Decimal`;
- gross and known-cost-adjusted PnL remain distinct;
- unknown costs remain unknown rather than being silently treated as zero;
- aggregate percentage is `Return on traded notional`, not account/equity ROI;
- cumulative PnL ordering is deterministic by `exit_time_ms`, then `trade_id`;
- daily analytics use MSK close date;
- time-of-day analytics use MSK entry time;
- ticker grouping key is `symbol`;
- signal grouping key is `pattern + source_timeframe`;
- unavailable STOP-block and daily-drawdown-block counters remain explicitly unavailable.

### 2. Read-only Statistics core

PR #95 implemented the Statistics core.

Implemented components:

- `terminal/statistics/models.py`;
- `terminal/statistics/reader.py`;
- `terminal/statistics/aggregation.py`;
- focused Statistics tests.

Reader guarantees:

- true SQLite URI `mode=ro` boundary;
- no schema initialization;
- no migration;
- no WAL configuration/change;
- no persistence writes;
- account-scoped completed Robot trades;
- fail-closed behavior for missing/incompatible schema;
- fail-closed candidate linkage/account consistency checks.

Aggregation core includes:

- selected PnL-basis semantics;
- coverage/completeness handling;
- cumulative realized Robot PnL series;
- summary metrics;
- Return on traded notional subset integrity;
- Decimal arithmetic.

### 3. Daily PnL and per-day ticker breakdown

PR #97 implemented daily aggregation.

Implemented behavior:

- close-date grouping by `exit_time_ms` in `Europe/Moscow` / MSK;
- total daily selected PnL;
- completed-trade count;
- selected-trade count;
- per-day ticker breakdown;
- deterministic day ordering;
- deterministic symbol ordering;
- adjusted-basis exclusion of trades with unknown recorded costs from selected aggregates;
- Decimal-only calculations.

Protected task:

- `20260914T174247Z-7fa68df84210` — PASS.

Merged PR #97:

- merge SHA `22ef20222c8dbccbb8ec9d73eaf26ea587b8a6f4`.

### 4. Ticker ranking

PR #99 implemented the next narrow aggregation slice.

Implemented model:

- `TickerRankingRow`
  - `symbol`;
  - `selected_pnl_usdt`;
  - `trade_count`.

Implemented aggregation:

- group by `symbol`;
- selected `PnlBasis` support;
- for `KNOWN_COST_ADJUSTED`, trades with unknown cost evidence are excluded from both selected PnL and selected trade count;
- Decimal arithmetic only;
- deterministic ranking order:
  1. selected PnL descending;
  2. trade count descending;
  3. symbol ascending.

Deliberately not added in this slice:

- separate best/worst ticker state;
- per-ticker win rate;
- per-ticker average PnL;
- API/UI exposure;
- reader changes;
- schema/store/runtime/lifecycle changes.

Verification:

- protected task `20260914T183235Z-4e21fb8fe162` — `STATUS PASS`;
- 22 focused aggregation tests passed;
- `git diff --check` passed;
- protected verifier reported no blockers.

Implementation commit:

- `dac17f5d4100803246cef39b2155eec0aac4cd13` — `feat: add Robot Statistics ticker ranking`.

Merged PR #99:

- merge SHA `575aefa2407c8e7f4bdac50f8ab6b4c168fca132`.

## Current Statistics ownership boundary

The completed Statistics line owns its Statistics implementation only. During the final micro-slice its writable scope was deliberately limited to:

- `terminal/statistics/models.py`;
- `terminal/statistics/aggregation.py`;
- `tests/test_robot_statistics_aggregation.py`.

The following areas remain outside Statistics ownership unless a future authorized slice explicitly changes that boundary:

- Robot runtime/control/admission/execution/protection/recovery;
- persistence schema and write store;
- PAPER/LIVE runtime behavior;
- Robot Safety changes;
- Telegram monitoring;
- API/UI exposure.

## Coordination with Robot Safety line

Current ownership was explicitly separated before pausing Statistics.

Robot Safety P0.1 owns the active runtime work involving:

- `terminal/runtime/paper_http_server.py`;
- `terminal/runtime/paper_runtime.py`;
- `tests/test_terminal_paper_runtime.py`.

The local modification to `DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-SAFETY-P0-001.md` in the Statistics worktree is also unrelated to Statistics and must not be lost by reset/restore/checkout.

`start_scanner.bat` in the main worktree was separately identified as a pre-existing local modification and is not part of Statistics or Robot Safety P0.1 ownership.

## Not yet implemented in Statistics v1

The following planned slices remain pending and should be taken one small protected task at a time:

1. Signal ranking using the fixed key `pattern + source_timeframe`.
2. Time-of-day ranking using `entry_time_ms` converted to MSK, with sample-count visibility.
3. Remaining ranking/detail metrics required by the design contract where durable evidence supports them.
4. Filter projection across summary, daily series, rankings, and cumulative series.
5. Thin read-only API exposure.
6. AUTOPILOT / Robot Statistics UI.
7. Drill-down integration.

Do not add unavailable STOP-block or daily-drawdown-block counts heuristically. Those require future durable evidence/schema work in a separately authorized scope.

## Recommended restart point

When Statistics work resumes:

1. Start from current `origin/main` and synchronize the dedicated Statistics worktree/branch without touching unrelated Robot Safety local modifications.
2. Re-read `AGENTS.md`, `DOCUMENTS/ASSISTANT_PROTOCOL.md`, and the authoritative Statistics decision document.
3. Preserve the existing read-only / Decimal / no-schema-change boundary.
4. Use one narrow protected task per aggregation capability.
5. The next logical core aggregation slice is signal ranking by `pattern + source_timeframe`; it was discussed but intentionally NOT started before this pause.

## Pause decision

Statistics development is intentionally paused here. No protected task for signal ranking was started. The completed work through ticker ranking is merged and verified. Future work should continue from this checkpoint rather than reopening or reworking the already accepted daily/ticker slices without a concrete defect or changed requirement.
