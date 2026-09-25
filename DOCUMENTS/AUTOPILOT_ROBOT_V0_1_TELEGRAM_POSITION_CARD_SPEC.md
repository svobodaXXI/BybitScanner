# AUTOPILOT Robot v0.1 — Telegram position card, `/positions` menu and closed-trade post (implementation spec)

Status: IMPLEMENTATION SPEC — Slice 1 and Slice 2 merged (PR #148); Slice 3 implemented locally (uncommitted)
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
5. Chart (candles of the signal's timeframe, `bybit_api.get_candles(symbol, str(minutes), limit)`;
   timeframe and `limit` per Section 5, item 6):
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

## 5. Slice 3 — Lifecycle posts (opened + closed)

Decisions (implemented; change on request):

1. Trigger: a daemon thread in the Telegram listener (`telegram_monitoring.py`) polls every ~10 s
   (`LIFECYCLE_POLL_SECONDS`) with its own SQLite connection and posts newly opened and newly closed
   robot trades (read-only store query `load_robot_trades_with_events_since`). The listener loop blocks
   in `getUpdates`, hence the separate thread. Read-only with respect to trading state; posting from the
   PAPER backend is rejected (Telegram network calls would enter the robot hot path).
2. De-duplication: durable state file `review_queue/.robot_lifecycle_notified` (directory is git-ignored)
   with `initialized_at_ms` and the most recent notified `trade_id`s per kind (opened / closed).
   The first run initializes it to the current time: no back-fill of history. A `trade_id` is recorded
   only after a successful send, so an undelivered post is retried; a damaged file restarts from now.
3. Post = the Slice 2 card and chart for the trade, headed "🤖 Сделка открыта" or
   "🤖 Сделка закрыта · <причина>". Close reason labels (the values actually written):
   `STOP` -> "по стопу", `TAKE` -> "по тейку", `EMERGENCY_CLOSE` -> "аварийное закрытие",
   unknown -> raw value.
4. Result of a closed trade (post and closed-trade card):
   "Итог: X USDT (до комиссий), комиссии Y USDT (вход + выход), Z% (после комиссий)", where
   X = `realized_pnl_usdt` (gross), Y = sum of `fee` over the trade's executions — the same executions
   drawn as filled markers (entry fills incl. partials + closing fill; for a LIMIT entry the closing-side
   executions within 5 s of `exit_time_ms` are added), Z = (X − Y) / (`entry_quantity` × `average_entry`) × 100.
   Stored `fees_costs_usdt` / `realized_pnl_pct` cover only the closing execution and are not shown;
   they are not changed here (see "Robot closed-trade fee attribution" in `PROJECT_STATE.md`).
5. Keyboard of lifecycle posts: only "Все позиции" (`robot:view:positions`). `build_robot_tab_keyboard`
   is unchanged; its "Под наблюдением" and "Обновить" buttons have no handlers yet (separate task).
6. Chart timeframe and window (implemented, `fix/telegram-cards-formatting`): the chart timeframe is the
   Robot signal's timeframe. Source: `signal_snapshot["scanner_source_timeframe"]` (minutes as a string,
   e.g. "5" or "1"), fallback `signal_snapshot["robot_geometry"]["scanner_source_timeframe"]`; allowed
   1, 3, 5, 15, 30, 60; anything else, a missing field or a parse error -> 5; a manual position (no robot
   trade) -> 5. The value is `PositionView.chart_candle_minutes` (set by `load_position_view`), the single
   source for the candle request and the renderer: `bybit_api.get_candles(symbol, str(minutes), limit)`,
   title "... | {minutes}m", time axis in MSK. One request helper (`telegram_monitoring._with_candles` +
   `robot_position_view.chart_candle_limit`) and one renderer (`render_position_chart`) serve both the
   position card and the lifecycle posts.
   `limit = min(1000, max(min_candles, ceil(minutes from entry_time_ms to now / minutes) + 24))`,
   `min_candles` = 300 for 1m and 120 for every other timeframe; for a closed trade also from
   `entry_time_ms` to now (the post goes out right after the close). If the entry's candle is 1000+ candles
   back (~16.7 h on 1m, ~83 h on 5m) it is outside even the largest window: 1000 candles are requested and
   the caption gets the line "Вход раньше окна графика". A fill or order at any time inside a candle is drawn
   on that candle (`[open, open + candle duration)`; for 1m this is the previous behaviour). Pattern lines
   are unchanged: evaluated at each candle's open time through `project_latest_geometry_index` in the frozen
   1m cursor space. PnL of an open position uses the close of the last candle. Windows above 500 candles are
   rendered on a wider canvas (16x7 in, 120 dpi, candle width 0.8) so bodies stay distinguishable.

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
- Slice 3: after a robot trade opens / closes, within ~10 s one post arrives (closed: exit marker, the
  correct close reason, entry + exit fees); a restart of the listener does not re-send it.

## 6. Owner UI refinement — queued 2026-09-25

This is a presentation-only follow-up for the **open Robot position card**. It does not change trading state, execution, protection, sizing, order ownership, PnL accounting or lifecycle behavior.

1. **Right-side chart clearance.** Move the visible end of the candle plot materially left, approximately toward the middle of the right half of the chart, so right-edge level/price annotations do not overlap the newest candles. Preserve the same candle set, timestamps and frozen pattern geometry; solve this with chart window/padding/layout only, not by dropping recent candles or moving execution evidence.
2. **Entry label.** Remove the word `Вход`. Keep the horizontal average-entry level and keep its numeric price annotation.
3. **Protection labels.** Render the stop and take labels as short `SL` and `TP`.
4. **Executed-fill markers.** Make the filled triangular execution markers slightly smaller. Replace the current black marker edge with a direction-matched edge: green for LONG-side fills and red for SHORT-side fills. Do not change execution time/price placement or the filled-vs-resting semantic distinction.
5. **Position size text.** The open-position card's `Размер` row must show the authoritative coin quantity plus the position's entry notional in parentheses. Compute notional as `quantity × average_entry` and format in USDT, for example: `Размер: 23760 4STOCK (249.95 USDT)`.
6. **Scope discipline.** Reuse the existing `robot_position_view.py` / `robot_position_chart.py` path. No new card subsystem, no data-model change and no trading mutation are justified by this UI refinement.

Acceptance: verify the changed renderer/text with focused tests, then inspect it through the normal Telegram position-card flow. Do not infer any trading correctness from the visual acceptance itself.
