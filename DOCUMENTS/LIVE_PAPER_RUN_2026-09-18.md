# Live PAPER run — 2026-09-18 (run log, runbook, open items)

Status: RUN LOG
Date: 2026-09-18
Scope: moving the live PAPER run from the VPS to the local PC, first Falling/Rising wedge robot trades,
incident `RECONCILIATION_REQUIRED`, next steps.
All times are local PC time. Facts below were observed in this session unless marked "not verified".

## 1. Repository and runtime layout

- PR #147 (`fix-robot-protection-health-json`) merged, merge SHA `0f4cffcca3cbc17817e87b42085ed07ae8934fe3`.
- VPS `/root/BybitScanner`: fast-forwarded to `0f4cffc`, service `bybitscanner-terminal.service` restarted,
  `/api/health` -> `{"ok":true,"mode":"paper"}`, `/api/robot/protection-health` -> `healthy: true`
  (before the restart it returned `Empty reply`; fixed by #147). Local user-owned modification of
  `bybit_api.py` on the VPS was left untouched.
- Local PC `C:\BybitScanner`: `main` == `origin/main` == `0f4cffc`; only untracked files
  (`start_robot.bat`, `stop_robot.bat`, `runtime/`, temp scripts, `New Chat.txt` …).
- Live run now: the PC runs three processes started by `start_robot.bat`:
  PAPER backend (`start_paper_backend.bat`, port 8765), Telegram listener (`telegram_monitoring.py`),
  Scanner (`main.py`). The VPS runs only the PAPER backend service. The VPS Telegram listener and Scanner
  (tmux sessions `telegram`, `scanner`) were stopped on purpose: one bot token allows one `getUpdates`
  poller (a second one gives `409 Conflict`). A tmux session `codex` remains on the VPS (unused).
- PC DB: `C:\BybitScanner\paper_runtime.sqlite3` (VPS has its own separate DB; robot state is not shared).
- Scanner config difference: PC Scanner runs with `Minimum Score: 30`; the VPS run used `60`.
  `TELEGRAM_TEST_MODE = False` on both.

## 2. Incident: robot fenced with `RECONCILIATION_REQUIRED`

Symptom: pressing "🤖 Робот" under a signal answered "отклонено — Робот не готов к приёму новых сделок",
status "Запущен / Нужна сверка".

Facts:
- DB state: `ROBOT_RUNNING` / `RECONCILIATION_REQUIRED`, reason
  `Robot position attestation no longer matches BLESSUSDT`, set at 22:15:01 (PAPER backend startup, restart
  recovery `robot_recovery.py`). Likely cause (not verified): two robot trades (BNCUSDT, BLESSUSDT) were left
  open in the local DB from earlier runs and their positions changed while the robot was off.
- The state is durable and survives restarts; the Telegram control panel shows no buttons in it
  (`robot_telegram_feed.py`: recovering from it is an unresolved separate problem).
- `POST /api/robot/reconcile` (no token, empty JSON body) is the designed exit. First attempt: HTTP 409,
  cancelled 2 PAPER limit orders (entries of the 2 APPROVED candidates), could not prove ownership/protection of
  the 2 open trades. State unchanged.
- User decision: clear the candidates and start clean.

Resolution (guarded, PAPER only):
1. All python processes stopped; DB backed up to `C:\BybitScanner_backup_20260918_222848\`.
2. Script deleted only the active leftovers in FK-safe order (protection obligations of those trades ->
   `robot_trades` -> `robot_candidates`), with an expected-count guard (4 candidates: 2 APPROVED + 2 OPEN;
   2 open trades). History kept: 17 CLOSED, 25 EXPIRED, 1 INVALIDATED. `robot_runtime_state` was NOT edited.
3. Robot restarted, `POST /api/robot/reconcile` -> HTTP 200, `recovery_status: PAUSED`.
4. User pressed "▶ Старт" in Telegram -> "Запущен / Готов" (22:30). First accepted signal: ACHUSDT.

## 3. Live results so far

- Falling Wedge / LONG:
  - UAIUSDT entry 22:58:04 (LIMIT) avg 0.3818581, qty 652, stop 0.3742210, take 0.3927548.
  - SAGAUSDT entry 23:02:04 (LIMIT) avg 0.0254413, qty 9814.6, stop 0.0249324, take 0.0283730.
  - Protection on both: `confirmed_active`; stops sit at the 2% fallback distance below entry.
- Rising Wedge / SHORT (first live shorts; mirror path verified):
  - WUSDT: entry 23:06:34 avg 0.0109873; STOP exit 23:07:05 at 0.0111044 (31 s later);
    realized_pnl_usdt -2.6654 (gross), fees 0.1516, realized_pnl_pct -1.127% (net). Candidate status CLOSED.
  - RIOTUSDT: entry 23:07:40 avg 23.86018, stop 23.95 (0.38% above), take 23.19097; take < entry < stop.
- Expired without entry: FUSDT (22:41:09), LONGXIAUSDT (23:00:09), ROSEUSDT (23:06:34).
- Later the same evening all of these trades closed; see section 3b (a TAKE exit of a short is still not observed).
- Correction of an earlier statement: there is no pattern allowlist for the robot in `main` at `0f4cffc`;
  Rising Wedge -> SHORT has been enabled since 2026-09-12 (see `SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`).
  ATR containment evaluation is currently disabled for all patterns (`CONTAINMENT_VIOLATION_EVALUATION_ENABLED = False`).

## 3b. Closed robot trades, 2026-09-18 (from `robot_trades`, 5 trades, PAPER)

| Symbol | Dir | Entry -> exit (18th) | Held | Reason | Entry | Stop | Take | Exit | Gross USDT | Fees | Net USDT | Net % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WUSDT | SHORT | 23:06:34 -> 23:07:05 | 31 s | STOP | 0.010987256 | 0.011106 | 0.010730668 | 0.011104428 | -2.6654 | 0.1516 | -2.8170 | -1.127 |
| RIOTUSDT | SHORT | 23:07:40 -> 23:22:14 | 14m33s | STOP | 23.860182 | 23.95 | 23.190973 | 23.969981 | -1.1485 | 0.1504 | -1.2989 | -0.520 |
| SAGAUSDT | LONG | 23:02:04 -> 23:34:10 | 32m05s | STOP | 0.025441255 | 0.024932429 | 0.028372976 | 0.024914208 | -5.1727 | 0.1467 | -5.3195 | -2.130 |
| UAIUSDT | LONG | 22:58:04 -> 23:35:28 | 37m24s | TAKE | 0.38185813 | 0.37422097 | 0.39275483 | 0.39256641 | +6.9818 | 0.1536 | +6.8282 | +2.743 |
| XTZUSDT | SHORT | 23:15:15 -> 23:39:01 | 23m45s | STOP | 0.2821 | 0.2838 | 0.27575776 | 0.2839 | -0.9562 | 0.0905 | -1.0466 | -0.698 |

Total: gross -2.9610, fees 0.6928, net -3.6538 USDT; 1 win, 4 losses. Robot flat afterwards (no open trades).

Caveat: the Fees column (`fees_costs_usdt`) is ONLY the fee of the closing execution; the entry fee is not
included (roughly 0.15 USDT per trade, e.g. WUSDT). Net USDT and Net % are therefore better than reality:
the real result is worse by about one more fee per trade. See "Robot closed-trade fee attribution" in
`PROJECT_STATE.md`.

Observations:
- Every exit reason matches the level side (long stop below entry, short stop above entry, take on the profit side),
  so STOP/TAKE fired on the right legs for both LONG and SHORT. The first TAKE exit (UAIUSDT, long) and the first
  SHORT stop exits were observed.
- Exit prices differ from the stop/take level by 0.014-0.083% (WUSDT -0.014% favorable, RIOT +0.083%,
  SAGA -0.073%, XTZ +0.035%, UAI take -0.048%, the last four adverse). By design: protection is a durable
  obligation latched on the executable book side (bid for LONG, ask for SHORT) and closed by a PAPER market
  order through `PaperMarketExecutor` against the current book (`paper_runtime._evaluate_fresh_protection_crossing`,
  `_dispatch_paper_protection_obligation`). A TAKE is therefore a market fill, not a resting limit. The book may
  retreat between latch and dispatch (WUSDT).
- Stop distances: SAGAUSDT and UAIUSDT used the 2% fallback (stop = entry x 0.98); the shorts used structural
  stops 1.08% (WUSDT), 0.38% (RIOTUSDT), 0.60% (XTZUSDT) above entry. Take distances: 2.3%, 2.8%, 2.2% (shorts),
  11.5% (SAGAUSDT), 2.9% (UAIUSDT).
- Position size: about 250 USDT for four trades, about 150 USDT for XTZUSDT (derived from gross PnL / price
  delta). Cause not verified (possibly a partial LIMIT fill).
- Sample of 5 trades: no conclusions about strategy quality or stop buffer parameters yet.

## 4. Findings and open items

1. PnL accounting: `realized_pnl_usdt` is gross, `realized_pnl_pct` is net of `fees_costs_usdt`
   (`robot_flat_closure.py:335-336`, matches the WUSDT numbers). `fees_costs_usdt` holds only the closing
   execution's fee; the entry fee (~0.15 USDT per trade for WUSDT) is missing, so the Fees and Net columns
   in 3b understate costs and the real result is worse than shown. This is the "Robot closed-trade fee
   attribution" item in `PROJECT_STATE.md`. Do not treat the USDT column as net. The Telegram closed-trade
   post/card sums entry + exit fees from executions for display only; stored values are unchanged.
2. Doc bug: `AUTOPILOT_ROBOT_V0_1_TELEGRAM_FEED_AND_SHORT_WEDGE_DECISION.md` line 124 says TAKE is
   "90% of `potential_percent` from the actual entry price downward". Code (`robot_protection.py`) freezes
   TAKE as `reference - 0.9 * (reference - target)` from the signal reference price toward the scanner
   target (slightly short of the target), not moved by fills. Code is right, wording must be fixed.
   Status: fix script was given to the user; whether it was applied is not verified.
3. Old manual-test residue in the PC DB (30-31 Aug): CELOUSDT dust long (1.3 units, `sync_state =
   reconciliation_required`) and 5 commands stuck in `submitting` (OGUSDT x2, CELOUSDT x3, origin
   `terminal_manual`). Result: `/positions` always shows "незавершённая PAPER-операция или сверка".
   The robot admission state is separate and unaffected. Cleaning it needs a proper task; do not edit the
   command journal by hand.
4. Short stops can be very tight (RIOTUSDT 0.38%) and WUSDT stopped out in 31 s; revisit stop buffer
   parameters only after more samples.
5. Stale GitHub state (cosmetic, nothing removed): open PRs #143, #144 (ingress diagnostics, superseded by
   #145-#147), #63, #66 (Robot slice1/slice2, superseded), #121 (docs: VPS runtime acceptance, document-only,
   still not in `main`); branch `feat/trading-diary-d7-research-integration` holds one unmerged document.
   Local-only branches `backup/local-late-admission-wiring-6d999fe` and `codex/spatial-tape-dom-alignment`,
   and 5 stashes, were not touched. The backup branch content is functionally in `main`
   (`tests/test_robot_paper_acceptance.py`: 5 passed on `main`).
5b. `robot-v0-1-paper-protection-d24-evidence` content is in `main` (schema is now v21).
6. Windows console freeze: clicking inside a PowerShell window puts it in selection mode (title starts with
   "Выбрать") and suspends the process; the Telegram listener then stops answering. Press Enter/Esc. Preventive:
   window Properties -> disable QuickEdit for the three windows.

## 5. Runbook

A. Restart only the Telegram listener and the Scanner (e.g. to load new code): in the `Telegram Review`
   window Ctrl+C then `python telegram_monitoring.py`; in the `Scanner` window Ctrl+C then `python main.py`
   (from `C:\BybitScanner`). Do not restart the PAPER Backend while the robot has open trades: startup recovery
   re-validates OPEN trades against positions (this is what fenced the robot at 22:15:01; a restart with healthy
   positions was not tested). Do not run `start_robot.bat` again while the windows are open (duplicates).
B. Lift `RECONCILIATION_REQUIRED`: no Telegram button exists. Run
   `curl.exe -sS -X POST http://127.0.0.1:8765/api/robot/reconcile -H "Content-Type: application/json" -d "{}" -w "`nHTTP %{http_code}`n"`.
   HTTP 200 + `PAUSED` -> press "▶ Старт". HTTP 409 -> read `reason` and the `unresolved_*` lists; reconcile may
   already have cancelled PAPER limit orders. If open trades cannot be proven, back up the DB first (all python
   stopped), then use a guarded cleanup like section 2; never edit `robot_runtime_state` directly.
C. One Telegram bot token = one listener. If the PC runs the listener, the VPS listener must be stopped.
D. Read-only inspection of the local DB: open `paper_runtime.sqlite3` with
   `sqlite3.connect("file:paper_runtime.sqlite3?mode=ro", uri=True)` (works while the backend is running).
   Useful tables: `robot_candidates`, `robot_trades`, `protection_projections`, `position_projections`,
   `executions`, `paper_limit_orders`, `robot_runtime_state`.

## 6. Work state at end of day

- Slice 1 (emoji labels) implemented by a Claude Code session in `C:\BybitScanner`, NOT committed, NOT loaded
  by the running windows. Files: `telegram_labels.py` (new), `notification.py`, `main.py`,
  `telegram_monitoring.py`, `telegram_review.py`, `robot_telegram_feed.py`, 4-5 test files,
  `DOCUMENTS/DECISION_LOG.md` (DECISION-009), parent design doc authorization line.
- Slice 2 and Slice 3: specified in `AUTOPILOT_ROBOT_V0_1_TELEGRAM_POSITION_CARD_SPEC.md`, not started.
- The robot keeps trading on the PC PAPER account while the three windows stay open and the PC does not sleep.

## 7. Plan for the next session

1. Review closed robot trades (query in chat history): exit reasons, stop/take levels, gross vs net.
2. Commit Slice 1 (user), then run Slice 2 (spec section 4) in Claude Code; restart the two windows;
   check `/positions` -> card with chart on SAGAUSDT / UAIUSDT / RIOTUSDT.
3. Slice 3 (closed-trade post).
4. Later: fee attribution fix; cleanup of the August manual-test residue; stale PR cleanup;
   decide when the robot moves to the VPS (needs the VPS DB state, the token owner decision, and
   the user-owned `bybit_api.py` there).

## 8. Move of the live run from the PC to the VPS (2026-09-19 morning)

Supersedes section 1 (runtime layout) and the last bullet of section 6 (robot on the PC).

- PC: all project python processes stopped (backend, Telegram listener, Scanner). Local DB left as is:
  `ROBOT_RUNNING/READY` (v54), candidates APPROVED 1 / CLOSED 22 / EXPIRED 33 / INVALIDATED 1, no open trades.
  Nothing from the PC DB is carried to the VPS (separate databases). Do not start the PC listener while the VPS
  listener runs (one bot token = one poller).
- VPS `/root/BybitScanner` at `0f4cffc` (local user-owned `bybit_api.py` modification present, untouched).
  Backend `bybitscanner-terminal.service` was not restarted. Listener and Scanner run in tmux sessions
  `telegram` and `scanner`, started by `bash /root/vps_restart.sh` (kills and recreates both sessions, prints
  state first). They do not survive a VPS reboot (not systemd services yet).
- VPS state found: `ROBOT_RUNNING/RECONCILIATION_REQUIRED` (v16), reason
  `ROBOT_PROTECTION_COVERAGE_LOST symbol=EDGEUSDT reason=ingress_overflow`, set 09-18 18:59 (the ingress
  overflow fixed by PRs #143-#147). No open trades, no open limit orders, 3 APPROVED candidates from 09-18
  11:22-11:28 (KMNOUSDT, CSOPSAMSUNG2LUSDT, LGELECTRONICSUSDT). `protection-health`: healthy, high watermark 6
  of capacity 64, max queue latency about 0.4 s.
- `POST /api/robot/reconcile` at 08:30 -> HTTP 200, `PAUSED`. User pressed "Старт" at 09:32 -> `Запущен / Готов`.
- Lesson (an earlier expectation was wrong): stale APPROVED candidates do NOT expire on resume. Per
  `resume_without_replay` (`robot_state_machine.py`) a resumed candidate expires only when the geometry cursor
  reaches the frozen `apex_index`; missed candles are not replayed, the candidate just keeps watching the
  extrapolated frozen lines from "now". After ~21 h the three candidates were still active and LGELECTRONICSUSDT got a
  working entry LIMIT at the retest level computed from the day-old geometry.
- Clean slate without SQL (`AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md`, Section 7): PAUSE only blocks
  entries and keeps candidates APPROVED; STOP cancels a working entry LIMIT and gives every zero-fill pending
  candidate the terminal `INVALIDATED` status (never revived), allowed only with no open Robot position. Then
  "Запустить робота" (start from STOPPED) and, if it lands on PAUSED, "Старт". User chose this on 2026-09-19;
  outcome not verified at the time of writing.
- Deploy path for new code (Slices 1-2): commit -> PR -> merge -> on the VPS `git pull --ff-only origin main` ->
  `bash /root/vps_restart.sh` (listener and Scanner only; the backend is not needed for Telegram-side changes).
  Risk on the first position card: the chart calls `bybit_api.get_candles` and the VPS copy of `bybit_api.py` has
  local changes; if its signature differs the card falls back to text with "график недоступен".
- The robot takes only signals for which the user pressed "🤖 Робот"; there is no automatic selection in v0.1.

## 9. Incident 2026-09-19: ingress overflow, EMERGENCY_CLOSE and a poisoned candidate

Times are VPS time (CEST). The user's Telegram shows MSK, i.e. +1 hour.

- 09:23:53: the protection queue overflowed for CVXUSDT and CFGUSDT (capacity 64). The robot was moved to
  `RECONCILIATION_REQUIRED` (`ROBOT_PROTECTION_COVERAGE_LOST symbol=CVXUSDT reason=ingress_overflow`). Both
  positions were closed as `EMERGENCY_CLOSE` (obligations with `market_event_id` "rest-recovery") at 09:23:56 and
  09:23:59. `protection-health` afterwards: `high_watermark` 64, `max_queue_latency_ms` 3552,
  `max_processing_ms` 935.
- 4 of the 8 closes in the last 24 h were `EMERGENCY_CLOSE` (KSMUSDT 18th 17:49, AEONUSDT 18th 17:59, CVXUSDT and
  CFGUSDT 19th 09:23). These are not strategy exits: exclude them from STOP/TAKE statistics.
- Poisoned candidate: FIGHTUSDT (Triangle Compression), approved 19th 08:40. Admission did not check the pattern;
  the monitor cannot create a state for it (`unsupported Robot v0.1 pattern`), so `robot_state` stayed NULL and the
  error repeated every 60 s. `reconcile_restart` then fails on "approved candidate lacks durable recovery state"
  -> reconcile returns 409. Stop/Start does not help (the entry sync starts the same monitor).
- Resolution 19th 16:24: DB copy `/root/backup_paper_runtime_20260919_162437.sqlite3`; the one candidate was moved
  to `INVALIDATED` via `SQLiteStore.save_robot_candidate_state`; reconcile -> HTTP 200, `PAUSED`; 2 PAPER limit
  orders were cancelled. The user left the robot paused until the fix and diagnostics are in.
- Cause of the overflow is not proven. Suspect: a blocking REST request in `LiveOrderBookProvider.get_book` on the
  owner thread; the more symbols under protection, the higher the load on the 64-slot queue.
- Open: CSOPSAMSUNG2LUSDT (approved 18th 11:22, `WAITING_RETEST`) survived "Стоп"; cause not established.
- Fee is about 0.06% per leg (~0.15 USDT on 250 USDT), for a LIMIT entry as well.
- Follow-up implemented locally (uncommitted): no "🤖 Робот" button and admission rejection ("паттерн не
  поддерживается роботом") for patterns other than Falling/Rising Wedge; the monitor moves an APPROVED candidate
  without `robot_state` and with an unsupported pattern to `INVALIDATED` (phase
  `INVALIDATED_UNSUPPORTED_PATTERN`); `SerializedPaperRuntime` logs a WARNING for owner tasks > 200 ms (task
  qualname, queue depth) and `protection-health` ingress reports `slowest_task_label` / `slowest_task_ms`.
