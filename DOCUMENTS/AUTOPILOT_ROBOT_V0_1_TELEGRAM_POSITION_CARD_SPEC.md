# AUTOPILOT Robot v0.1 — Telegram position card, `/positions` menu and closed-trade post (implementation spec)

Status: IMPLEMENTATION SPEC — Slice 1 and Slice 2 implemented locally (uncommitted), Slice 3 PLANNED
Date: 2026-09-18
Implementation authorization: GRANTED 2026-09-18 (user)
Parent design: `AUTOPILOT_ROBOT_V0_1_TELEGRAM_FEED_AND_SHORT_WEDGE_DECISION.md`
(this file narrows the parent; for the items listed here this file wins)

## 1. Request (user, 2026-09-18)

1. Scanner posts start with a radar emoji (fallback: binoculars). Robot posts start with a robot-head emoji.
   In `/positions` the pin emoji is replaced by the robot head.
2. `/positions` is an interactive menu: one button per open position, formatted `1. CELOUSDT · Long`.
   Tapping a button sends a new post: full position information plus a chart with
   the pattern boundary lines from the candidate signal, the average-entry / STOP / TAKE levels and
   triangle markers for executed trades. A resting (not yet filled) LIMIT is drawn as a hollow
   triangle (colored outline only).
3. When the robot closes a trade, a post arrives: the same card and chart, plus the close reason
   (stop / take).

The parent design already covers items 2 and 3 (Open Position Details card, executed-trade triangles,
closed-trade post). New in this spec: hollow triangle for a resting LIMIT, emoji conventions,
the delivery mechanism for the closed-trade post.

## 2. Baseline (repository `main` at `0f4cffc`)

- `robot_telegram_feed.py` has text-only stubs `build_observation_card`, `build_opened_card`,
  `build_closed_card`, `build_static_chart_projection`. Nothing outside tests calls them.
- `/monitoring` candidate card (`telegram_monitoring.py`, `format_candidate_card`) is text only.
- `/positions` (`_send_paper_positions`) is a text list; `format_paper_positions_view` builds it.
- There is no chart renderer for the robot and no lifecycle event posts.
- Available building blocks:
  - `telegram_bot.send_photo(token, chat_id, photo_path, caption, reply_markup)`;
  - `chart.py` (`draw_chart`, mplfinance) — scanner chart style and MSK time labels;
  - `bybit_api.get_candles(symbol, interval, limit)` — returns only the latest `limit` candles as a
    DataFrame with `time` (ms), `open`, `high`, `low`, `close`, `volume`, `turnover`.
    `bybit_api.py` is a user-owned file: import only, never modify;
  - `scanner_geometry_cursor.project_latest_geometry_index(snapshot, latest_closed_candle_time_ms=t)`
    maps a 1m candle time to the frozen geometry index space.
- Data model facts:
  - `executions`: `order_id`, `symbol`, `side` (`Buy`/`Sell`), `price`, `quantity`, `fee`, `exchange_timestamp_ms`.
  - `paper_limit_orders`: `order_id`, `symbol`, `side`, `price`, `quantity`, `status` (`open`/`partially_filled`/`filled`/`cancelled`; resting orders are `open` and `partially_filled`), `created_at_ms`.
  - `robot_trades`: `trade_id`, `candidate_id` (unique, FK to `robot_candidates`), `symbol`, `direction`, `pattern`,
    `entry_time_ms`, `entry_path` (`LIMIT`/`MARKET`), `average_entry`, `stop_price`, `take_price`,
    `exit_time_ms`, `exit_price`, `exit_reason`, `realized_pnl_usdt`, `realized_pnl_pct`, `fees_costs_usdt`.
  - `protection_projections`: `take_profit`, `stop_loss`, `status` (`confirmed_active` when working).
  - Candidate `signal_snapshot` holds `robot_geometry` (already in 1m index space: `upper_line` /
    `lower_line` `{slope, intercept}`, `apex.index`, `current_index`) and `scanner_geometry_cursor`
    (`geometry_index`, `source_candle_time_ms`, `timeframe = "1"`).
  - Candidate `robot_state["execution"]["limit_order_id"]` links the candidate to its LIMIT order.

## 3. Slice 1 — emoji labels (DONE locally, NOT committed, NOT yet running)

Result reported by the Claude Code session (91 tests passed in the 5 affected test files):

- New `telegram_labels.py`: `SCANNER_EMOJI = "📡"`, `ROBOT_EMOJI = "🤖"` (single source).
- Scanner prefix added in `notification.py` (signal post), `main.py` ("Сканер запущен"),
  `telegram_monitoring.py` (scanner status lines).
- Robot prefix added to all `Робот: …` messages in `telegram_review.py` and `telegram_monitoring.py`;
  `/positions` header pin replaced by `ROBOT_EMOJI` in `robot_telegram_feed.py`.
- `SCANNER_ACTIONS` (bot menu command descriptions) intentionally unchanged — posts only.
- Tests updated: `test_telegram_delivery.py`, `test_telegram_monitoring.py`,
  `test_telegram_robot_control.py`, `test_telegram_robot_handoff.py` (+ feed tests).
- `DECISION_LOG.md`: DECISION-009 (emoji choice). Parent design: authorization line set to GRANTED.

Emoji rationale: Unicode has no radar and no binoculars emoji (also none in the Emoji 18.0 draft).
`📡` (satellite antenna) is the closest to a radar. Change the constants to swap.

To see Slice 1 in the running bot: restart only the `Telegram Review` window and the `Scanner`
window (Ctrl+C, then `python telegram_monitoring.py` / `python main.py` from `C:\BybitScanner`).
Do NOT restart the `PAPER Backend` window while the robot has open trades (see run log, section 5).

## 4. Slice 2 — `/positions` buttons + position card with chart (DONE locally, NOT committed)

Decisions:

1. `/positions`: keep the existing list text and the warning line; add an inline keyboard with one button
   per open position: `N. SYMBOL · Long|Short`, `callback_data = "pos:card:<SYMBOL>"`
   (handled in `_process_positions_callback`). Under the card: button `⬅️ К позициям`.
2. New modules:
   - `robot_position_view.py`: `load_position_view(store, symbol)`, `format_position_card(view)` (pure).
   - `robot_position_chart.py`: `render_position_chart(view, candles_df, out_path) -> Path`
     (mplfinance; style and MSK axis like `chart.py`). Output `charts/robot/<SYMBOL>_position.png`
     (overwritten). The same view/chart code must work for closed trades (Slice 3).
3. Data sources:
   - position: `position_projections` (`quantity`, `average_entry`, `side`);
   - robot trade: `robot_trades WHERE symbol=? AND exit_time_ms IS NULL`; candidate via `candidate_id`;
     frozen snapshot = `candidate.signal_snapshot`;
   - no robot trade (manual/dust position, e.g. CELOUSDT with `sync_state=reconciliation_required`):
     text-only card, line "Позиция не от робота — график недоступен".
4. Card (photo caption, <= 1024 chars): symbol, direction `LONG`/`SHORT`, status "открыта", size,
   average entry, current PnL (approximate, from the last 1m close), STOP, TAKE, pattern.
   STOP/TAKE come from `protection_projections` (what is actually working); fallback
   `robot_trades.stop_price` / `take_price`.
5. Chart (1m candles, `bybit_api.get_candles(symbol, "1", 300)`):
   - pattern lines only from the frozen snapshot: price = `slope * idx + intercept`, with
     `idx = project_latest_geometry_index(snapshot, latest_closed_candle_time_ms=t)`;
     never recompute or refit geometry; draw until the apex time or the window end;
   - horizontal levels: average entry, STOP (red), TAKE (green), with price labels on the right;
   - markers: filled triangle = executed fill (`Buy` up, `Sell` down; price/time from
     `executions`); hollow triangle (outline only) = a resting LIMIT (`open` or `partially_filled`) `paper_limit_orders` row for
     `robot_state["execution"]["limit_order_id"]` (price, `created_at_ms`);
   - executions of the trade: `order_id == limit_order_id`; if `entry_path` is not `LIMIT` or the id is
     absent, executions of the symbol with `exchange_timestamp_ms` in
     `[entry_time_ms - 5000, (exit_time_ms or now) + 5000]`. First check the remaining `robot_trades`
     columns: if an entry-order reference exists, use it;
   - closed trade: add an exit marker from `robot_trades.exit_time_ms` / `exit_price`.
6. Failure isolation: no candles or a render error -> text card + "график недоступен"; `sendPhoto`
   error -> send as text. Log to stdout like the rest of the file.
7. Do not touch: `bybit_api.py`, any DB write, existing `callback_data`, robot logic.
8. Tests: new tests for `format_position_card` and `render_position_chart` (synthetic DataFrame, no network,
   PNG exists and is non-empty); update existing `/positions` tests; run only affected files.
9. Docs: add to the parent design, marker section: "a not yet filled LIMIT is drawn as a hollow triangle".

Implementation notes:

- (a) For candles earlier than `source_candle_time_ms` (where `project_latest_geometry_index` refuses),
  the index is the snapshot index minus the elapsed minutes, i.e. a linear continuation of the frozen
  geometry; nothing is refit.
- (b) Pattern lines start at their `anchor_index`.
- (c) `robot_trades` has no entry-order reference; `robot_state.execution.limit_order_id` is used.
- (d) Two open robot trades for the same symbol -> the card is rendered like a manual position.
- (e) The exit marker from `robot_trades` is not drawn if an execution already drawn has
  |dt| <= 2 s from `exit_time_ms` and the same price (MARKET entry: the exit fill is in the window).

## 5. Slice 3 — closed-trade post (PLANNED)

Decisions (defaults chosen by the assistant; change on request):

1. Trigger: the Telegram listener (`telegram_monitoring.py`) detects newly closed robot trades
   (`robot_trades.exit_time_ms IS NOT NULL`). The listener loop blocks in `getUpdates` (timeout 30 s),
   so use a daemon thread (own SQLite connection per poll) checking every ~10 s.
   Read-only with respect to trading state. Posting from the PAPER backend is rejected: it would put
   Telegram network calls into the robot hot path.
2. De-duplication: durable watermark file `review_queue/.robot_closed_notified` (directory is git-ignored)
   with the last notified `exit_time_ms` and the most recent notified `trade_id`s.
   First run initializes the watermark to the current time (no back-fill of history).
3. Post = the Slice 2 card and chart for the closed trade (exit marker added) plus:
   - close reason label: `STOP` -> "стоп", `TAKE` -> "тейк" (verify the exact enum values in code/DB first),
     `EMERGENCY_CLOSE` -> "аварийное закрытие (Закрыть всё)", unknown -> raw value;
   - result: `realized_pnl_usdt` is GROSS and `realized_pnl_pct` is NET of fees (see
     `robot_flat_closure.py:335-336`); show both explicitly:
     "Итог: X USDT (до комиссий), комиссии Y USDT, Z% (после комиссий)" until fee attribution is fixed.
4. Chart window: `get_candles` returns only the latest 300 1m candles; if the trade ended earlier than
   the window start, render the latest window without the exit marker and say so in the caption.
5. Out of scope now: "trade opened" and "signal accepted" posts (present in the parent design).

## 6. Constraints (all slices)

- Monitoring is read-only: no order/candidate/trade writes (parent design, Data contract).
- Pattern lines/apex come only from the frozen signal snapshot; no re-fit on live data.
- Chart overlays come only from persisted authoritative records.
- Agents do not commit or push; the user commits (PR flow as usual).
- Never modify `bybit_api.py`.

## 7. Acceptance checks (manual, after restarting Telegram Review + Scanner windows)

- Slice 1: a new scanner post starts with `📡 Сканер:`; robot replies start with `🤖 Робот:`;
  `/positions` header starts with `🤖`.
- Slice 2: `/positions` shows one button per open position; tapping an open robot position sends a photo with
  the card; lines follow the frozen wedge; entry/STOP/TAKE lines match the card; filled triangles at fills.
  Tapping CELOUSDT (manual dust) gives the text card without a chart.
- Slice 3: after a robot trade closes, within ~10 s one post arrives with the exit marker and the
  correct close reason; a restart of the listener does not re-send it.
