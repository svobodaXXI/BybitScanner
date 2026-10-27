from pathlib import Path
from datetime import datetime
import hashlib
import json
import re
import time

import requests

import config
import telegram_bot
import telegram_runtime_intent
from telegram_labels import ROBOT_EMOJI
from robot_candidate_store import RobotCandidateNotFound
from robot_telegram_feed import (
    build_robot_close_all_confirmation_keyboard,
    build_robot_control_keyboard,
    format_robot_status_text,
    parse_robot_control_callback,
)
from terminal.application.robot_admission import (
    RobotAdmissionRejected,
    admit_robot_candidate,
)
from terminal.application.robot_control import (
    RobotControlRejected,
    close_all_now,
    get_robot_runtime_status,
    pause_robot,
)
from tools import stop_robot_runtime


PROJECT_ROOT = Path(r"C:\BybitScanner")
REVIEW_QUEUE = PROJECT_ROOT / "review_queue"
OFFSET_FILE = REVIEW_QUEUE / ".telegram_offset"

REVIEW_QUEUE.mkdir(
    parents=True,
    exist_ok=True
)


ACTION_LABELS = {
    "queue": "review",
    "good": "good",
    "geometry": "geometry_error",
    "anchor": "anchor_start_error",
}


ROBOT_ADMISSION_REASON_LABELS = {
    "Robot admission is not ready": "Робот не готов к приёму новых сделок",
    "Robot runtime state is unavailable": "Состояние робота недоступно",
    "Scanner candidate is not admissible": "Сигнал сканера не допускается к приёму",
    "Scanner candidate snapshot is invalid": "Данные сигнала сканера некорректны",
    "Scanner candidate pattern is not supported by Robot": "паттерн не поддерживается роботом",
    "Robot admission clock returned invalid timestamp": "Некорректная временная метка при приёме сигнала",
    "Robot candidate identity conflicts with durable state": "Идентификатор сигнала конфликтует с сохранёнными данными",
}


def _robot_admission_reason_text(reason):
    text = str(reason)
    return ROBOT_ADMISSION_REASON_LABELS.get(text, text)


def _safe_name(value):
    value = str(value)
    value = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        value
    )
    return value.strip("_") or "unknown"


def _load_offset():
    if not OFFSET_FILE.exists():
        return None

    try:
        return int(
            OFFSET_FILE.read_text(
                encoding="utf-8"
            ).strip()
        )
    except Exception:
        return None


def _save_offset(offset):
    OFFSET_FILE.write_text(
        str(int(offset)),
        encoding="utf-8"
    )


def _telegram_request(
    method,
    **params
):
    url = (
        "https://api.telegram.org/"
        f"bot{config.TELEGRAM_TOKEN}/"
        f"{method}"
    )

    response = requests.get(
        url,
        params=params,
        timeout=40
    )

    return response.json()


def _answer_callback(
    callback_id,
    text
):
    try:
        _telegram_request(
            "answerCallbackQuery",
            callback_query_id=callback_id,
            text=text
        )
    except Exception as exc:
        print(
            "[REVIEW] answer callback error:",
            exc
        )


def _download_telegram_photo(
    file_id,
    destination
):
    result = _telegram_request(
        "getFile",
        file_id=file_id
    )

    if not result.get("ok"):
        raise RuntimeError(
            f"getFile failed: {result}"
        )

    file_path = (
        result["result"]["file_path"]
    )

    url = (
        "https://api.telegram.org/file/"
        f"bot{config.TELEGRAM_TOKEN}/"
        f"{file_path}"
    )

    response = requests.get(
        url,
        timeout=30
    )
    response.raise_for_status()

    destination.write_bytes(
        response.content
    )


def _parse_callback(data):
    parts = str(data).split(":")

    if len(parts) != 4:
        return None

    prefix, action, symbol, timeframe = parts

    if prefix != "review":
        return None

    if action not in ACTION_LABELS:
        return None

    return {
        "kind": "review",
        "action": action,
        "symbol": symbol,
        "timeframe": timeframe,
    }


def _parse_workspace_callback(data):
    """Only a verified owner callback may request local UI opening."""
    import re
    parts = str(data).split(":")
    if len(parts) != 4 or parts[0] != "workspace":
        return None
    _, mode, symbol, timeframe = parts
    if mode not in ("EDITOR", "TERMINAL"):
        return None
    if not re.fullmatch(r"[A-Z0-9]{2,32}USDT", symbol):
        return None
    if timeframe not in ("15s", "1m", "5m", "15m", "1h", "1d"):
        return None
    return {"kind": "workspace", "mode": mode, "symbol": symbol, "timeframe": timeframe}


def _run_workspace_callback(callback_query, parsed):
    """Queue-only boundary: no shell execution or robot startup in listener."""
    from workspace_owner_launcher import request_owner_workspace_open
    try:
        request_owner_workspace_open(parsed["mode"], parsed["symbol"], parsed["timeframe"])
    except Exception as exc:
        print("[WORKSPACE OPEN FAILED]", type(exc).__name__)
        _answer_callback(callback_query.get("id"), "Редактор/Терминал недоступен на ПК")
        return
    _answer_callback(callback_query.get("id"), "Команда открытия передана на ПК")


def _parse_robot_callback(data):
    parts = str(data).split(":")

    if len(parts) != 3:
        return None

    prefix, action, candidate_id = parts

    if prefix != "robot" or action != "approve":
        return None

    if not candidate_id:
        return None

    return {
        "kind": "robot",
        "action": action,
        "candidate_id": candidate_id,
    }


def _save_review(
    callback_query,
    parsed
):
    message = (
        callback_query.get("message")
        or {}
    )

    photos = (
        message.get("photo")
        or []
    )

    if not photos:
        raise RuntimeError(
            "Telegram message has no photo"
        )

    best_photo = photos[-1]

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    symbol = _safe_name(
        parsed["symbol"]
    )

    timeframe = _safe_name(
        parsed["timeframe"]
    )

    action = parsed["action"]

    callback_id = _safe_name(
        callback_query.get("id", "")
    )

    callback_suffix = (
        callback_id[-8:]
        if callback_id
        else "callback"
    )

    case_name = (
        f"{timestamp}_"
        f"{symbol}_"
        f"{timeframe}_"
        f"{action}_"
        f"{callback_suffix}"
    )

    case_dir = (
        REVIEW_QUEUE
        / case_name
    )

    case_dir.mkdir(
        parents=True,
        exist_ok=False
    )

    chart_path = (
        case_dir / "chart.png"
    )

    _download_telegram_photo(
        best_photo["file_id"],
        chart_path
    )

    from_user = (
        callback_query.get("from")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    review = {
        "schema_version": "1.0",
        "source": "telegram_review_button",
        "saved_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "symbol": parsed["symbol"],
        "timeframe": parsed["timeframe"],
        "review_action": action,
        "review_label": ACTION_LABELS[action],
        "chart": "chart.png",
        "telegram": {
            "callback_query_id":
                callback_query.get("id"),
            "message_id":
                message.get("message_id"),
            "chat_id":
                chat.get("id"),
            "user_id":
                from_user.get("id"),
            "username":
                from_user.get("username"),
            "photo_file_id":
                best_photo.get("file_id"),
            "photo_unique_id":
                best_photo.get(
                    "file_unique_id"
                ),
        },
    }

    (
        case_dir / "review.json"
    ).write_text(
        json.dumps(
            review,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    return case_dir


_ROBOT_CONTROL_SUCCESS_TEXT = {
    "start": f"{ROBOT_EMOJI} Робот: запущен ▶",
    "pause": f"{ROBOT_EMOJI} Робот: на паузе ⏸",
    "resume": f"{ROBOT_EMOJI} Робот: возобновлён ▶",
    "stop": f"{ROBOT_EMOJI} Робот: остановлен ⏹",
}


def _call_robot_control_command(command):
    # Dispatched by name (not a dict of pre-bound functions) so tests can
    # patch telegram_review.<name>_robot the same way they already patch
    # admit_robot_candidate, instead of a reference captured at import time.
    if command == "pause":
        return pause_robot(http_post=_post_robot_synchronize_pending_entries)
    raise ValueError(f"unsupported Robot control command: {command}")


def _post_robot_backend_command(url, payload, *, command):
    """Shared Telegram transport: preserve each Robot command's wire contract."""
    response = requests.post(url, json=payload, timeout=15)
    body = response.json()
    if response.status_code != 200 or not body.get("ok", False):
        raise RobotControlRejected(f"PAPER backend rejected {command}: {body}")
    return body


def _post_robot_close_all_now(url, payload):
    # close_all_now() owns legality; Telegram supplies the existing network
    # transport without duplicating response validation.
    return _post_robot_backend_command(url, payload, command="close_all_now")


def _post_robot_synchronize_pending_entries(url, payload):
    # Shared bridge for pause/stop, with its original rejection identity.
    return _post_robot_backend_command(url, payload, command="synchronize_pending_entries")


def _request_close_all_confirmation(callback_query):
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    _answer_callback(
        callback_query.get("id"),
        "Подтвердите закрытие всех позиций робота",
    )
    if chat_id is not None:
        telegram_bot.send_message(
            config.TELEGRAM_TOKEN,
            chat_id,
            "❌ Закрыть все позиции робота Market-ордером? Это действие необратимо.",
            reply_markup=build_robot_close_all_confirmation_keyboard(),
        )


def _robot_close_all_callback_action_id(callback_query):
    """Tie a retried Telegram delivery to its original PAPER close action.

    Telegram callback_query.id uniquely identifies the confirmed button tap.
    We hash it into the existing opaque client_action_id rather than storing
    Telegram data in PAPER commands. Separate confirmation taps remain separate
    operator actions; legacy callers without callback IDs keep their default.
    """
    callback_id = callback_query.get("id")
    if not isinstance(callback_id, str) or not callback_id:
        return None
    digest = hashlib.sha256(
        ("robot-close-all-confirm" + chr(0) + callback_id).encode("utf-8")
    ).hexdigest()[:32]
    return f"robot-close-all-cb-{digest}"


def _confirm_close_all_now(callback_query):
    action_id = _robot_close_all_callback_action_id(callback_query)
    try:
        result = close_all_now(
            http_post=_post_robot_close_all_now,
            **({"client_action_id": action_id} if action_id is not None else {}),
        )
    except RobotControlRejected as exc:
        _answer_callback(
            callback_query.get("id"),
            f"{ROBOT_EMOJI} Робот: отклонено — {exc}",
        )
        print("[ROBOT CONTROL REJECTED]", "close_all", exc)
        return None
    except Exception as exc:
        _answer_callback(callback_query.get("id"), f"{ROBOT_EMOJI} Робот: ошибка команды")
        print("[ROBOT CONTROL ERROR]", "close_all", exc)
        return None

    prefix = f"{ROBOT_EMOJI} Робот: закрытие отправлено ❌"
    _answer_callback(callback_query.get("id"), prefix)
    _send_robot_status_panel(callback_query, prefix)
    print("[ROBOT CONTROL]", "close_all", result)
    return result


def _run_robot_control_command(
    callback_query,
    command,
):
    if command == "status":
        prefix = f"{ROBOT_EMOJI} Робот"
        _answer_callback(callback_query.get("id"), prefix)
        _send_robot_status_panel(callback_query, prefix)
        return None

    # close_all_now() is the one command that forces an immediate Market
    # close, so it is never fired directly from a single tap -- see
    # AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 Rationale and
    # CR-ROBOT-CONTROL-001's approved_scope for the one-tap confirmation.
    if command == "close_all":
        _request_close_all_confirmation(callback_query)
        return None
    if command == "close_all_confirm":
        return _confirm_close_all_now(callback_query)
    if command == "close_all_cancel":
        prefix = "Отменено"
        _answer_callback(callback_query.get("id"), prefix)
        _send_robot_status_panel(callback_query, prefix)
        return None
    if command in ("start", "resume"):
        return _run_robot_intent(callback_query, command)
    if command == "stop":
        return _run_runtime_stop(callback_query)

    try:
        state = _call_robot_control_command(command)
    except RobotControlRejected as exc:
        _answer_callback(
            callback_query.get("id"),
            f"{ROBOT_EMOJI} Робот: отклонено — {exc}",
        )
        print(
            "[ROBOT CONTROL REJECTED]",
            command,
            exc,
        )
        return None
    except Exception as exc:
        _answer_callback(
            callback_query.get("id"),
            f"{ROBOT_EMOJI} Робот: ошибка команды"
        )
        print(
            "[ROBOT CONTROL ERROR]",
            command,
            exc
        )
        return None

    prefix = _ROBOT_CONTROL_SUCCESS_TEXT[command]
    _answer_callback(
        callback_query.get("id"),
        prefix,
    )
    _send_robot_status_panel(callback_query, prefix)
    print(
        "[ROBOT CONTROL]",
        command,
        state.mode,
        state.recovery_status,
    )
    return state


def _run_robot_intent(callback_query, command):
    # START/RESUME are the owner's ROBOT runtime intent; the shared bootstrap may
    # need to start the PAPER backend first, so the callback is answered up front.
    _answer_callback(callback_query.get("id"), f"{ROBOT_EMOJI} Робот: запуск…")
    result = telegram_runtime_intent.execute("ROBOT")
    if result.ok:
        _send_robot_status_panel(callback_query, _ROBOT_CONTROL_SUCCESS_TEXT[command])
    else:
        chat_id = ((callback_query.get("message") or {}).get("chat") or {}).get("id")
        if chat_id is not None:
            try:
                telegram_bot.send_message(
                    config.TELEGRAM_TOKEN, chat_id, telegram_runtime_intent.failure_text(result),
                )
            except Exception as exc:
                print("[ROBOT CONTROL ERROR]", command, exc)
    print("[ROBOT CONTROL]", command, result.message)
    return result


def _run_runtime_stop(callback_query):
    # Robot Stop is the owner's FULL runtime stop. The canonical helper runs as an
    # independent process because it will shut down this Telegram worker itself.
    _answer_callback(callback_query.get("id"), f"{ROBOT_EMOJI} Робот: остановка…")
    chat_id = ((callback_query.get("message") or {}).get("chat") or {}).get("id")
    text = "⏹ Останавливаю сканер, робота, Telegram и backend…"
    try:
        stop_robot_runtime.launch_detached(stop_robot_runtime.SCOPE_ALL, notify_chat=chat_id)
    except Exception as exc:
        print("[ROBOT CONTROL ERROR]", "stop", type(exc).__name__)
        text = "⚠ Остановка не запущена."
    if chat_id is not None:
        try:
            telegram_bot.send_message(config.TELEGRAM_TOKEN, chat_id, text)
        except Exception as exc:
            print("[ROBOT CONTROL ERROR]", "stop", exc)
    return None


def _approve_robot_candidate(
    callback_query,
    parsed,
):
    message = callback_query.get("message") or {}
    from_user = callback_query.get("from") or {}
    chat = message.get("chat") or {}

    record, changed = admit_robot_candidate(
        parsed["candidate_id"],
        approval={
            "source": "telegram_robot_button",
            "callback_query_id": callback_query.get("id"),
            "message_id": message.get("message_id"),
            "chat_id": chat.get("id"),
            "user_id": from_user.get("id"),
            "username": from_user.get("username"),
        },
    )

    return record, changed


def _send_robot_status_panel(
    callback_query,
    prefix,
):
    # The sole entry point into the admission-gate control panel today (no
    # /robot command, no send-once-at-startup message -- see
    # CR-ROBOT-CONTROL-001): every press of the per-signal "🤖 Робот" button
    # re-sends the panel with live state, whether admission succeeded,
    # was rejected, or errored.
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if chat_id is None:
        return

    try:
        status = get_robot_runtime_status()
    except Exception as exc:
        print(
            "[ROBOT STATUS PANEL ERROR]",
            exc,
        )
        return

    mode = status.mode if status is not None else "ROBOT_STOPPED"
    recovery_status = status.recovery_status if status is not None else "ROBOT_STOPPED"

    try:
        telegram_bot.send_message(
            config.TELEGRAM_TOKEN,
            chat_id,
            f"{prefix}\n\nСтатус робота: {format_robot_status_text(mode, recovery_status)}",
            reply_markup=build_robot_control_keyboard(mode, recovery_status),
        )
    except Exception as exc:
        print(
            "[ROBOT STATUS PANEL ERROR]",
            exc,
        )


def _process_callback(
    callback_query
):
    data = callback_query.get(
        "data",
        ""
    )

    parsed = _parse_callback(data)
    if parsed is None:
        parsed = _parse_workspace_callback(data)
    if parsed is None:
        parsed = _parse_robot_callback(data)
    if parsed is None:
        control_command = parse_robot_control_callback(data)
        if control_command is not None:
            parsed = {"kind": "robot_control", "command": control_command}

    if parsed is None:
        return

    owner_id = str(
        getattr(config, "TELEGRAM_CHAT_ID", "")
    ).strip()

    callback_user_id = str(
        (
            callback_query.get("from")
            or {}
        ).get("id", "")
    ).strip()

    if not owner_id or callback_user_id != owner_id:
        _answer_callback(
            callback_query.get("id"),
            "Недостаточно прав"
        )
        return

    if parsed["kind"] == "workspace":
        # Accept workspace launch requests only from the owner's private chat.
        # User-id equality alone is insufficient when a bot message is reused
        # in another chat. Never launch a PC process from a group callback.
        callback_chat = (callback_query.get("message") or {}).get("chat") or {}
        if (str(callback_chat.get("id", "")).strip() != owner_id or callback_chat.get("type") != "private"):
            _answer_callback(callback_query.get("id"), "Открытие разрешено только в личном чате")
            return
        _run_workspace_callback(callback_query, parsed)
        return

    if parsed["kind"] == "robot_control":
        _run_robot_control_command(
            callback_query,
            parsed["command"],
        )
        return

    if parsed["kind"] == "robot":
        try:
            record, changed = _approve_robot_candidate(
                callback_query,
                parsed,
            )

            prefix = (
                f"🤖 Сигнал принят: {record.symbol.value} ✅"
                if changed
                else f"🤖 Этот сигнал уже был принят ранее: {record.symbol.value} ❗"
            )
            _answer_callback(
                callback_query.get("id"),
                prefix,
            )

            print(
                "[ROBOT CANDIDATE APPROVED]",
                record.candidate_id,
                record.symbol.value,
            )
        except RobotAdmissionRejected as exc:
            prefix = f"{ROBOT_EMOJI} Робот: отклонено — {_robot_admission_reason_text(exc)}"
            print(
                "[ROBOT CANDIDATE REJECTED]",
                exc,
            )
            _answer_callback(
                callback_query.get("id"),
                prefix,
            )
        except RobotCandidateNotFound as exc:
            prefix = f"{ROBOT_EMOJI} Робот: сигнал устарел или больше не найден"
            print(
                "[ROBOT CANDIDATE NOT FOUND]",
                exc,
            )
            _answer_callback(
                callback_query.get("id"),
                prefix,
            )
        except Exception as exc:
            prefix = f"{ROBOT_EMOJI} Робот: ошибка сохранения"
            print(
                "[ROBOT CANDIDATE ERROR]",
                exc
            )
            _answer_callback(
                callback_query.get("id"),
                prefix,
            )

        _send_robot_status_panel(
            callback_query,
            prefix,
        )
        return

    try:
        case_dir = _save_review(
            callback_query,
            parsed
        )

        _answer_callback(
            callback_query["id"],
            "Сохранено в Review Queue ✅"
        )

        print(
            "[REVIEW SAVED]",
            case_dir
        )

    except Exception as exc:
        print(
            "[REVIEW ERROR]",
            exc
        )

        _answer_callback(
            callback_query.get("id"),
            "Ошибка сохранения"
        )


def run():
    print("=" * 60)
    print("BybitScanner Telegram Review Listener")
    print(f"Queue: {REVIEW_QUEUE}")
    print("=" * 60)

    offset = _load_offset()

    while True:
        try:
            params = {
                "timeout": 30,
                "allowed_updates":
                    json.dumps(
                        ["callback_query"]
                    ),
            }

            if offset is not None:
                params["offset"] = offset

            result = _telegram_request(
                "getUpdates",
                **params
            )

            if not result.get("ok"):
                print(
                    "[REVIEW TELEGRAM ERROR]",
                    result
                )
                time.sleep(3)
                continue

            for update in result.get(
                "result",
                []
            ):
                update_id = update.get(
                    "update_id"
                )

                if update_id is not None:
                    offset = update_id + 1
                    _save_offset(offset)

                callback_query = update.get(
                    "callback_query"
                )

                if callback_query:
                    _process_callback(
                        callback_query
                    )

        except KeyboardInterrupt:
            print()
            print("Review listener stopped.")
            break

        except Exception as exc:
            print(
                "[REVIEW LOOP ERROR]",
                exc
            )
            time.sleep(3)


if __name__ == "__main__":
    run()
