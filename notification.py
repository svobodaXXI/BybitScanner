"""
notification.py

Формирование и отправка
торговых уведомлений.

Не содержит:

- анализа;
- расчётов;
- работы с Bybit.

Только:

- принимает результат;
- форматирует сообщение;
- отправляет текст и график в Telegram;
- добавляет ссылку TradingView.
"""

import os

from telegram_bot import (
    send_message,
    send_photo
)

from tradingview_bridge import (
    create_tradingview_url
)

from robot_candidate_store import (
    create_signal_snapshot,
)

from timeframe_format import format_timeframe_ru
from robot_state_machine import is_supported_pattern

import config
from telegram_labels import SCANNER_EMOJI


# Presentation-only Russian pattern labels for the unified Scanner caption
# (owner format, 2026-09-23): direction is carried by the arrow, not the
# name, so Falling/Rising Wedge share one non-directional label. Mirrored
# from chart_clean.py's chart-title pattern_names mapping, which keeps its
# own directional wording (kept as a separate copy since the two modules
# must not import each other).
PATTERN_LABELS_RU = {
    "Falling Wedge": "Клин",
    "Rising Wedge": "Клин",
    "Triangle Compression": "Сжимающийся треугольник",
    "No wedge": "Клин не найден",
    "Unknown": "Неизвестная структура",
}

# Owner format 2026-09-23: arrow instead of a textual direction word.
DIRECTION_ARROWS = {"LONG": "↑", "SHORT": "↓"}

# Owner format 2026-09-23: a wedge's arrow describes its geometry (the slope
# of its two trendlines) and never changes after breakout, unlike
# DIRECTION_ARROWS above, which follows the breakout direction. Mirrored
# from chart_clean.py's copy (kept separate since the two modules must not
# import each other).
WEDGE_GEOMETRY_ARROWS = {"Falling Wedge": "↘", "Rising Wedge": "↗"}

POTENTIAL_UNAVAILABLE_RU = "РАСЧЁТ НЕДОСТУПЕН"


def format_potential_percent(potential):
    """Presentation-only percent text; mirrors chart_clean.py's
    build_chart_title potential formatting (kept as a separate copy since
    the two modules must not import each other)."""
    potential = potential or {}
    signed_potential = potential.get("signed_percent")
    if potential.get("direction") == "SYMMETRIC":
        symmetric_percent = potential.get("percent")
        return (
            f"±{symmetric_percent:.2f}%"
            if symmetric_percent is not None
            else POTENTIAL_UNAVAILABLE_RU
        )
    if signed_potential is None:
        return POTENTIAL_UNAVAILABLE_RU
    return f"{signed_potential:+.2f}%"

# Presentation-only stage -> status-circle mapping, derived entirely from the
# existing Scanner confirmation/quality classification (confirmation.py's
# breakout/retest booleans and signal/quality.py's tier names) -- no new
# strategy semantics. See report for the full mapping rationale.
_MATURE_QUALITY_TIERS = {"B Setup", "A Setup", "Elite Setup"}

CIRCLE_FORMING = "🟢"
CIRCLE_MATURE_PRE_BREAKOUT = "🟡"
CIRCLE_POST_BREAKOUT_WAITING_RETEST = "🟠"
CIRCLE_POST_RETEST_LATE_ENTRY = "🔴"


def signal_stage_circle(result):
    """Map the existing Scanner confirmation/quality classification onto one
    of four presentation stages, without inventing new internal states.

    breakout + retest       -> POST-RETEST / LATE ENTRY  (🔴)
    breakout only           -> POST-BREAKOUT / WAITING RETEST (🟠)
    no breakout, mature     -> MATURE / NEAR APEX / PRE-BREAKOUT (🟡)
    no breakout, not mature -> FORMING (🟢)
    """

    confirmation = result.get("confirmation") or {}
    breakout = bool(confirmation.get("breakout", False))
    retest = bool(confirmation.get("retest", False))

    if breakout and retest:
        return CIRCLE_POST_RETEST_LATE_ENTRY
    if breakout:
        return CIRCLE_POST_BREAKOUT_WAITING_RETEST

    quality_tier = (result.get("quality") or {}).get("quality")
    if quality_tier in _MATURE_QUALITY_TIERS:
        return CIRCLE_MATURE_PRE_BREAKOUT
    return CIRCLE_FORMING


CHARTS_DIR = "charts"


def get_telegram_chat_ids():
    """Return configured Telegram recipients in stable, deduplicated order."""

    configured = getattr(
        config,
        "TELEGRAM_CHAT_IDS",
        None
    )

    if isinstance(configured, (str, int)):
        configured = (configured,)

    recipients = []
    seen = set()

    for value in configured or ():
        if value is None:
            continue

        chat_id = str(value).strip()

        if not chat_id or chat_id in seen:
            continue

        seen.add(chat_id)
        recipients.append(chat_id)

    if recipients:
        return tuple(recipients)

    legacy_chat_id = str(
        getattr(config, "TELEGRAM_CHAT_ID", "")
    ).strip()

    if legacy_chat_id:
        return (legacy_chat_id,)

    return ()


def get_telegram_owner_chat_id():
    """Return the legacy single-recipient ID used as Scanner OWNER."""

    return str(
        getattr(config, "TELEGRAM_CHAT_ID", "")
    ).strip()


def _telegram_delivery_ok(response):
    return bool(
        isinstance(response, dict)
        and response.get("ok", False)
    )


def format_symbol_for_telegram(symbol):
    """Format a symbol for the Telegram card without changing its identity."""

    symbol = str(symbol)

    if symbol.endswith("USDT"):
        return symbol[:-4]

    return symbol


ROBOT_CANDIDATE_FAILURE_WARNING = (
    "⚠️ Робот: кандидат {symbol} {timeframe} не создан. "
    "Сигнал доставлен без Robot-кнопки."
)


def warn_owner_robot_candidate_failed(owner_chat_id, symbol, timeframe):
    """Tell only the owner that a signal has no Robot button; never retried."""

    text = ROBOT_CANDIDATE_FAILURE_WARNING.format(
        symbol=format_symbol_for_telegram(symbol),
        timeframe=format_timeframe_ru(timeframe),
    )

    try:
        response = send_message(
            config.TELEGRAM_TOKEN,
            owner_chat_id,
            text
        )

        if not _telegram_delivery_ok(response):
            print(
                f"[ROBOT CANDIDATE WARNING ERROR] "
                f"chat_id={owner_chat_id} response={response}"
            )

    except Exception as error:
        print(
            f"[ROBOT CANDIDATE WARNING ERROR] "
            f"chat_id={owner_chat_id} error={error}"
        )


def send_message_to_recipients(text, reply_markup=None):
    """Send one message to every configured recipient without fail-fast."""

    recipients = get_telegram_chat_ids()

    if not recipients:
        print("[TELEGRAM ERROR] No recipients configured")
        return False

    all_delivered = True

    for chat_id in recipients:
        try:
            response = send_message(
                config.TELEGRAM_TOKEN,
                chat_id,
                text,
                reply_markup=reply_markup
            )

            if not _telegram_delivery_ok(response):
                all_delivered = False
                print(
                    f"[TELEGRAM MESSAGE ERROR] "
                    f"chat_id={chat_id} response={response}"
                )

        except Exception as error:
            all_delivered = False
            print(
                f"[TELEGRAM MESSAGE ERROR] "
                f"chat_id={chat_id} error={error}"
            )

    return all_delivered


def format_signal(
    result,
    test_mode=False
):
    """
    Преобразует результат анализа
    в сообщение для Telegram.
    """

    if not result:
        return None

    pattern = result.get(
        "pattern",
        "Unknown"
    )

    pattern_label = PATTERN_LABELS_RU.get(
        pattern,
        pattern
    )

    score = result.get(
        "final_score",
        result.get(
            "score",
            0
        )
    )

    symbol = result.get(
        "symbol",
        "UNKNOWN"
    )

    circle = signal_stage_circle(result)

    timeframe_label = format_timeframe_ru(
        result.get(
            "timeframe",
            getattr(config, "TIMEFRAME", "1"),
        )
    )

    if pattern in WEDGE_GEOMETRY_ARROWS:
        # A wedge's own slope, not the (possibly not-yet-happened) breakout
        # direction: fixed for the pattern and never changes after breakout.
        arrow = WEDGE_GEOMETRY_ARROWS[pattern]
    else:
        confirmation = result.get("confirmation") or {}
        arrow = DIRECTION_ARROWS.get(confirmation.get("direction"), "")
    potential_text = format_potential_percent(result.get("potential"))
    pattern_line = f"{arrow} {pattern_label} ({potential_text})".strip()

    test_marker = (
        "\n🧪 TEST MODE"
        if test_mode
        else ""
    )

    message = f"""
{SCANNER_EMOJI} Сканер: {symbol} {circle}
{pattern_line}
{timeframe_label}{test_marker}
Баллы: {score}
"""

    return message.strip()


def build_tradingview_keyboard(
    symbol,
    timeframe,
    include_review_actions=True,
    robot_candidate_id=None,
    robot_status_button=False,
):
    """Telegram inline keyboard for TradingView, review, and Robot admission."""

    tradingview_url = (
        create_tradingview_url(
            symbol,
            timeframe
        )
    )

    symbol = str(symbol)
    timeframe = str(timeframe)

    keyboard = [
        [
            {
                "text":
                    "\U0001F4C8 Open TradingView",

                "url":
                    tradingview_url
            }
        ]
    ]

    if robot_candidate_id:
        keyboard.append(
            [
                {
                    "text": "🤖 Робот",
                    "callback_data": (
                        f"robot:approve:{robot_candidate_id}"
                    ),
                }
            ]
        )
    elif robot_status_button:
        keyboard.append(
            [
                {
                    "text": "🤖 Робот",
                    "callback_data": "robot:cmd:status",
                }
            ]
        )

    if include_review_actions:
        keyboard.extend(
            [
            [
                {
                    "text":
                        "\U0001F4CC \u0412 \u0440\u0430\u0437\u0431\u043e\u0440",

                    "callback_data":
                        f"review:queue:{symbol}:{timeframe}"
                },
                {
                    "text":
                        "\u2705 \u0425\u043e\u0440\u043e\u0448\u0438\u0439",

                    "callback_data":
                        f"review:good:{symbol}:{timeframe}"
                }
            ],
            [
                {
                    "text":
                        "\u274C \u0413\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u044f",

                    "callback_data":
                        f"review:geometry:{symbol}:{timeframe}"
                },
                {
                    "text":
                        "\u2693 Anchor/START",

                    "callback_data":
                        f"review:anchor:{symbol}:{timeframe}"
                }
            ]
            ]
        )

    return {
        "inline_keyboard": keyboard
    }


def send_signal(
    result,
    test_mode=False
):
    """
    Отправляет сигнал в Telegram.

    Если для символа существует сохранённый
    график, он отправляется после текста.

    Под графиком добавляется кнопка
    открытия текущего символа в TradingView.
    """

    if not config.TELEGRAM_ENABLED:
        return False

    message = format_signal(
        result,
        test_mode=test_mode
    )

    if not message:
        return False

    all_delivered = send_message_to_recipients(
        message
    )

    symbol = result.get(
        "symbol"
    )

    if not symbol:
        return all_delivered

    timeframe = str(
        result.get(
            "timeframe",
            getattr(
                config,
                "TIMEFRAME",
                "5"
            )
        )
    )

    chart_path = os.path.join(
        CHARTS_DIR,
        (f"{symbol}_analysis.png" if timeframe == "5"
         else f"{symbol}_{timeframe}_analysis.png")
    )

    if not os.path.exists(
        chart_path
    ):
        print(
            f"[TELEGRAM] Chart not found: "
            f"{chart_path}"
        )
        return all_delivered

    owner_chat_id = get_telegram_owner_chat_id()
    robot_candidate_id = None
    robot_candidate_failed = False

    # Only production Scanner signals can be handed to Robot.  Persist the
    # complete signal payload first; a failed persistence simply withholds the
    # Robot button and does not break ordinary Scanner notification delivery.
    # Patterns without a Robot lifecycle get no candidate and no Robot button.
    robot_handoff_ready = not result.get("scanner_observational_only", False) and (
        timeframe == "1"
        or result.get("robot_handoff_ready") is True
    ) and is_supported_pattern(result.get("pattern"))
    if owner_chat_id and not test_mode and robot_handoff_ready:
        try:
            candidate = create_signal_snapshot(
                result,
                timeframe=timeframe,
            )
            robot_candidate_id = candidate["candidate_id"]
        except Exception as error:
            robot_candidate_failed = True
            print(
                "[ROBOT CANDIDATE ERROR] "
                f"symbol={symbol} error={error}"
            )

    for chat_id in get_telegram_chat_ids():
        try:
            is_owner = (
                bool(owner_chat_id)
                and chat_id == owner_chat_id
            )
            reply_markup = (
                build_tradingview_keyboard(
                    symbol,
                    timeframe,
                    include_review_actions=is_owner,
                    robot_candidate_id=(
                        robot_candidate_id
                        if is_owner
                        else None
                    ),
                )
            )

            response = send_photo(
                config.TELEGRAM_TOKEN,
                chat_id,
                chart_path,
                reply_markup=reply_markup
            )

            if not _telegram_delivery_ok(response):
                all_delivered = False
                print(
                    f"[TELEGRAM PHOTO ERROR] "
                    f"chat_id={chat_id} response={response}"
                )

        except Exception as error:
            all_delivered = False
            print(
                f"[TELEGRAM PHOTO ERROR] "
                f"chat_id={chat_id} error={error}"
            )

    # After the ordinary card/photo delivery, tell the owner (only) why the
    # Robot button is missing. The warning never affects delivery status.
    if robot_candidate_failed:
        warn_owner_robot_candidate_failed(owner_chat_id, symbol, timeframe)

    return all_delivered
