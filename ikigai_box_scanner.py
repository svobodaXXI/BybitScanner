"""Opt-in observational Scanner -> Telegram bridge for Ikigai Box.

No Robot candidate, orders, or Wedge signal-memory key can be created here.
The existing Scanner owns candle acquisition; the newest Bybit kline is skipped
because it can still be open. See DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md.
"""

import os
import re

from geometry.ikigai_box import IkigaiBoxWatch, detect_ikigai_box
from geometry.ikigai_box_chart import ikigai_box_signal_text, render_ikigai_box_chart
from notification import (
    build_tradingview_keyboard,
    get_telegram_chat_ids,
    get_telegram_owner_chat_id,
    send_message,
    send_photo,
)
from signal_memory import load_memory, save_memory

import config


_SAFE_SYMBOL = re.compile(r"^[A-Z0-9]+$")


def send_ikigai_box_observation(
    symbol, candles, *, timeframe, test_mode=False, chart_dir="charts"
):
    """Deliver observational text then photo per frozen first-impulse pair.

    Returns True only if every configured recipient received both parts.
    Never posts a Telegram text card pointing at a stale wedge image.
    """
    if not getattr(config, "TELEGRAM_ENABLED", False) or candles is None:
        return False
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not _SAFE_SYMBOL.fullmatch(symbol) or not timeframe.isdecimal():
        return False
    # The Bybit klines endpoint includes the current incomplete candle.
    # Do not even pass it to the detector or chart renderer.
    if len(candles) < 2:
        return False
    closed = candles.iloc[:-1]
    formation = detect_ikigai_box(closed)
    if formation is None:
        return False

    recipients = get_telegram_chat_ids()
    if not recipients:
        return False
    anchor_a_time = int(closed.iloc[formation.anchor_start_index]["time"])
    anchor_b_time = int(closed.iloc[formation.anchor_end_index]["time"])
    identity = f"{anchor_a_time}:{anchor_b_time}"
    memory_key = f"ikigai_box:{symbol}:{timeframe}:{formation.direction}"
    memory = load_memory()
    if not test_mode and memory.get(memory_key, {}).get("anchors") == identity:
        return False

    # Separate first-impulse-specific path: never reuse <symbol>_analysis.png
    # produced by chart_clean.py for a wedge on the same symbol.
    chart_path = os.path.join(
        chart_dir,
        "ikigai_box",
        f"{symbol}_{timeframe}_{formation.direction}_{anchor_a_time}_{anchor_b_time}.png",
    )
    render_ikigai_box_chart(
        closed, formation, chart_path, symbol=symbol, timeframe=timeframe
    )
    message = ikigai_box_signal_text(symbol, timeframe, formation)
    owner_chat_id = get_telegram_owner_chat_id()
    delivered = True
    for chat_id in recipients:
        is_owner = chat_id == owner_chat_id and bool(owner_chat_id)
        markup = build_tradingview_keyboard(
            symbol, timeframe,
            include_review_actions=is_owner,
            robot_candidate_id=None,
            robot_status_button=(is_owner and not test_mode),
        )
        try:
            text_response = send_message(config.TELEGRAM_TOKEN, chat_id, message)
            if not isinstance(text_response, dict) or not text_response.get("ok"):
                delivered = False
                continue
            response = send_photo(
                config.TELEGRAM_TOKEN,
                chat_id,
                chart_path,
                caption="",
                reply_markup=markup,
            )
            if not isinstance(response, dict) or not response.get("ok"):
                delivered = False
        except Exception as exc:
            print(f"[IKIGAI BOX TELEGRAM] {symbol}: {exc}")
            delivered = False

    # A failed delivery remains retryable. Keep Box history namespaced so the
    # old symbol-only Wedge memory is not changed.
    if delivered and not test_mode:
        memory[memory_key] = {
            "anchors": identity,
            "pattern": "Ikigai Box",
        }
        save_memory(memory)
    return delivered


def send_ikigai_box_watch_observation(
    symbol, candles, watch, *, timeframe, test_mode=False, chart_dir="charts"
):
    """Send one early *observational* WATCH card for a caller-frozen A/B.

    Caller must supply the exact closed-candle WATCH from sequential
    detect_ikigai_box_watches() replay. This intentionally does NOT scan or
    persist WATCH state: a stateless Scanner pass cannot preserve its box
    after re-entry. The old confirmed-formation sender remains unchanged.
    """
    if not getattr(config, "TELEGRAM_ENABLED", False) or candles is None:
        return False
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not _SAFE_SYMBOL.fullmatch(symbol) or not timeframe.isdecimal():
        return False
    if not isinstance(watch, IkigaiBoxWatch) or len(candles) < 2:
        return False
    closed = candles.iloc[:-1].reset_index(drop=True)
    if watch.as_of_index != len(closed) - 1:
        return False
    a_idx, b_idx = watch.anchor_start_index, watch.anchor_end_index
    if not (0 <= a_idx < b_idx < watch.box_start_index
            <= watch.box_end_index <= watch.as_of_index):
        return False
    sign = 1 if watch.direction == "SHORT" else -1 if watch.direction == "LONG" else 0
    if sign == 0:
        return False
    if (
        float(closed.iloc[a_idx]["low" if sign == 1 else "high"])
        != watch.anchor_start_price
        or float(closed.iloc[b_idx]["high" if sign == 1 else "low"])
        != watch.anchor_end_price
        or float(closed.iloc[watch.box_start_index:watch.box_end_index+1]["low"].min())
        != watch.box_low
        or float(closed.iloc[watch.box_start_index:watch.box_end_index+1]["high"].max())
        != watch.box_high
    ):
        return False
    # A WATCH for a zone that was already touched is not an advance
    # observation. Unlike Robot, this bridge never places an entry order.
    after_anchor = closed.iloc[b_idx + 1:]
    if (
        after_anchor["high"].max() >= watch.fibonacci_1_618
        if sign == 1 else after_anchor["low"].min() <= watch.fibonacci_1_618
    ):
        return False
    recipients = get_telegram_chat_ids()
    if not recipients:
        return False
    a_time = int(closed.iloc[a_idx]["time"])
    b_time = int(closed.iloc[b_idx]["time"])
    if b_time <= a_time:
        return False
    identity = f"{a_time}:{b_time}"
    # Keep every frozen A/B identity independent. One symbol can have several
    # historical boxes; a later send must not overwrite earlier dedup evidence.
    memory_key = (
        f"ikigai_box_watch:{symbol}:{timeframe}:{watch.direction}:"
        f"{a_time}:{b_time}"
    )
    history = load_memory()
    if not test_mode and (
        history.get(memory_key, {}).get("anchors") == identity
        or history.get(
            f"ikigai_box:{symbol}:{timeframe}:{watch.direction}", {}
        ).get("anchors") == identity
    ):
        return False

    # Distinct chart path includes both anchors and this closed-candle time.
    # Never reuse either the Wedge chart or a potentially stale Box PNG.
    chart_path = os.path.join(
        chart_dir, "ikigai_box",
        f"{symbol}_{timeframe}_WATCH_{watch.direction}_{a_time}_{b_time}_"
        f"{int(closed.iloc[watch.as_of_index]['time'])}.png",
    )
    render_ikigai_box_chart(
        closed, watch, chart_path, symbol=symbol, timeframe=timeframe,
    )
    message = ikigai_box_signal_text(symbol, timeframe, watch)
    owner_chat_id = get_telegram_owner_chat_id()
    delivered = True
    for recipient in recipients:
        markup = build_tradingview_keyboard(
            symbol, timeframe,
            include_review_actions=(recipient == owner_chat_id and bool(owner_chat_id)),
            robot_candidate_id=None,
        )
        try:
            text_response = send_message(config.TELEGRAM_TOKEN, recipient, message)
            if not isinstance(text_response, dict) or not text_response.get("ok"):
                delivered = False
                continue
            response = send_photo(
                config.TELEGRAM_TOKEN, recipient, chart_path,
                caption="", reply_markup=markup,
            )
            if not isinstance(response, dict) or not response.get("ok"):
                delivered = False
        except Exception as exc:
            print(f"[IKIGAI WATCH TELEGRAM] {symbol}: {exc}")
            delivered = False
    if delivered and not test_mode:
        history[memory_key] = {
            "anchors": identity, "phase": watch.phase,
            "pattern": "Ikigai Box WATCH",
        }
        save_memory(history)
    return delivered
