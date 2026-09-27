"""Telegram owner access to the shared runtime intent bootstrap.

The calling Telegram worker already owns getUpdates, so the bootstrap proves
or starts only the PAPER backend before its single POST /api/runtime/intent.
Backend identity, spawn and intent routing stay in tools.runtime_intent.
"""

from __future__ import annotations

from tools.runtime_intent import BootstrapResult, OUTCOME_BLOCKED, execute_runtime_intent

NOT_CONFIRMED_TEXT = "⚠ Запуск не подтверждён."


def execute(intent: str) -> BootstrapResult:
    try:
        result = execute_runtime_intent(intent, require_telegram=False, out=_log)
    except Exception as exc:
        result = BootstrapResult(
            intent, "ERROR", f"ERROR: intent={intent} bootstrap raised {type(exc).__name__}",
        )
    _log(result.message)
    return result


def failure_text(result: BootstrapResult) -> str:
    if result.outcome == OUTCOME_BLOCKED and result.blocked_by:
        return "⛔ Запуск заблокирован: " + ", ".join(result.blocked_by)
    return NOT_CONFIRMED_TEXT


def _log(line: str) -> None:
    print("[RUNTIME INTENT]", line, flush=True)
