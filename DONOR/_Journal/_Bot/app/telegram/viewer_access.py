"""Manual owner/viewer authorization at the Telegram transport boundary."""

from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject, WebAppInfo

from app.core.access import AccessRole
from app.infrastructure.persistence.telegram_access import TelegramAccessStore

from .config import TelegramSettings

logger = logging.getLogger(__name__)


class TelegramViewerAuthorizationMiddleware(BaseMiddleware):
    """Keep owner behavior intact while limiting approved viewers to the WebApp entry point."""

    def __init__(self, settings: TelegramSettings, access_store: TelegramAccessStore) -> None:
        self._settings = settings
        self._access_store = access_store

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = getattr(event, "from_user", None)
        user_id = user.id if user is not None else None
        if user_id is None:
            return None

        role = await self._access_store.resolve_role(user_id, self._settings.allowed_user_id)
        if role is None:
            logger.warning("Unauthorized Telegram access attempt: user_id=%s", user_id)
            await _deny_unknown(event)
            return None

        data["access_role"] = role
        if role is AccessRole.VIEWER:
            if _is_start_message(event):
                await _send_viewer_start(event, self._settings.webapp_url)
            else:
                await _deny_viewer_write(event)
            return None

        if isinstance(event, Message):
            command, argument = _admin_command(event.text)
            if command is not None:
                await self._handle_owner_command(event, command, argument)
                return None

        return await handler(event, data)

    async def _handle_owner_command(self, message: Message, command: str, argument: str | None) -> None:
        try:
            viewer_id = int(argument or "")
            if viewer_id <= 0:
                raise ValueError
        except ValueError:
            await message.answer(f"Использование: /{command} TELEGRAM_ID")
            return

        if self._settings.allowed_user_id is not None and viewer_id == self._settings.allowed_user_id:
            await message.answer("Этот Telegram ID уже является владельцем журнала.")
            return

        if command == "grant_viewer":
            await self._access_store.grant_viewer(viewer_id)
            await message.answer(f"Доступ предоставлен пользователю {viewer_id}. Режим просмотра.")
            return

        revoked = await self._access_store.revoke_viewer(viewer_id)
        if revoked:
            await message.answer(f"Доступ пользователя {viewer_id} отключён.")
        else:
            await message.answer(f"Пользователь {viewer_id} не имеет доступа на просмотр.")


def _admin_command(text: str | None) -> tuple[str | None, str | None]:
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None, None
    parts = raw.split(maxsplit=1)
    command = parts[0][1:].split("@", 1)[0].lower()
    if command not in {"grant_viewer", "revoke_viewer"}:
        return None, None
    return command, parts[1].strip() if len(parts) == 2 else None


def _is_start_message(event: TelegramObject) -> bool:
    if not isinstance(event, Message):
        return False
    command = (event.text or "").strip().split(maxsplit=1)[0].split("@", 1)[0].lower()
    return command == "/start"


def _viewer_keyboard(webapp_url: str | None):
    if not webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть журнал", web_app=WebAppInfo(url=webapp_url))]
        ]
    )


async def _send_viewer_start(message: Message, webapp_url: str | None) -> None:
    await message.answer(
        "Доступ предоставлен.\nРежим просмотра.",
        reply_markup=_viewer_keyboard(webapp_url),
    )


async def _deny_unknown(event: TelegramObject) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer("⛔ Доступ запрещён.", show_alert=True)
    elif isinstance(event, Message):
        await event.answer("⛔ Доступ запрещён.")


async def _deny_viewer_write(event: TelegramObject) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer("Редактирование отключено.", show_alert=True)
    elif isinstance(event, Message):
        await event.answer("Редактирование отключено.")
