from pathlib import Path
from datetime import datetime
import json
import re
import time

import requests

import config


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
        "action": action,
        "symbol": symbol,
        "timeframe": timeframe,
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


def _process_callback(
    callback_query
):
    data = callback_query.get(
        "data",
        ""
    )

    parsed = _parse_callback(
        data
    )

    if parsed is None:
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
