"""Opt-in observational Scanner -> Telegram bridge for Ikigai Box.

No Robot candidate, orders, or Wedge signal-memory key can be created here.
The existing Scanner owns candle acquisition; the newest Bybit kline is skipped
because it can still be open. See DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md.
"""

import os
import re

from geometry.ikigai_box import detect_ikigai_box
from geometry.ikigai_box_chart import render_ikigai_box_chart
from notification import (
    build_tradingview_keyboard,
    get_telegram_chat_ids,
    send_photo,
)
from signal_memory import load_memory, save_memory

import config


_SAFE_SYMBOL = re.compile(r"^[A-Z0-9]+$")


def send_ikigai_box_observation(
    symbol, candles, *, timeframe, test_mode=False, chart_dir="charts"
):
    """Deliver one *observational* photo per frozen first-impulse anchor pair.

    Returns True only if every configured recipient received the photo.
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
    caption = (
        f"📦 {symbol} · Коробка Икигаи · {formation.direction}\n"
        f"Фибо первого импульса: 1.0 = {formation.fibonacci_1_0:.8g}; "
        f"1.618 = {formation.fibonacci_1_618:.8g}; "
        f"2.618 = {formation.fibonacci_2_618:.8g}\n"
        "Наблюдение сканера; зоны входа плановые. "
        "Робот ордера не выставлял."
    )
    if test_mode:
        caption += "\n🧪 TEST MODE"
    markup = build_tradingview_keyboard(
        symbol, timeframe,
        include_review_actions=False, robot_candidate_id=None,
    )
    delivered = True
    for chat_id in recipients:
        try:
            response = send_photo(
                config.TELEGRAM_TOKEN,
                chat_id,
                chart_path,
                caption=caption,
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
