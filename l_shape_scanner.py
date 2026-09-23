"""Scanner-owned L-shaped candidate preview and owner-visible Telegram delivery.

Reuse already fetched candles; no separate market fetch, Robot candidate,
approval, order placement or modification of Wedge/Box signal memory.
"""

from pathlib import Path
import re

import config
from geometry.l_shape import find_latest_l_shape
from geometry.l_shape_preview import l_shape_caption, render_l_shape_preview
from notification import (
    build_tradingview_keyboard,
    get_telegram_chat_ids,
    get_telegram_owner_chat_id,
    send_photo,
)
from signal_memory import load_memory, save_memory


def observe_l_shape(symbol, candles, *, timeframe, chart_dir="charts"):
    """Report and render a candidate using only the snapshot's closed prefix.

    Scanner's Bybit snapshot includes the newest possibly open candle; exclude
    it before detection and rendering. The most recent HIGH -> trough ->
    breakout in the closed candles is reported, so a breakout a few candles
    before the scan is not missed. The filename preserves the local HIGH/LOW
    and the breakout (decision) candle, independently of other pattern charts.
    """
    if candles is None or len(candles) < 2:
        return None
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not re.fullmatch(r"[A-Z0-9]+", symbol) or not timeframe.isdecimal():
        raise ValueError("invalid L-shape symbol or timeframe")
    closed = candles.iloc[:-1].copy().reset_index(drop=True)
    formation = find_latest_l_shape(closed)
    if formation is None:
        return None
    source_time = int(closed.iloc[formation.as_of_index]["time"])
    extreme_time = int(closed.iloc[formation.extreme_index]["time"])
    chart = Path(chart_dir) / "l_shape" / (
        f"{symbol}_{timeframe}_{formation.direction}_{extreme_time}_{source_time}.png"
    )
    # Report the candidate even if the subsequent renderer fails.
    print(
        f"{symbol:<15} L-SHAPE candidate {formation.direction} "
        f"source_candle_time_ms={source_time} extreme_time_ms={extreme_time} "
        f"breakout={formation.breakout_level} target={formation.target_level}"
    )
    chart.parent.mkdir(parents=True, exist_ok=True)
    render_l_shape_preview(
        closed, formation, chart, symbol=symbol, timeframe=timeframe,
    )
    print(f"{symbol:<15} L-SHAPE preview {chart}")
    return {
        "formation": formation,
        "extreme_time_ms": extreme_time,
        "source_candle_time_ms": source_time,
        "chart_path": str(chart),
    }


def send_l_shape_observation(symbol, observation, *, timeframe, test_mode=False):
    """Send a candidate preview to the normal Telegram feed, without Robot.

    Deduplicate by the frozen local HIGH/LOW + breakout candle, which never
    change once the breakout candle has closed. Persist per-recipient success so retries do not resend
    a successful photo to other recipients when only one delivery failed.
    """
    if not getattr(config, "TELEGRAM_ENABLED", False) or not observation:
        return False
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not re.fullmatch(r"[A-Z0-9]+", symbol) or not timeframe.isdecimal():
        raise ValueError("invalid L-shape symbol or timeframe")
    formation = observation["formation"]
    if formation.direction not in ("LONG", "SHORT"):
        raise ValueError("invalid L-shape direction")

    recipients = get_telegram_chat_ids()
    if not recipients:
        return False
    extreme_time = int(observation["extreme_time_ms"])
    breakout_time = int(observation["source_candle_time_ms"])
    memory_key = (
        f"l_shape:{symbol}:{timeframe}:{formation.direction}:"
        f"{extreme_time}:{breakout_time}"
    )
    memory = load_memory()
    seen = memory.get(memory_key, {})
    already_sent = set(seen.get("delivered_to", ())) if not test_mode else set()
    owner_chat_id = get_telegram_owner_chat_id()
    caption = l_shape_caption(symbol, timeframe, formation)
    if test_mode:
        caption += "\n🧪 TEST MODE"

    all_delivered = True
    sent_new = False
    for chat_id in recipients:
        if chat_id in already_sent:
            continue
        markup = build_tradingview_keyboard(
            symbol, timeframe,
            include_review_actions=(chat_id == owner_chat_id and bool(owner_chat_id)),
            robot_candidate_id=None,
        )
        try:
            response = send_photo(
                config.TELEGRAM_TOKEN,
                chat_id,
                observation["chart_path"],
                caption=caption,
                reply_markup=markup,
            )
            if not isinstance(response, dict) or not response.get("ok"):
                all_delivered = False
                continue
            sent_new = True
            if not test_mode:
                already_sent.add(chat_id)
                memory[memory_key] = {
                    "delivered_to": sorted(already_sent),
                    "pattern": "L-shape",
                }
                save_memory(memory)
        except Exception as error:
            all_delivered = False
            print(f"[L-SHAPE TELEGRAM] {symbol} chat_id={chat_id}: {error}")
    return all_delivered and sent_new
