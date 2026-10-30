"""
signal_memory.py

Память торговых сигналов.

Хранит историю обнаруженных сетапов:
- первое обнаружение;
- последний score;
- направление;
- статус развития.
"""


import os
import json
import time
from datetime import datetime



MEMORY_FILE = "signals_history.json"



def load_memory():

    """
    Загружает историю сигналов.
    """

    if not os.path.exists(MEMORY_FILE):

        return {}


    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)


    except Exception:

        return {}




def save_memory(memory):

    """
    Сохраняет историю.
    """

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(

            memory,

            file,

            indent=4,

            ensure_ascii=False

        )




def _signal_key(signal):
    """The exact same scoped identity used by update_signal."""
    symbol = signal["symbol"]
    timeframe = signal.get("timeframe")
    pattern = signal["pattern"]
    formation_id = signal.get("formation_id")
    if timeframe is not None and not str(timeframe).strip():
        raise ValueError("signal timeframe must not be empty")
    return (
        f"scanner:{symbol}:{str(timeframe).strip()}:{pattern}"
        + (f":{formation_id}" if formation_id is not None else "")
        if timeframe is not None else symbol
    )


def record_telegram_delivery(signal, delivered, *, retry_delay_seconds=300):
    """Record an attempted signal delivery, not a trading decision.

    A failed attempt re-arms the same signal after a cooldown, even when its
    score stays unchanged. Preexisting signals without this flag are not replayed.
    """
    memory = load_memory()
    record = memory.get(_signal_key(signal))
    if not isinstance(record, dict):
        return
    if delivered:
        record.pop("telegram_retry_after_epoch", None)
    else:
        record["telegram_retry_after_epoch"] = int(time.time()) + retry_delay_seconds
    save_memory(memory)


def update_signal(signal):

    """
    Обновляет сигнал в памяти.

    Возвращает статус изменения.
    """

    memory = load_memory()


    symbol = signal["symbol"]
    timeframe = signal.get("timeframe")
    pattern = signal["pattern"]
    formation_id = signal.get("formation_id")
    # Existing callers retain their symbol-only memory until they explicitly
    # opt into timeframe-scoped identities.
    key = _signal_key(signal)
    # Preserve the previous 5m score when migrating the same pattern.
    prior_scoped = any(
        existing.startswith(f"scanner:{symbol}:5:{pattern}:")
        for existing in memory
    )
    if key not in memory and str(timeframe).strip() == "5" and not prior_scoped:
        legacy = memory.get(symbol)
        if isinstance(legacy, dict) and legacy.get("pattern") == pattern:
            memory[key] = dict(legacy)


    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )



    if key not in memory:


        memory[key] = {

            "first_seen": now,

            "last_seen": now,

            "previous_score": signal["score"],

            "current_score": signal["score"],

            "direction": signal["direction"],

            "pattern": signal["pattern"]

        }


        status = "NEW"



    else:


        old_score = memory[key].get(
            "current_score",
            0
        )


        new_score = signal["score"]


        difference = new_score - old_score



        if difference >= 5:

            status = "STRENGTHENING"


        elif difference <= -5:

            status = "WEAKENING"


        else:

            status = "STABLE"



        if (status not in ("NEW", "STRENGTHENING")
                and memory[key].get("telegram_retry_after_epoch") is not None
                and int(time.time()) >= int(memory[key]["telegram_retry_after_epoch"])):
            status = "NEW"

        memory[key].update({

            "last_seen": now,

            "previous_score": old_score,

            "current_score": new_score,

            "direction": signal["direction"],

            "pattern": signal["pattern"]

        })



    save_memory(
        memory
    )


    return status




def get_signal(symbol):

    """
    Получить сохранённый сигнал.
    """

    memory = load_memory()

    return memory.get(
        symbol
    )