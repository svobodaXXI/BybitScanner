# BybitScanner — handoff for Claude
Date: 2026-09-12

## Project
Repository: `C:\BybitScanner`
GitHub: `svobodaXXI/BybitScanner`

## Working protocol
- Work exactly one dependent step at a time.
- Before repo edits, read `DOCUMENTS/ASSISTANT_PROTOCOL.md` and root `AGENTS.md`.
- Do not ask the user to manually edit repo-owned source/docs.
- Do not touch unrelated/user-owned untracked files.
- Repo edits go through the project harness:
  - `python -m tools.dev.task start --intent ... --path ...`
  - make the narrow authorized change
  - `python -m tools.dev.task finish --task TASK_ID`
- User prefers short copy-ready PowerShell commands.
- If a user action is required, begin with exactly: `Сейчас сделай:`
- End-of-session target: commit, clean tracked status, push, verify GitHub.

## Current Git state
Branch: `robot-v0-1-admission-gate`
HEAD: `a445e9c87e226499d15f9f6979bcd66bf96fec49`

Tracked modified files:
- `DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`
- `tests/test_directional_envelope_quality.py`
- `tests/test_scanner_geometry_atr_containment.py`
- `wedge/integrity.py`

Known user-owned/untracked — DO NOT TOUCH / COMMIT:
- `New Chat.txt`
- `_narrow_scan_temp2.py`
- `_narrow_scan_temp_exclude_ab.py`
- `robot.ico`
- `runtime/`
- `start_robot.bat`
- `stop_robot.bat`
- `test_100.txt`
- `test_compare_falling_candidates.py`
- `Инструкция по запуску на новом компьютере.txt`

## Completed containment package
Purpose: temporarily disable Scanner containment penalties until calibration is completed.

Implemented:
- `wedge/integrity.py`
  - `CONTAINMENT_VIOLATION_EVALUATION_ENABLED = False`
  - early zero-return path
  - previous implementation retained behind the switch
- tests explicitly enable the switch for legacy containment behavior
- default-off behavior covered
- docs updated with calibration-required note

Verification:
- focused tests: `38/38 PASS`
- diff-check: PASS
- final task: PASS
- receipt: `20260912T162357Z-1d98431d478c`

A checkpoint command was suggested earlier:
`python -m tools.dev.checkpoint --message "fix: temporarily disable scanner containment penalties"`
but its output was not observed. Do not assume commit/push happened.

## Robot v0.1 runtime investigation
Read-only investigation. Do not start/stop/change Robot state without explicit authorization.

Candidate:
- symbol `1000NEIROCTOUSDT`
- pattern `Falling Wedge`
- candidate id `452a8621daa863885e821918`

Saved scanner snapshot:
`C:\BybitScanner\runtime\terminal\robot_candidates\452a8621daa863885e821918.json`

Authoritative DB:
`C:\BybitScanner\paper_runtime.sqlite3`
(default from `BYBITSCANNER_PAPER_DB`, fallback `paper_runtime.sqlite3`)

Observed Robot runtime state:
- `mode = ROBOT_RUNNING`
- `recovery_status = READY`

Observed authoritative candidate state:
- status `APPROVED`
- `state_revision = 23`
- phase `WAITING_RETEST`
- direction `LONG`
- `breakout_index = 201`
- `retest_index = null`
- `geometry_cursor = 222`
- `last_event = NO_TRANSITION`

Interpretation:
Robot is active, detected the Falling Wedge upside breakout, and is waiting for a retest before entry.

`robot_trades` currently has `0` rows.
Robot has not entered any PAPER trade yet.

Relevant architecture confirmed:
- `terminal/application/robot_admission.py` admits Scanner candidates to authoritative SQLite.
- `terminal/application/robot_breakout_monitor.py` advances durable APPROVED candidates on closed 1m candles.
- `terminal/runtime/paper_runtime.py` constructs and starts `RobotBreakoutMonitor`.
- Monitor opens its own SQLiteStore connection through a store factory.

## Telegram resend test
The saved `1000NEIROCTOUSDT` signal was successfully resent to Telegram from `signal_snapshot_json`.

Important:
- no new Robot candidate created
- existing Robot state unchanged
- text delivery succeeded
- chart delivery succeeded
- owner message id `2784`
- second recipient message id `2785`

The resend did NOT call `notification.send_signal()` because that production path can persist/create a Robot candidate.

## Immediate next task
Finish current containment package safely:
1. Review only the four tracked modified files.
2. Commit only those tracked files.
3. Do not include untracked/user-owned files.
4. Push according to repository protocol.
5. Verify remote state.
6. Leave tracked working tree clean.

Suggested commit message:
`fix: temporarily disable scanner containment penalties`
