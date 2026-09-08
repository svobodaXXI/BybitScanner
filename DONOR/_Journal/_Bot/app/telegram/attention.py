"""Telegram presentation helpers for Attention Center notifications."""

from app.application.attention import AttentionItem, AttentionSummary


def format_attention_reminder(item: AttentionItem) -> str:
    label = item.instrument_label or "Инструмент недоступен"
    if item.readiness.status.value == "OPEN":
        headline = f"{label} открыта и требует внимания."
    else:
        headline = f"{label} закрыта, но не готова к статистике."
    missing = "\n".join(f"• {_missing_label(reason)}" for reason in item.readiness.missing)
    return f"⚠ {headline}\n\nНе заполнено:\n{missing or '• Проверьте данные сделки'}\n\nОткройте сделку в Telegram и заполните данные."


def _missing_label(reason: str) -> str:
    return {
        "INSTRUMENT": "Инструмент",
        "DIRECTION": "Направление",
        "ENTRY_PRICE": "Цена входа",
        "QUANTITY": "Количество",
        "EXIT_PRICE": "Цена выхода",
        "NET_PNL": "Результат сделки",
    }.get(reason, "Обязательное поле")


def format_attention_digest(summary: AttentionSummary) -> str:
    return (
        f"⚠ В журнале требуют внимания {summary.total_attention} сделок\n\n"
        f"{summary.open_count} открыты\n"
        f"{summary.incomplete_count} закрыты, но не заполнены"
    )
