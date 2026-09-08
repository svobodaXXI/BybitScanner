"""Safe user-facing mapping for expected application failures."""

from app.application.errors import (
    AccountNotFoundError,
    CustomFieldNotApplicableError,
    CustomFieldNotFoundError,
    CustomFieldNotManualError,
    DuplicateTradeCustomValueError,
    InvalidCustomFieldValueError,
    TradeAlreadyClosedError,
    TradeNotFoundError,
    HistoricalPreviewError,
)
from app.infrastructure.exchanges.bybit.errors import (
    BybitAuthenticationError,
    BybitPayloadError,
    BybitRateLimitError,
    BybitRequestError,
)


def user_error(error: Exception) -> str | None:
    if isinstance(error, HistoricalPreviewError):
        reasons = {
            "HISTORICAL_POSITION_CONTEXT": "не удалось восстановить позицию на границе периода",
            "HISTORICAL_AGGREGATION": "ошибка агрегации исторических исполнений",
            "HISTORICAL_NORMALIZATION": "ошибка нормализации исторических исполнений",
            "HISTORICAL_FETCH": "не удалось получить исторические исполнения",
        }
        return f"❌ Не удалось сформировать предпросмотр.\n\nПричина: {reasons.get(error.code, 'ошибка обработки исторических данных')}.\nКод: {error.code}"
    if isinstance(error, BybitRequestError):
        return f"❌ Ошибка Bybit\n\n{str(error)[:600]}"
    if isinstance(error, BybitAuthenticationError):
        return "❌ Bybit отклонил запрос авторизации или разрешений."
    if isinstance(error, BybitRateLimitError):
        return "❌ Bybit временно ограничил частоту запросов. Повторите позже."
    if isinstance(error, BybitPayloadError):
        return "❌ Bybit вернул неподдерживаемые или некорректные данные."
    if isinstance(error, AccountNotFoundError):
        return "❌ Аккаунт не найден."
    if isinstance(error, TradeNotFoundError):
        return "❌ Сделка не найдена."
    if isinstance(error, TradeAlreadyClosedError):
        return "❌ Сделка уже закрыта."
    if isinstance(error, CustomFieldNotFoundError):
        return "❌ Поле не найдено."
    if isinstance(error, CustomFieldNotManualError):
        return "❌ Это поле заполняется автоматически."
    if isinstance(error, CustomFieldNotApplicableError):
        return "❌ Поле не применимо в этом контексте."
    if isinstance(error, InvalidCustomFieldValueError):
        return "❌ Некорректное значение поля. Повторите ввод."
    if isinstance(error, DuplicateTradeCustomValueError):
        return "❌ Это значение уже сохранено."
    return None
