"""Opt-in Scanner -> Telegram bridge for Ikigai Box.

A CONFIRMED Box may be frozen as an immutable BOX_PLAN_ONLY plan through a
caller-supplied preparer so the owner card can offer ``🤖 Робот``; admission
itself only happens on that owner tap. No orders or Wedge signal-memory key are
created here, and WATCH stays observational. The newest Bybit kline is skipped
because it can still be open. See DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md.
"""

import os
import re
from decimal import Decimal, InvalidOperation

from geometry.ikigai_box import IkigaiBoxWatch, detect_ikigai_box
from geometry.ikigai_box_chart import ikigai_box_signal_text, render_ikigai_box_chart
from notification import (
    build_tradingview_keyboard,
    get_telegram_chat_ids,
    get_telegram_owner_chat_id,
    send_message,
    send_photo,
    warn_owner_robot_candidate_failed,
)
from robot_failure_diagnostics import record_robot_incident
from signal_memory import load_memory, save_memory
from terminal.paper.ikigai_box_plan import approved_first_grid

import config


_SAFE_SYMBOL = re.compile(r"^[A-Z0-9]+$")


def _completed_before_delivery(closed, formation, tick_size):
    """True only when an exact first-grid P1 touch precedes a later TAKE touch.

    Same-candle P1+TAKE is intentionally ambiguous because OHLC has no intrabar
    ordering, so it is not enough to mark a setup completed.
    """

    if tick_size in (None, ""):
        return False
    try:
        tick = Decimal(str(tick_size))
        if not tick.is_finite() or tick <= 0:
            return False
        prices, take = approved_first_grid(
            direction=formation.direction,
            frozen_f1=Decimal(str(formation.fibonacci_1_0)),
            frozen_f1618=Decimal(str(formation.fibonacci_1_618)),
            tick_size=tick,
        )
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return False

    p1 = prices[0]
    start = formation.second_start_index
    end = formation.as_of_index
    if type(start) is not int or type(end) is not int or not (0 <= start <= end < len(closed)):
        return False

    entry_index = None
    for index in range(start, end + 1):
        row = closed.iloc[index]
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        touched = high >= p1 if formation.direction == "SHORT" else low <= p1
        if touched:
            entry_index = index
            break

    if entry_index is None:
        return False

    for index in range(entry_index + 1, end + 1):
        row = closed.iloc[index]
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        completed = low <= take if formation.direction == "SHORT" else high >= take
        if completed:
            return True
    return False


def box_robot_formation(closed, formation):
    """Frozen CONFIRMED-formation facts the Robot Box planner consumes."""
    return {
        "direction": formation.direction,
        "a_time_ms": int(closed.iloc[formation.anchor_start_index]["time"]),
        "b_time_ms": int(closed.iloc[formation.anchor_end_index]["time"]),
        "decision_time_ms": int(closed.iloc[formation.as_of_index]["time"]),
        "anchor_a_price": str(formation.anchor_start_price),
        "anchor_b_price": str(formation.anchor_end_price),
        "f1": str(formation.fibonacci_1_0),
        "f1618": str(formation.fibonacci_1_618),
        "f2618": str(formation.fibonacci_2_618),
    }


def _prepare_owner_robot_handle(robot_plan_preparer, symbol, timeframe, closed, formation):
    """(callback handle, failed). Failure never blocks ordinary Box delivery."""
    try:
        from terminal.application.robot_admission import box_plan_admission_handle

        source_id = robot_plan_preparer(symbol, timeframe, box_robot_formation(closed, formation))
        return box_plan_admission_handle(str(source_id)), False
    except Exception as exc:
        record_robot_incident(
            incident_type="ROBOT_CANDIDATE_FAILURE",
            stage="box_plan_preparation",
            reason_code="BOX_PLAN_PREPARATION_EXCEPTION",
            symbol=symbol,
            timeframe=str(timeframe).strip() or None,
            pattern="IKIGAI_BOX",
            error=exc,
        )
        print(
            "[ROBOT CANDIDATE ERROR] "
            f"symbol={symbol} pattern=IKIGAI_BOX "
            f"error_class={type(exc).__name__}"
        )
        return None, True


def send_ikigai_box_observation(
    symbol, candles, *, timeframe, test_mode=False, chart_dir="charts",
    robot_plan_preparer=None, tick_size=None,
):
    """Deliver text then photo per frozen first-impulse pair.

    With ``robot_plan_preparer`` (production owner delivery only) the exact
    CONFIRMED formation is frozen as BOX_PLAN_ONLY first and the owner photo gets
    ``🤖 Робот`` -> ``robot:approve:<bp-handle>``. Returns True only if every
    configured recipient received both parts. Never posts a stale wedge image.
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

    if _completed_before_delivery(closed, formation, tick_size):
        if not test_mode:
            memory[memory_key] = {
                "anchors": identity,
                "pattern": "Ikigai Box",
                "status": "COMPLETED_BEFORE_DELIVERY",
            }
            save_memory(memory)
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
    robot_handle, robot_failed = None, False
    if (robot_plan_preparer is not None and not test_mode
            and owner_chat_id and owner_chat_id in recipients):
        robot_handle, robot_failed = _prepare_owner_robot_handle(
            robot_plan_preparer, symbol, timeframe, closed, formation,
        )
    delivered = True
    for chat_id in recipients:
        is_owner = chat_id == owner_chat_id and bool(owner_chat_id)
        markup = build_tradingview_keyboard(
            symbol, timeframe,
            include_review_actions=is_owner,
            robot_candidate_id=robot_handle if is_owner else None,
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

    # Same owner-only notice as the common Wedge/L-shape handoff failure path.
    if robot_failed:
        warn_owner_robot_candidate_failed(owner_chat_id, symbol, timeframe)

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
