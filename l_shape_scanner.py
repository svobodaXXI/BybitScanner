"""Scanner-owned L-shaped candidate preview and owner-visible Telegram delivery.

Reuse already fetched candles. Production owner cards may persist an immutable
L-shape Robot candidate, but this module never approves or executes it.
"""

from pathlib import Path
import re

import config
from geometry.l_shape import detect_l_shape, l_shape_signal_plan
from geometry.l_shape_preview import l_shape_caption, render_l_shape_preview
from robot_candidate_store import create_signal_snapshot
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
    it before detection and rendering. Only a HIGH -> trough -> breakout whose
    breakout IS the latest closed candle is a current signal, and only if it
    passes L-shape signal eligibility (potential >= 0.8%, reference STOP with
    reward/risk >= 2:1). There is never a fallback to an older breakout: that
    formation is history, not a signal (CAKEUSDT 5m sent 108 candles late).
    The filename preserves the local HIGH/LOW and the breakout (decision)
    candle, independently of other pattern charts.
    """
    if candles is None or len(candles) < 2:
        return None
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not re.fullmatch(r"[A-Z0-9]+", symbol) or not timeframe.isdecimal():
        raise ValueError("invalid L-shape symbol or timeframe")
    closed = candles.iloc[:-1].copy().reset_index(drop=True)
    formation = detect_l_shape(closed)       # breakout == latest closed candle
    if formation is None:
        return None
    plan = l_shape_signal_plan(formation)
    if not plan.eligible:
        print(
            f"{symbol:<15} L-SHAPE structure not signalled {formation.direction} "
            f"source_candle_time_ms={int(closed.iloc[formation.as_of_index]['time'])} "
            f"potential={plan.potential_percent:.2f}% "
            f"reason={plan.rejection}"
        )
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
        f"breakout={formation.breakout_level} target={formation.target_level} "
        f"stop={plan.stop} stop_kind={plan.stop_kind} rr={plan.reward_risk:.2f}"
    )
    chart.parent.mkdir(parents=True, exist_ok=True)
    render_l_shape_preview(
        closed, formation, chart, symbol=symbol, timeframe=timeframe,
    )
    print(f"{symbol:<15} L-SHAPE preview {chart}")
    return {
        "formation": formation,
        "signal_plan": plan,
        "extreme_time_ms": extreme_time,
        "source_candle_time_ms": source_time,
        "chart_path": str(chart),
    }


def _robot_signal_snapshot(symbol, timeframe, observation):
    formation = observation["formation"]
    plan = observation["signal_plan"]
    return {
        "pattern": "L-shape",
        "symbol": str(symbol).strip().upper(),
        "timeframe": str(timeframe).strip(),
        "scanner_source_timeframe": str(timeframe).strip(),
        "robot_handoff_ready": True,
        "l_shape": {
            "direction": formation.direction,
            "source_timeframe": str(timeframe).strip(),
            "breakout_time_ms": int(observation["source_candle_time_ms"]),
            "extreme_time_ms": int(observation["extreme_time_ms"]),
            "reference": plan.reference,
            "target": plan.target,
            "stop": plan.stop,
            "stop_kind": plan.stop_kind,
            "structural_stop": plan.structural_stop,
            "potential_percent": plan.potential_percent,
            "reward_risk": plan.reward_risk,
        },
    }


def send_l_shape_observation(symbol, observation, *, timeframe, test_mode=False):
    """Send an eligible L-shape preview and owner-only executable Robot handoff.

    The immutable candidate identity is persisted in signal memory before
    delivery, so a per-recipient Telegram retry reuses the same Robot candidate
    instead of allocating a second one.
    """
    if not getattr(config, "TELEGRAM_ENABLED", False) or not observation:
        return False
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not re.fullmatch(r"[A-Z0-9]+", symbol) or not timeframe.isdecimal():
        raise ValueError("invalid L-shape symbol or timeframe")
    formation = observation["formation"]
    if formation.direction not in ("LONG", "SHORT"):
        raise ValueError("invalid L-shape direction")
    plan = observation.get("signal_plan")
    if plan is None or not plan.eligible:
        return False

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
    robot_candidate_id = None
    if owner_chat_id and not test_mode:
        robot_candidate_id = str(seen.get("robot_candidate_id", "")).strip() or None
        if robot_candidate_id is None:
            try:
                candidate = create_signal_snapshot(
                    _robot_signal_snapshot(symbol, timeframe, observation),
                    timeframe=timeframe,
                )
                robot_candidate_id = candidate["candidate_id"]
                memory[memory_key] = {
                    **seen,
                    "delivered_to": sorted(already_sent),
                    "pattern": "L-shape",
                    "robot_candidate_id": robot_candidate_id,
                }
                save_memory(memory)
                seen = memory[memory_key]
            except Exception as error:
                print(
                    "[ROBOT CANDIDATE ERROR] "
                    f"symbol={symbol} pattern=L-shape error={error}"
                )

    caption = l_shape_caption(symbol, timeframe, formation)
    if test_mode:
        caption += "\n🧪 TEST MODE"

    all_delivered = True
    sent_new = False
    for chat_id in recipients:
        if chat_id in already_sent:
            continue
        is_owner = chat_id == owner_chat_id and bool(owner_chat_id)
        markup = build_tradingview_keyboard(
            symbol, timeframe,
            include_review_actions=is_owner,
            robot_candidate_id=robot_candidate_id if is_owner else None,
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
                    **seen,
                    "delivered_to": sorted(already_sent),
                    "pattern": "L-shape",
                    "robot_candidate_id": robot_candidate_id,
                }
                save_memory(memory)
        except Exception as error:
            all_delivered = False
            print(f"[L-SHAPE TELEGRAM] {symbol} chat_id={chat_id}: {error}")
    return all_delivered and sent_new
